"""Safe operational metrics collector (S58 item 3, T1).

Reads real PostgreSQL state inside the caller's transaction plus the
local backup-staging filesystem. Returns counts/ages/status only; never
clinical payloads, secrets, or tracebacks.

Sources (all real tables, zero when absent, never fabricated):
- queue age: oldest eligible ``reasoning_jobs`` row (queued or reclaimable
  claimed with ``available_at`` due), mirroring ``queue.claim_next_job``.
- heartbeat: ``MAX(reasoning_jobs.last_heartbeat)``; missing when never seen
  or older than :data:`HEARTBEAT_MISSING_SECONDS`.
- provider retries: ``reasoning_attempts`` rows with ``attempt_index > 1``.
- provider auth failures: ``reasoning_jobs.failure_details`` auth codes plus
  ``reasoning_attempts`` auth text plus ``audit_events`` provider capability
  tests with ``credential_ok = false``.
- inference limit rejections: ``audit_events`` admission refusals
  (``network.validate`` with ``admitted = false``) plus job/attempt rows
  carrying inference/resource/limit text. Zero-backed until S47 counters
  land; the query shape is real and documented here.
- disk: ``shutil.disk_usage`` of the backup staging directory filesystem
  (single-host deployment; the database volume shares this filesystem).
- backup: latest ``recovery_jobs`` row with ``kind = 'backup`` and
  ``status = 'succeeded'``; ``("none")`` when never succeeded.
- saves: honest zero; no dedicated save-failure ledger exists yet (S47
  counters pending). Failed mutations raise without an audit success row,
  so there is no failure ledger to count.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from x_insight.contracts import to_utc_z
from x_insight.operations import backup

HEARTBEAT_MISSING_SECONDS = 120
QUEUE_AGE_SECONDS = 300
DISK_HIGH_PERCENT = 80
PROVIDER_AUTH_FAILURE_THRESHOLD = 2


def queue_oldest_eligible_age_seconds(conn: Connection) -> float | None:
    """Return the age in seconds of the oldest eligible job, or None."""
    value = conn.execute(
        text(
            "SELECT EXTRACT(EPOCH FROM (now() - MIN(created_at))) "
            "FROM reasoning_jobs "
            "WHERE (status = 'queued' OR "
            "(status = 'claimed' AND lease_deadline <= now())) "
            "AND (available_at IS NULL OR available_at <= now())"
        )
    ).scalar()
    if value is None:
        return None
    age = float(value)
    if age < 0:
        return 0.0
    return age


def heartbeat_status(conn: Connection) -> tuple[bool, float | None]:
    """Return (missing, age_seconds) from the latest job heartbeat."""
    value = conn.execute(
        text(
            "SELECT EXTRACT(EPOCH FROM (now() - MAX(last_heartbeat))) "
            "FROM reasoning_jobs WHERE last_heartbeat IS NOT NULL"
        )
    ).scalar()
    if value is None:
        return True, None
    age = float(value)
    if age < 0:
        age = 0.0
    return age > HEARTBEAT_MISSING_SECONDS, age


def provider_retries(conn: Connection) -> int:
    """Count retry attempts (attempt_index beyond the first try)."""
    value = conn.execute(
        text("SELECT COUNT(*) FROM reasoning_attempts WHERE attempt_index > 1")
    ).scalar()
    return int(value or 0)


def provider_auth_failures(conn: Connection) -> int:
    """Count real auth-failure signals across jobs, attempts, and tests."""
    jobs_auth = conn.execute(
        text(
            "SELECT COUNT(*) FROM reasoning_jobs "
            "WHERE failure_details->>'code' ILIKE '%auth%'"
        )
    ).scalar()
    attempts_auth = conn.execute(
        text(
            "SELECT COUNT(*) FROM reasoning_attempts "
            "WHERE error_details::text ILIKE '%auth%' "
            "OR outcome ILIKE '%auth%'"
        )
    ).scalar()
    credential_tests = conn.execute(
        text(
            "SELECT COUNT(*) FROM audit_events "
            "WHERE operation = 'provider.config.test' "
            "AND result_payload->>'credential_ok' = 'false'"
        )
    ).scalar()
    return int(jobs_auth or 0) + int(attempts_auth or 0) + int(credential_tests or 0)


def inference_limit_rejections(conn: Connection) -> int:
    """Count real admission/inference limit signals; zero when absent."""
    admission = conn.execute(
        text(
            "SELECT COUNT(*) FROM audit_events "
            "WHERE operation = 'network.validate' "
            "AND details->>'admitted' = 'false'"
        )
    ).scalar()
    jobs = conn.execute(
        text(
            "SELECT COUNT(*) FROM reasoning_jobs WHERE "
            "failure_details->>'code' ILIKE '%inference%' "
            "OR failure_details->>'code' ILIKE '%resource%' "
            "OR failure_details->>'code' ILIKE '%limit%' "
            "OR failure_details->>'code' ILIKE '%admission%' "
            "OR failure_details->>'code' ILIKE '%oversized%' "
            "OR failure_details->>'code' ILIKE '%budget_exceeded%'"
        )
    ).scalar()
    attempts = conn.execute(
        text(
            "SELECT COUNT(*) FROM reasoning_attempts WHERE "
            "error_details::text ILIKE '%inference%' "
            "OR error_details::text ILIKE '%resource%' "
            "OR error_details::text ILIKE '%limit%' "
            "OR outcome ILIKE '%inference%' "
            "OR outcome ILIKE '%resource%'"
        )
    ).scalar()
    return int(admission or 0) + int(jobs or 0) + int(attempts or 0)


def disk_usage() -> tuple[float, str]:
    """Return (usage_percent, staging_path) for the backup filesystem."""
    staging = backup.staging_dir()
    probe = staging
    if not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent and os.path.exists(parent):
            probe = parent
        elif os.path.exists("/tmp"):
            probe = "/tmp"
        else:
            probe = "/"
    try:
        usage = shutil.disk_usage(probe)
    except OSError:
        return 0.0, staging
    total = float(usage.total) if usage.total else 0.0
    if total <= 0:
        return 0.0, staging
    percent = float(usage.used) / total * 100.0
    if percent < 0.0:
        percent = 0.0
    if percent > 100.0:
        percent = 100.0
    return percent, staging


def backup_status(conn: Connection) -> tuple[str | None, str]:
    """Return (last_success_at, status) for the latest succeeded backup."""
    row = (
        conn.execute(
            text(
                "SELECT status, completed_at FROM recovery_jobs "
                "WHERE kind = 'backup' AND status = 'succeeded' "
                "ORDER BY completed_at DESC NULLS LAST, "
                "created_at DESC LIMIT 1"
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None, "none"
    status = str(row["status"])
    completed = row["completed_at"]
    if completed is None:
        return None, status
    return to_utc_z(completed), status


def save_failures() -> int:
    """Return the save-failure count (honest zero: no ledger yet)."""
    return 0


def collect_metrics(conn: Connection) -> dict[str, Any]:
    """Collect the safe ops-metrics payload inside the caller's transaction."""
    queue_age = queue_oldest_eligible_age_seconds(conn)
    missing, heartbeat_age = heartbeat_status(conn)
    retries = provider_retries(conn)
    auth_failures = provider_auth_failures(conn)
    limit_rejections = inference_limit_rejections(conn)
    usage_percent, staging_path = disk_usage()
    last_success_at, backup_state = backup_status(conn)
    failures = save_failures()
    alerts: dict[str, bool] = {
        "missing_heartbeat": missing,
        "queue_age_exceeded": queue_age is not None and queue_age > QUEUE_AGE_SECONDS,
        "provider_auth_failure": auth_failures >= PROVIDER_AUTH_FAILURE_THRESHOLD,
        "disk_high": usage_percent > DISK_HIGH_PERCENT,
    }
    return {
        "schema_version": 1,
        "queue": {"oldest_eligible_age_seconds": queue_age},
        "heartbeat": {
            "missing": missing,
            "last_heartbeat_age_seconds": heartbeat_age,
        },
        "provider": {"retries": retries, "auth_failures": auth_failures},
        "inference": {"limit_rejections": limit_rejections},
        "disk": {"usage_percent": usage_percent, "path": staging_path},
        "backup": {"last_success_at": last_success_at, "status": backup_state},
        "saves": {"failures": failures},
        "alerts": alerts,
    }
