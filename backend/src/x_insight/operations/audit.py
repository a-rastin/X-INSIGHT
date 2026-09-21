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
