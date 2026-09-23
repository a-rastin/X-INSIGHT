"""Durable leased job queue (S44 slices 1-4, extensible)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from x_insight import db

HEARTBEAT_INTERVAL_SECONDS = 15
LEASE_SECONDS = 120
MAX_PROVIDER_SLOTS = 2
MAX_QUEUED_RUNS = 100

ACTIVE_RUN_STATUSES = frozenset(
    {
        "queued",
        "preparing_question",
        "estimating_cpts",
        "validating_cpts",
        "inferring",
        "rendering",
    }
)

TERMINAL_RUN_STATUSES = frozenset(
    {
        "succeeded",
        "failed",
        "needs_clarification",
        "stale",
        "cancelled",
    }
)


def _default_now() -> datetime:
    return datetime.now(UTC)


_now_fn: Callable[[], datetime] = _default_now


def now_utc() -> datetime:
    """Return the current UTC time (overridable in tests)."""
    return _now_fn()


def set_now_fn(fn: Callable[[], datetime]) -> None:
    """Override the clock (tests only); use :func:`reset_now_fn` after."""
    global _now_fn
    _now_fn = fn


def reset_now_fn() -> None:
    """Restore the production UTC clock."""
    global _now_fn
    _now_fn = _default_now


def lease_deadline_from(now: datetime) -> datetime:
    """Return the lease deadline for a claim/heartbeat made at ``now``."""
    return now + timedelta(seconds=LEASE_SECONDS)


def get_deployment_generation(database_url: str | None = None) -> int:
    """Return the current deployment generation (1 when uninitialized)."""
    with db.transaction(database_url) as conn:
        try:
            value = conn.execute(
                text("SELECT generation FROM deployment_state WHERE id = 1")
            ).scalar()
        except Exception:
            return 1
        if value is None:
            try:
                conn.execute(
                    text(
                        "INSERT INTO deployment_state (id, generation) "
                        "VALUES (1, 1) ON CONFLICT (id) DO NOTHING"
                    )
                )
            except Exception:
                pass
            return 1
        return int(value)


def set_deployment_generation(generation: int, database_url: str | None = None) -> int:
    """Persist the deployment generation (tests/fencing rotation)."""
    value = int(generation)
    with db.transaction(database_url) as conn:
        conn.execute(
            text(
                "INSERT INTO deployment_state (id, generation) "
                "VALUES (1, :generation) ON CONFLICT (id) "
                "DO UPDATE SET generation = :generation"
            ),
            {"generation": value},
        )
    return value


def _current_generation(conn: Any) -> int:
    try:
        value = conn.execute(
            text("SELECT generation FROM deployment_state WHERE id = 1")
        ).scalar()
    except Exception:
        return 1
    if value is None:
        return 1
    return int(value)


def _outcome_text(outcome: Any) -> str | None:
    if outcome is None:
        return None
    if isinstance(outcome, str):
        return outcome
    try:
        return json.dumps(outcome, sort_keys=True, default=str)
    except Exception:
        return str(outcome)


def _error_json(outcome_error: Any) -> str | None:
    if outcome_error is None:
        return None
    if isinstance(outcome_error, str):
        return outcome_error
    try:
        return json.dumps(outcome_error, sort_keys=True, default=str)
    except Exception:
        return str(outcome_error)


def first_eligible_question(
    pins: Mapping[str, Any],
    triples: list[tuple[str, dict[str, Any], str]],
) -> tuple[str, int] | None:
    """Return (question_key, ordinal) for the first ready question.

    Triples are in :func:`build_projections` order. A question is
    eligible when its persisted projection ``applicability`` is
    ``ready``. Return None when no question is ready (no job).
    """
    _ = pins
    for ordinal, (question_key, projection, _projection_hash) in enumerate(triples):
        if isinstance(projection, dict) and projection.get("applicability") == "ready":
            return (question_key, ordinal)
    return None


def claim_next_job(
    *,
    worker_id: str | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Claim one queued job under the global provider-slot cap.

    Single short transaction: advisory-serialize claims, refuse when
    ``MAX_PROVIDER_SLOTS`` live leases exist, else claim the oldest
    eligible job (``FOR UPDATE SKIP LOCKED``) with a fresh lease token.
    Expired claimed leases (deadline at or before now) are eligible for
    reclaim with fencing+1. The caller must invoke the provider OUTSIDE
    this transaction.
    """
    _ = worker_id
    now = now_utc()
    with db.transaction(database_url) as conn:
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "reasoning_claim"},
        )
        active = conn.execute(
            text(
                "SELECT COUNT(*) FROM reasoning_jobs "
                "WHERE status = 'claimed' AND lease_deadline > :now"
            ),
            {"now": now},
        ).scalar()
        if active is not None and int(active) >= MAX_PROVIDER_SLOTS:
            return None
        row = (
            conn.execute(
                text(
                    "SELECT j.id, j.run_id, j.question_key, j.ordinal, "
                    "j.fencing_generation, j.author_id, j.created_at "
                    "FROM reasoning_jobs j "
                    "LEFT JOIN queue_fairness qf "
                    "ON qf.physician_id = j.author_id "
                    "WHERE (j.status = 'queued' OR (j.status = 'claimed' "
                    "AND j.lease_deadline <= :now)) "
                    "AND (j.available_at IS NULL OR j.available_at <= :now) "
                    "ORDER BY (qf.last_granted_at IS NOT NULL), "
                    "qf.last_granted_at ASC NULLS FIRST, "
                    "j.created_at ASC, j.id ASC "
                    "LIMIT 1 FOR UPDATE OF j SKIP LOCKED"
                ),
                {"now": now},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        token = uuid.uuid4().hex
        generation = int(row["fencing_generation"] or 0) + 1
        deployment_generation = _current_generation(conn)
        deadline = lease_deadline_from(now)
        conn.execute(
            text(
                "UPDATE reasoning_jobs SET status = 'claimed', "
                "lease_token = :token, lease_deadline = :deadline, "
                "last_heartbeat = :now, fencing_generation = :generation, "
                "deployment_generation = :deployment, updated_at = :now "
                "WHERE id = :id"
            ),
            {
                "token": token,
                "deadline": deadline,
                "now": now,
                "generation": generation,
                "deployment": deployment_generation,
                "id": str(row["id"]),
            },
        )
        conn.execute(
            text(
                "UPDATE runs SET status = 'preparing_question', "
                "updated_at = :now WHERE id = :run_id"
            ),
            {"now": now, "run_id": str(row["run_id"])},
        )
        author_id = row["author_id"]
        if author_id is not None:
            conn.execute(
                text(
                    "INSERT INTO queue_fairness "
                    "(physician_id, last_granted_at, granted_count) "
                    "VALUES (:pid, :now, 1) ON CONFLICT (physician_id) "
                    "DO UPDATE SET last_granted_at = :now, "
                    "granted_count = queue_fairness.granted_count + 1"
                ),
                {"pid": str(author_id), "now": now},
            )
        return {
            "job_id": str(row["id"]),
            "run_id": str(row["run_id"]),
            "question_key": str(row["question_key"]),
            "ordinal": int(row["ordinal"]),
            "lease_token": token,
            "fencing_generation": generation,
            "deployment_generation": deployment_generation,
            "lease_deadline": deadline,
        }


def heartbeat(
    job_id: str,
    lease_token: str,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Extend a live lease; None on unknown token or expired lease."""
    now = now_utc()
    with db.transaction(database_url) as conn:
        row = (
            conn.execute(
                text(
                    "SELECT id, lease_token, lease_deadline FROM reasoning_jobs "
                    "WHERE id = :id FOR UPDATE"
                ),
                {"id": str(job_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        if str(row["lease_token"]) != str(lease_token):
            return None
        deadline = row["lease_deadline"]
        if deadline is None or deadline <= now:
            return None
        extended = lease_deadline_from(now)
        conn.execute(
            text(
                "UPDATE reasoning_jobs SET last_heartbeat = :now, "
                "lease_deadline = :deadline, updated_at = :now "
                "WHERE id = :id"
            ),
            {"now": now, "deadline": extended, "id": str(job_id)},
        )
        return {
            "job_id": str(job_id),
            "lease_token": str(lease_token),
            "lease_deadline": extended,
        }


def record_attempt(
    job_id: str,
    lease_token: str,
    outcome: Any = None,
    error_details: Any = None,
    database_url: str | None = None,
) -> int | None:
    """Persist one provider attempt; return its 1-based attempt_index."""
    now = now_utc()
    with db.transaction(database_url) as conn:
        row = (
            conn.execute(
                text(
                    "SELECT id, run_id, lease_token, attempt_count "
                    "FROM reasoning_jobs WHERE id = :id FOR UPDATE"
                ),
                {"id": str(job_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        if str(row["lease_token"]) != str(lease_token):
            return None
        next_index = int(row["attempt_count"] or 0) + 1
        conn.execute(
            text(
                "INSERT INTO reasoning_attempts "
                "(job_id, run_id, attempt_index, lease_token, "
                "started_at, finished_at, outcome, error_details) "
                "VALUES (:job_id, :run_id, :attempt_index, :lease_token, "
                ":started_at, :finished_at, :outcome, "
                "CAST(:error_details AS jsonb)) "
                "ON CONFLICT (job_id, attempt_index) DO NOTHING"
            ),
            {
                "job_id": str(row["id"]),
                "run_id": str(row["run_id"]),
                "attempt_index": next_index,
                "lease_token": str(lease_token),
                "started_at": now,
                "finished_at": now,
                "outcome": _outcome_text(outcome),
                "error_details": _error_json(error_details),
            },
        )
        conn.execute(
            text(
                "UPDATE reasoning_jobs SET attempt_count = :count, "
                "updated_at = :now WHERE id = :id"
            ),
            {"count": next_index, "now": now, "id": str(row["id"])},
        )
        return next_index


def complete_job(
    job_id: str,
    lease_token: str,
    outcome: Any = "succeeded",
    error_details: Any = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Commit a claimed job; None when the token/generation/lease is stale."""
    now = now_utc()
    with db.transaction(database_url) as conn:
        row = (
            conn.execute(
                text("SELECT * FROM reasoning_jobs WHERE id = :id FOR UPDATE"),
                {"id": str(job_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        if str(row["lease_token"]) != str(lease_token):
            return None
        deadline = row["lease_deadline"]
        if deadline is None or deadline <= now:
            return None
        current = _current_generation(conn)
        job_generation = (
            row["deployment_generation"] if "deployment_generation" in row else 1
        )
        if int(job_generation or 1) != int(current or 1):
            return None
        outcome_text = _outcome_text(outcome)
        error_json = _error_json(error_details)
        conn.execute(
            text(
                "UPDATE reasoning_jobs SET status = 'succeeded', "
                "failure_details = CAST(:error_details AS jsonb), "
                "updated_at = :now WHERE id = :id"
            ),
            {"error_details": error_json, "now": now, "id": str(job_id)},
        )
        return {
            "committed": True,
            "job_id": str(job_id),
            "lease_token": str(lease_token),
            "fencing_generation": int(row["fencing_generation"] or 0),
            "deployment_generation": int(current),
            "outcome": outcome_text,
        }
