"""Single-question worker step (S44 slices 2-4: claim + attempt outside txn).

S45 slice 1: when no explicit ``provider_adapter`` is passed, the claimed
job runs through the real coordinator (MCP + controlled provider +
inference); an explicitly passed adapter keeps the S44 compat path.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import text

from x_insight import db
from x_insight.reasoning import queue as queue_module

logger = logging.getLogger(__name__)


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


def main(argv: list[str] | None = None) -> int:
    """Worker entrypoint for ``python -m x_insight.reasoning.worker``.

    Repeatedly claims queued jobs via :func:`run_once`; sleeps briefly
    when the queue is empty. Handles SIGTERM/SIGINT gracefully (exit 0).
    ``--once`` performs a single claim pass then exits.
    """
    parser = argparse.ArgumentParser(
        prog="python -m x_insight.reasoning.worker",
        description="X-INSIGHT reasoning worker: claim queued jobs via run_once().",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single worker claim pass then exit.",
    )
    parser.add_argument(
        "--worker-id",
        default=None,
        help="Worker identity recorded with queue claims.",
    )
    parser.add_argument(
        "--idle-seconds",
        type=float,
        default=2.0,
        help="Sleep between empty polls.",
    )
    args = parser.parse_args(argv)

    stop = {"flag": False}

    def _handle(*_args: Any) -> None:
        stop["flag"] = True

    try:
        signal.signal(signal.SIGTERM, _handle)
        signal.signal(signal.SIGINT, _handle)
    except Exception:
        pass

    if args.once:
        result = run_once(worker_id=args.worker_id)
        if result.get("claimed"):
            logger.info(
                "worker claimed job_id=%s run_id=%s",
                result.get("job_id"),
                result.get("run_id"),
            )
        return 0

    while not stop["flag"]:
        try:
            result = run_once(worker_id=args.worker_id)
        except KeyboardInterrupt:
            break
        except Exception:
            logger.exception("worker pass failed")
            if stop["flag"]:
                break
            time.sleep(args.idle_seconds)
            continue
        if stop["flag"]:
            break
        if result.get("claimed"):
            logger.info(
                "worker claimed job_id=%s run_id=%s",
                result.get("job_id"),
                result.get("run_id"),
            )
        else:
            time.sleep(args.idle_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
