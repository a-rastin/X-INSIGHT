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
from x_insight.assessments.diagnosis import evaluate_diagnosis
from x_insight.contracts import content_hash, parse_if_match, to_utc_z, utc_now
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


_STAMPED_ACK_KEYS = frozenset(
    {"actor_id", "acknowledged_at", "assessed_revision", "answers_hash"}
)


_STAMPED_BYPASS_KEYS = frozenset(
    {"actor_id", "bypassed_at", "status", "assessed_revision"}
)


def _apply_diagnosis_ack(
    incoming: dict[str, Any],
    stored: dict[str, Any],
    actor_id: str,
    new_revision: int,
) -> dict[str, Any]:
    """Apply S09 slice 3-4 ack/bypass semantics to the autosave payload (PATCH only).

    Bypass contract (slice 4, minimal): client requests with
    ``{"bypass": {"confirm": True}}`` only; server stamps exactly
    ``{actor_id, bypassed_at, status, assessed_revision}`` (no reason, no
    hash). Any other bypass value is 422. Bypass takes precedence over
    warning_ack: when bypass is active (freshly stamped or preserved),
    warning_ack is cleared to None since bypassed status is distinct from
    completion. Bypass persists across GET and across later answer edits
    that omit the bypass key; clearing requires explicit ``bypass: None``.
    """
    if "diagnosis" not in incoming:
        return incoming
    diag = incoming["diagnosis"]
    if not isinstance(diag, dict):
        raise HTTPException(422, "Invalid diagnosis content.")
    answers = diag.get("answers")
    if not isinstance(answers, dict):
        raise HTTPException(422, "Invalid diagnosis content.")
    stored_diag = stored.get("diagnosis") if isinstance(stored, dict) else None
    if "bypass" in diag:
        incoming_bypass = diag["bypass"]
        if incoming_bypass is None:
            new_bypass: dict[str, Any] | None = None
        elif (
            isinstance(incoming_bypass, dict)
            and set(incoming_bypass.keys()) == {"confirm"}
            and incoming_bypass.get("confirm") is True
        ):
            new_bypass = {
                "actor_id": actor_id,
                "bypassed_at": to_utc_z(utc_now()),
                "status": "bypassed",
                "assessed_revision": new_revision,
            }
        else:
            raise HTTPException(422, "Invalid diagnosis bypass.")
    else:
        stored_bypass = (
            stored_diag.get("bypass") if isinstance(stored_diag, dict) else None
        )
        if (
            isinstance(stored_bypass, dict)
            and set(stored_bypass.keys()) == set(_STAMPED_BYPASS_KEYS)
            and stored_bypass.get("status") == "bypassed"
        ):
            new_bypass = stored_bypass
        else:
            new_bypass = None
    if new_bypass is not None:
        out = dict(diag)
        out["bypass"] = new_bypass
        out["warning_ack"] = None
        updated = dict(incoming)
        updated["diagnosis"] = out
        return updated
    if "warning_ack" in diag and diag["warning_ack"] is not None:
        ack = diag["warning_ack"]
        if (
            not isinstance(ack, dict)
            or set(ack.keys()) != {"confirm"}
            or ack.get("confirm") is not True
        ):
            raise HTTPException(422, "Invalid diagnosis acknowledgement.")
        try:
            result = evaluate_diagnosis(answers)
        except ValueError as exc:
            raise HTTPException(422, "Invalid diagnosis acknowledgement.") from exc
        complete = result.get("status") == "complete"
        below = result.get("threshold_met") is False
        if not (complete and below):
            raise HTTPException(422, "Invalid diagnosis acknowledgement.")
        stamped = {
            "actor_id": actor_id,
            "acknowledged_at": to_utc_z(utc_now()),
            "assessed_revision": new_revision,
            "answers_hash": content_hash(answers),
        }
        out = dict(diag)
        out["warning_ack"] = stamped
        out["bypass"] = None
        updated = dict(incoming)
        updated["diagnosis"] = out
        return updated
    if (
        isinstance(stored_diag, dict)
        and isinstance(stored_diag.get("answers"), dict)
        and stored_diag["answers"] == answers
        and isinstance(stored_diag.get("warning_ack"), dict)
        and set(stored_diag["warning_ack"].keys()) == set(_STAMPED_ACK_KEYS)
    ):
        out = dict(diag)
        out["warning_ack"] = stored_diag["warning_ack"]
        out["bypass"] = None
        updated = dict(incoming)
        updated["diagnosis"] = out
        return updated
    out = dict(diag)
    out["warning_ack"] = None
    out["bypass"] = None
    updated = dict(incoming)
    updated["diagnosis"] = out
    return updated


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
        stored_draft = row["draft_data"] if isinstance(row["draft_data"], dict) else {}
        new_draft = _apply_diagnosis_ack(
            dict(body.draft_data),
            stored_draft,
            str(actor["user_id"]),
            int(row["revision"]) + 1,
        )
        updated = (
            conn.execute(
                text(
                    "UPDATE encounters SET draft_data = CAST(:data AS jsonb), "
                    " revision = revision + 1, updated_at = now() "
                    "WHERE id = :id RETURNING *"
                ),
                {"id": str(encounter_id), "data": json.dumps(new_draft)},
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
