"""Author-owned draft persistence (S07 slice 1: GET/PATCH with revisions)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from x_insight import db
from x_insight.contracts import parse_if_match, to_utc_z
from x_insight.identity.routes import _check_csrf, _request_id, _require_session
from x_insight.operations.audit import record_audit

router = APIRouter()


class DraftPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_data: dict[str, Any]


class DiscardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool

    def check_confirmed(self) -> None:
        if self.confirm is not True:
            raise HTTPException(422, "Explicit discard confirmation is required.")


def _payload(row: Any) -> dict[str, Any]:
    data = dict(row)
    return {
        "schema_version": 1,
        "encounter": {
            "id": str(data["id"]),
            "patient_id": str(data["patient_id"]),
            "kind": data["kind"],
            "author_id": str(data["author_id"]) if data["author_id"] else None,
            "state": data["state"],
            "revision": data["revision"],
            "draft_data": data.get("draft_data") or {},
            "created_at": to_utc_z(data["created_at"]),
            "updated_at": to_utc_z(data["updated_at"]),
        },
    }


def _get_encounter(conn: Any, encounter_id: UUID) -> Any:
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
    return row


@router.get("/patients/{patient_id}/encounters")
def list_encounters(patient_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        denied, _actor = _require_session(request, conn)
        if denied is not None:
            return denied
        rows = (
            conn.execute(
                text(
                    "SELECT * FROM encounters WHERE patient_id = :pid "
                    "ORDER BY created_at, id"
                ),
                {"pid": str(patient_id)},
            )
            .mappings()
            .all()
        )
        return JSONResponse(
            {
                "schema_version": 1,
                "items": [_payload(r)["encounter"] for r in rows],
            },
            headers={"Cache-Control": "private, no-store"},
        )


@router.get("/encounters/{encounter_id}")
def get_encounter(encounter_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        denied, _actor = _require_session(request, conn)
        if denied is not None:
            return denied
        row = _get_encounter(conn, encounter_id)
        payload = _payload(row)
        return JSONResponse(
            payload,
            headers={
                "ETag": f'"{row["revision"]}"',
                "Cache-Control": "private, no-store",
            },
        )


@router.patch("/encounters/{encounter_id}")
def patch_encounter(
    encounter_id: UUID, body: DraftPatch, request: Request
) -> JSONResponse:
    with db.transaction() as conn:
        denied, actor = _require_session(request, conn)
        if denied is not None:
            return denied
        csrf_denied = _check_csrf(request, actor)
        if csrf_denied is not None:
            return csrf_denied
        row = (
            conn.execute(
                text("SELECT * FROM encounters WHERE id = :id FOR UPDATE"),
                {"id": str(encounter_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(404, "Encounter not found.")
        # Author-only mutation; shared reads stay allowed (FR-22).
        if str(row["author_id"]) != str(actor["user_id"]):
            raise HTTPException(403, "Only the draft author may edit.")
        if parse_if_match(request.headers) != str(row["revision"]):
            raise HTTPException(
                412, "The draft changed. Reload and reconcile your edits."
            )
        if row["state"] != "draft":
            raise HTTPException(409, "Only draft encounters can be edited.")
        patient = (
            conn.execute(
                text("SELECT archived FROM patients WHERE id = :id"),
                {"id": str(row["patient_id"])},
            )
            .mappings()
            .first()
        )
        if patient is not None and patient["archived"]:
            raise HTTPException(409, "Archived patient drafts are read-only.")
        updated = (
            conn.execute(
                text(
                    "UPDATE encounters SET draft_data = CAST(:data AS jsonb), "
                    " revision = revision + 1, updated_at = now() "
                    "WHERE id = :id RETURNING *"
                ),
                {"id": str(encounter_id), "data": json.dumps(body.draft_data)},
            )
            .mappings()
            .one()
        )
        record_audit(
            conn,
            operation="encounter.update",
            actor_id=str(actor["user_id"]),
            request_id=_request_id(request),
            result_reference=str(updated["id"]),
            target_display=str(updated["patient_id"]),
        )
        payload = _payload(updated)
        return JSONResponse(
            payload,
            headers={
                "ETag": f'"{updated["revision"]}"',
                "Cache-Control": "private, no-store",
            },
        )


@router.post("/encounters/{encounter_id}/discard")
def discard_encounter(
    encounter_id: UUID, body: DiscardRequest, request: Request
) -> JSONResponse:
    """Explicit author-confirmed discard (S07 slice 4).

    Requires If-Match current revision + {"confirm": true}. Sets
    state=discarded, bumps revision, retains the row + draft_data as an
    audit tombstone; the patient row is untouched. No jobs exist yet, so
    jobs cancellation is a no-op (S51 integrates real cancellation).
    """
    body.check_confirmed()
    with db.transaction() as conn:
        denied, actor = _require_session(request, conn)
        if denied is not None:
            return denied
        csrf_denied = _check_csrf(request, actor)
        if csrf_denied is not None:
            return csrf_denied
        row = (
            conn.execute(
                text("SELECT * FROM encounters WHERE id = :id FOR UPDATE"),
                {"id": str(encounter_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(404, "Encounter not found.")
        if str(row["author_id"]) != str(actor["user_id"]):
            raise HTTPException(403, "Only the draft author may discard.")
        if parse_if_match(request.headers) != str(row["revision"]):
            raise HTTPException(
                412, "The draft changed. Reload and reconcile your edits."
            )
        if row["state"] != "draft":
            raise HTTPException(409, "Only draft encounters can be discarded.")
        discarded = (
            conn.execute(
                text(
                    "UPDATE encounters SET state = 'discarded', "
                    " revision = revision + 1, updated_at = now() "
                    "WHERE id = :id RETURNING *"
                ),
                {"id": str(encounter_id)},
            )
            .mappings()
            .one()
        )
        record_audit(
            conn,
            operation="encounter.discard",
            actor_id=str(actor["user_id"]),
            request_id=_request_id(request),
            result_reference=str(discarded["id"]),
            target_display=str(discarded["patient_id"]),
        )
        return JSONResponse(
            _payload(discarded),
            headers={
                "ETag": f'"{discarded["revision"]}"',
                "Cache-Control": "private, no-store",
            },
        )
