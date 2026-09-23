"""Transaction-scoped audit insertion.

Call inside the caller's transaction (see db.transaction) so the domain
mutation and its audit row commit or roll back together. No separate commit
here; no generic repository layer.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session


def record_audit(
    conn: Connection | Session,
    *,
    operation: str,
    actor_id: str | None = None,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
    result_reference: str | None = None,
    request_id: str | None = None,
    target_display: str | None = None,
    details: dict[str, Any] | None = None,
    result_payload: dict[str, Any] | None = None,
    result_status: int | None = None,
) -> str:
    """Insert one audit event in the ambient transaction; return its ID."""
    row = conn.execute(
        text(
            "INSERT INTO audit_events "
            "(actor_id, operation, idempotency_key, request_hash, "
            " result_reference, request_id, actor_display, target_display, details, "
            " result_payload, result_status) "
            "VALUES (:actor_id, :operation, :idempotency_key, :request_hash, "
            " :result_reference, :request_id, "
            " (SELECT username FROM users WHERE id::text = :actor_id), "
            " :target_display, CAST(:details AS jsonb), CAST(:payload AS jsonb), "
            " :status) RETURNING id"
        ),
        {
            "actor_id": actor_id,
            "operation": operation,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "result_reference": result_reference,
            "request_id": request_id,
            "target_display": target_display,
            "details": json.dumps(details or {}),
            "payload": json.dumps(result_payload)
            if result_payload is not None
            else None,
            "status": result_status,
        },
    ).scalar_one()
    return str(row)


# --- Recovery event hooks (S54–S56) ---
# S54–S56 will emit these operations via `record_audit` at their own
# transaction/command paths, under the same atomicity rule as above (audit
# row commits or rolls back together with the domain mutation). NO route
# emits them yet.
BACKUP_CREATE = "backup.create"
BACKUP_DOWNLOAD = "backup.download"
RESTORE_VALIDATE = "restore.validate"
RESTORE_COMMIT = "restore.commit"
RECOVERY_OPERATIONS = (
    BACKUP_CREATE,
    BACKUP_DOWNLOAD,
    RESTORE_VALIDATE,
    RESTORE_COMMIT,
)

# Plan §10.1 audit inventory as actually implemented (operation -> producer).
# Recovery entries are reserved constants only (S54–S56, not yet emitted);
# exports.* entries are S53-owned (not yet emitted).
REQUIRED_AUDIT_COVERAGE: dict[str, str] = {
    "auth.login_success": "identity/routes.py",
    "auth.login_failure": "identity/routes.py",
    "auth.logout": "identity/routes.py",
    "auth.password_change": "identity/routes.py",
    "physician.create": "identity/accounts.py",
    "physician.edit": "identity/accounts.py",
    "physician.deactivate": "identity/accounts.py",
    "physician.reactivate": "identity/accounts.py",
    "patient.create": "cases/patients.py",
    "patient.update": "cases/patients.py",
    "patient.archive": "cases/patients.py",
    "patient.unarchive": "cases/patients.py",
    "encounter.update": "cases/encounters.py",
    "encounter.discard": "cases/encounters.py",
    "encounter.followup_create": "cases/encounters.py",
    "encounter.note.add": "cases/notes.py",
    "encounter.secondary_plan.save": "cases/signing.py",
    "encounter.sign": "cases/signing.py",
    "encounter.addendum": "cases/signing.py",
    "run.start": "reasoning/runs.py",
    "run.retry": "reasoning/runs.py",
    "provider.config.save": "reasoning/routes.py",
    "provider.config.test": "reasoning/routes.py",
    "provider.config.delete": "reasoning/routes.py",
    "network.import": "models/routes.py",
    "network.version": "models/routes.py",
    "network.validate": "models/routes.py",
    "model_bundle.activate": "models/routes.py",
    "model_bundle.rollback": "models/routes.py",
    # S54–S56, not yet emitted:
    BACKUP_CREATE: "recovery/backup.py",
    BACKUP_DOWNLOAD: "recovery/backup.py",
    RESTORE_VALIDATE: "recovery/restore.py",
    RESTORE_COMMIT: "recovery/restore.py",
    # S53-owned, not yet emitted:
    # "exports.*": "cases/exports.py",
}


def verify_audit_append_only(conn: Connection | Session) -> dict[str, Any]:
    """Inspect (never write) the audit append-only guard; report its state."""
    trigger = conn.execute(
        text(
            "SELECT tgname FROM pg_trigger WHERE tgrelid = "
            "'audit_events'::regclass AND tgname = "
            "'audit_events_append_only' AND NOT tgisinternal"
        )
    ).scalar()
    if trigger is not None:
        return {"append_only": True, "mechanism": f"trigger:{trigger}"}
    return {"append_only": False, "mechanism": "none"}
