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
    this transaction. No claim is granted while restore maintenance fencing
    is active (worker quiesce; stale complete_job generation check below
    stays as the commit-side fence).
    """
    try:
        from x_insight.operations.restore import maintenance_active

        if maintenance_active():
            return None
    except Exception:
        pass
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


def reschedule_for_retry(
    job_id: str,
    lease_token: str,
    available_at: datetime,
    database_url: str | None = None,
    failure_details: Any = None,
) -> bool:
    """Park a still-claimed job back to ``queued`` with future eligibility.

    Single short transaction (no sleeping while holding locks): only the
    holder of the current lease may reschedule, and only from ``claimed``.
    The next :func:`claim_next_job` skips the row until ``available_at``
    (``available_at <= now`` gate) and then re-claims it with fencing+1
    and a fresh lease. Failed rows are never touched here. An optional
    secret-free last-error marker (``{"code": ..., "error": "failed"}``)
    stays visible on the queued row for transparency; it never carries
    secrets.
    """
    now = now_utc()
    if failure_details is None:
        failure_json: str | None = None
    elif isinstance(failure_details, str):
        failure_json = failure_details
    else:
        try:
            failure_json = json.dumps(failure_details, sort_keys=True, default=str)
        except Exception:
            failure_json = None
    with db.transaction(database_url) as conn:
        row = (
            conn.execute(
                text(
                    "SELECT lease_token, status FROM reasoning_jobs "
                    "WHERE id = :id FOR UPDATE"
                ),
                {"id": str(job_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return False
        if str(row["lease_token"]) != str(lease_token):
            return False
        if str(row["status"]) != "claimed":
            return False
        conn.execute(
            text(
                "UPDATE reasoning_jobs SET status = 'queued', "
                "available_at = :available_at, lease_token = NULL, "
                "lease_deadline = NULL, "
                "failure_details = COALESCE("
                "CAST(:failure_details AS jsonb), failure_details), "
                "updated_at = :now "
                "WHERE id = :id"
            ),
            {
                "available_at": available_at,
                "failure_details": failure_json,
                "now": now,
                "id": str(job_id),
            },
        )
        return True


def get_batch_start(job_id: str, database_url: str | None = None) -> int:
    """Return the job's current batch start attempt (0 when unknown)."""
    with db.transaction(database_url) as conn:
        try:
            row = (
                conn.execute(
                    text(
                        "SELECT batch_start_attempt FROM reasoning_jobs WHERE id = :id"
                    ),
                    {"id": str(job_id)},
                )
                .mappings()
                .first()
            )
        except Exception:
            return 0
        if row is None:
            return 0
        try:
            return int(row["batch_start_attempt"] or 0)
        except (TypeError, ValueError):
            return 0


def requeue_failed_job(
    job_id: str,
    failed_stage: str,
    database_url: str | None = None,
) -> bool:
    """Start a new bounded batch for a terminally failed job.

    Single short transaction: only a ``failed`` row may be requeued.
    The attempt ledger is retained (never deleted); the new batch
    starts at the current ``attempt_count`` so only fresh attempts
    count against the per-batch budget. The run returns to ``queued``
    so the next claim can proceed. Pinned rows are never touched.
    """
    now = now_utc()
    with db.transaction(database_url) as conn:
        row = (
            conn.execute(
                text(
                    "SELECT id, run_id, status, attempt_count FROM reasoning_jobs "
                    "WHERE id = :id FOR UPDATE"
                ),
                {"id": str(job_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return False
        if str(row["status"]) != "failed":
            return False
        conn.execute(
            text(
                "UPDATE reasoning_jobs SET status = 'queued', "
                "available_at = :now, lease_token = NULL, "
                "lease_deadline = NULL, "
                "retry_batch = COALESCE(retry_batch, 0) + 1, "
                "batch_start_attempt = :attempt_count, "
                "failed_stage = :failed_stage, stage = :failed_stage, "
                "failure_details = NULL, updated_at = :now "
                "WHERE id = :id"
            ),
            {
                "now": now,
                "attempt_count": int(row["attempt_count"] or 0),
                "failed_stage": str(failed_stage),
                "id": str(row["id"]),
            },
        )
        conn.execute(
            text(
                "UPDATE runs SET status = 'queued', updated_at = :now "
                "WHERE id = :run_id AND status = 'failed'"
            ),
            {"now": now, "run_id": str(row["run_id"])},
        )
        return True


def begin_attempt(
    job_id: str,
    lease_token: str,
    database_url: str | None = None,
) -> int | None:
    """Persist one attempt start before outbound work; return its index.

    Single short transaction: only the holder of the current ``claimed``
    lease may begin, and the attempt row (outcome NULL) plus the bumped
    ``attempt_count`` survive a worker crash. An uncertain in-flight
    request therefore consumes its recorded attempt; recovery reclaims the
    lease and begins the next index instead of resetting the counter.
    """
    now = now_utc()
    with db.transaction(database_url) as conn:
        row = (
            conn.execute(
                text(
                    "SELECT id, run_id, lease_token, status, attempt_count "
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
        if str(row["status"]) != "claimed":
            return None
        next_index = int(row["attempt_count"] or 0) + 1
        conn.execute(
            text(
                "INSERT INTO reasoning_attempts "
                "(job_id, run_id, attempt_index, lease_token, "
                "started_at, finished_at, outcome, error_details) "
                "VALUES (:job_id, :run_id, :attempt_index, :lease_token, "
                ":started_at, NULL, NULL, NULL) "
                "ON CONFLICT (job_id, attempt_index) DO NOTHING"
            ),
            {
                "job_id": str(row["id"]),
                "run_id": str(row["run_id"]),
                "attempt_index": next_index,
                "lease_token": str(lease_token),
                "started_at": now,
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


def finish_attempt(
    job_id: str,
    attempt_index: int,
    outcome: Any = None,
    error_details: Any = None,
    database_url: str | None = None,
) -> bool:
    """Close a begun attempt with its outcome; True when the row exists."""
    now = now_utc()
    with db.transaction(database_url) as conn:
        updated = conn.execute(
            text(
                "UPDATE reasoning_attempts SET finished_at = :now, "
                "outcome = :outcome, "
                "error_details = CAST(:error_details AS jsonb) "
                "WHERE job_id = :job_id AND attempt_index = :attempt_index"
            ),
            {
                "now": now,
                "outcome": _outcome_text(outcome),
                "error_details": _error_json(error_details),
                "job_id": str(job_id),
                "attempt_index": int(attempt_index),
            },
        )
        return bool(updated.rowcount and updated.rowcount > 0)


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
