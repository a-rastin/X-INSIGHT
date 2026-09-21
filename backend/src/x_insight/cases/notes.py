"""Attributed page notes (S13). Append-only; separate table, never draft_data."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from x_insight import db
from x_insight.contracts import canonical_json, parse_idempotency_key, to_utc_z
from x_insight.identity.hashing import hash_password, verify_password
from x_insight.identity.routes import _check_csrf, _request_id, _require_session
from x_insight.operations.audit import record_audit

router = APIRouter()
ANALYSIS_EXCLUDED_TOP_LEVEL_KEYS = frozenset({"notes"})


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    page: str
    text: str


def _payload(row: Any) -> dict[str, Any]:
    d = dict(row)
    return {
        "id": str(d["id"]),
        "encounter_id": str(d["encounter_id"]),
        "page": d["page"],
        "text": d["text"],
        "author_id": str(d["author_id"]),
        "author_display": d["author_display"],
        "created_at": to_utc_z(d["created_at"]),
    }


def project_encounter_for_analysis(
    draft: dict[str, Any],
) -> dict[str, Any]:
    return {k: v for k, v in draft.items() if k not in ANALYSIS_EXCLUDED_TOP_LEVEL_KEYS}


@router.post("/encounters/{encounter_id}/notes")
def create_note(encounter_id: UUID, body: NoteCreate, request: Request) -> JSONResponse:
    page = body.page.strip()
    note_text = body.text.strip()
    if not page or not note_text:
        raise HTTPException(422, "Page and text are required.")
    with db.transaction() as conn:
        denied, actor = _require_session(request, conn)
        if denied is not None:
            return denied
        csrf = _check_csrf(request, actor)
        if csrf is not None:
            return csrf
        row = (
            conn.execute(
                text("SELECT * FROM encounters WHERE id = :id"),
                {"id": str(encounter_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(404, "Encounter not found.")
        if str(row["author_id"]) != str(actor["user_id"]):
            raise HTTPException(403, "Only the draft author may add notes.")
        actor_id = str(actor["user_id"])
        key = parse_idempotency_key(request.headers)
        scope = {
            "actor_id": actor_id,
            "operation": "encounter.note.add",
            "idempotency_key": key,
            "encounter_id": str(encounter_id),
        }
        fingerprint = canonical_json(
            {"page": page, "text": note_text, "encounter_id": str(encounter_id)}
        ).decode()
        if key is not None:
            conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
                {"scope": canonical_json(scope).decode()},
            )
            saved = (
                conn.execute(
                    text(
                        "SELECT request_hash, result_payload, "
                        "result_status FROM audit_events "
                        "WHERE actor_id = :actor_id "
                        "AND operation = :operation "
                        "AND idempotency_key = :idempotency_key "
                        "AND result_reference = :encounter_id"
                    ),
                    scope,
                )
                .mappings()
                .first()
            )
            if saved is not None:
                if not verify_password(fingerprint, str(saved["request_hash"])):
                    raise HTTPException(
                        409, "Idempotency key was used for another request."
                    )
                return JSONResponse(
                    status_code=int(saved["result_status"] or 201),
                    content=saved["result_payload"],
                )
        username = str(actor["username"])
        created = (
            conn.execute(
                text(
                    "INSERT INTO encounter_notes "
                    "(encounter_id, page, text, author_id, author_display) "
                    "VALUES (:eid, :page, :text, :aid, :adisp) RETURNING *"
                ),
                {
                    "eid": str(encounter_id),
                    "page": page,
                    "text": note_text,
                    "aid": actor_id,
                    "adisp": username,
                },
            )
            .mappings()
            .one()
        )
        result: dict[str, Any] = {"schema_version": 1, "note": _payload(created)}
        if key is not None:
            record_audit(
                conn,
                operation="encounter.note.add",
                actor_id=actor_id,
                idempotency_key=key,
                request_hash=hash_password(fingerprint),
                result_reference=str(encounter_id),
                request_id=_request_id(request),
                target_display=str(row["patient_id"]),
                result_payload=result,
                result_status=201,
            )
        else:
            record_audit(
                conn,
                operation="encounter.note.add",
                actor_id=actor_id,
                request_id=_request_id(request),
                result_reference=str(created["id"]),
                target_display=str(row["patient_id"]),
            )
        return JSONResponse(status_code=201, content=result)


@router.get("/encounters/{encounter_id}/notes")
def list_notes(encounter_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        denied, _a = _require_session(request, conn)
        if denied is not None:
            return denied
        exists = conn.execute(
            text("SELECT id FROM encounters WHERE id = :id"), {"id": str(encounter_id)}
        ).first()
        if exists is None:
            raise HTTPException(404, "Encounter not found.")
        rows = (
            conn.execute(
                text(
                    "SELECT * FROM encounter_notes "
                    "WHERE encounter_id = :id ORDER BY created_at, id"
                ),
                {"id": str(encounter_id)},
            )
            .mappings()
            .all()
        )
        return JSONResponse(
            {"schema_version": 1, "items": [_payload(r) for r in rows]},
            headers={"Cache-Control": "private, no-store"},
        )
