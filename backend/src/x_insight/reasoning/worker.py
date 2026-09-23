"""Single-question worker step (S44 slices 2-4: claim + attempt outside txn).

S45 slice 1: when no explicit ``provider_adapter`` is passed, the claimed
job runs through the real coordinator (MCP + controlled provider +
inference); an explicitly passed adapter keeps the S44 compat path.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import text

from x_insight import db
from x_insight.reasoning import queue as queue_module


def _record_question_failure(claim: Any, exc: BaseException) -> None:
    """Best-effort terminal failure marker; never masks the original error.

    Sets the still-claimed job and its run to ``failed`` with a secret-free
    machine-readable code so GET surfaces the failure. Skipped unless the
    lease still matches (no clobbering reclaims) and no succeeded artifact
    exists (a stored success recommits instead of failing).
    """
    try:
        code = getattr(exc, "code", "failed")
        if (
            not isinstance(code, str)
            or not code.replace("_", "").replace("-", "").isalnum()
        ):
            code = "failed"
        job_id = str(claim["job_id"])
        lease_token = str(claim["lease_token"])
        run_id = str(claim["run_id"])
        question_key = str(claim["question_key"])
        with db.transaction() as conn:
            artifact = (
                conn.execute(
                    text(
                        "SELECT 1 FROM run_question_artifacts "
                        "WHERE run_id = :run_id AND question_key = :question_key "
                        "AND status = 'succeeded'"
                    ),
                    {"run_id": run_id, "question_key": question_key},
                )
                .mappings()
                .first()
            )
            if artifact is not None:
                return
            row = (
                conn.execute(
                    text(
                        "SELECT lease_token, status FROM reasoning_jobs "
                        "WHERE id = :id FOR UPDATE"
                    ),
                    {"id": job_id},
                )
                .mappings()
                .first()
            )
            if row is None:
                return
            if str(row["lease_token"]) != lease_token:
                return
            if str(row["status"]) != "claimed":
                return
            conn.execute(
                text(
                    "UPDATE reasoning_jobs SET status = 'failed', "
                    "failure_details = CAST(:failure_details AS jsonb), "
                    "updated_at = now() WHERE id = :id"
                ),
                {
                    "failure_details": json.dumps(
                        {"code": code, "error": "failed"}, sort_keys=True
                    ),
                    "id": job_id,
                },
            )
            conn.execute(
                text(
                    "UPDATE runs SET status = 'failed', updated_at = now() "
                    "WHERE id = :id"
                ),
                {"id": run_id},
            )
    except Exception:
        pass


def _claimed_result(claim: Any, attempt_index: Any) -> dict[str, Any]:
    return {
        "claimed": True,
        "busy": False,
        "job_id": claim["job_id"],
        "run_id": claim["run_id"],
        "question_key": claim["question_key"],
        "lease_token": claim["lease_token"],
        "fencing_generation": claim.get("fencing_generation"),
        "lease_deadline": claim.get("lease_deadline"),
        "attempt_index": attempt_index,
    }


def run_once(
    *,
    database_url: str | None = None,
    provider_adapter: Callable[..., Any] | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    """Claim one job, run the provider outside the claim transaction.

    The lease stays ``claimed`` afterwards so heartbeats can extend it;
    each provider invocation records exactly one persisted attempt.
    """
    claim = queue_module.claim_next_job(worker_id=worker_id, database_url=database_url)
    if claim is None:
        return {
            "claimed": False,
            "busy": True,
            "job_id": None,
            "run_id": None,
            "question_key": None,
            "lease_token": None,
            "fencing_generation": None,
            "attempt_index": None,
        }
    if provider_adapter is not None:
        adapter: Callable[..., Any] = provider_adapter
        try:
            outcome = adapter(dict(claim))
        except Exception as exc:
            queue_module.record_attempt(
                str(claim["job_id"]),
                str(claim["lease_token"]),
                outcome=None,
                error_details={"error": repr(exc)},
                database_url=database_url,
            )
            raise
        attempt_index = queue_module.record_attempt(
            str(claim["job_id"]),
            str(claim["lease_token"]),
            outcome=outcome,
            database_url=database_url,
        )
        return _claimed_result(claim, attempt_index)
    from x_insight.reasoning import coordinator as coordinator_module

    try:
        outcome = coordinator_module.execute_claimed_question(
            dict(claim), database_url=database_url
        )
    except Exception as exc:
        queue_module.record_attempt(
            str(claim["job_id"]),
            str(claim["lease_token"]),
            outcome=None,
            error_details={"error": repr(exc)},
            database_url=database_url,
        )
        _record_question_failure(dict(claim), exc)
        raise
    attempt_index = queue_module.record_attempt(
        str(claim["job_id"]),
        str(claim["lease_token"]),
        outcome=outcome,
        database_url=database_url,
    )
    return _claimed_result(claim, attempt_index)
