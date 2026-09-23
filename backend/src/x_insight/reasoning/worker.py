"""Single-question worker step (S44 slices 2-4: claim + attempt outside txn)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from x_insight.reasoning import queue as queue_module


def _default_adapter(job: dict[str, Any]) -> dict[str, Any]:
    _ = job
    return {"ok": True}


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
    adapter: Callable[..., Any] = provider_adapter or _default_adapter
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
