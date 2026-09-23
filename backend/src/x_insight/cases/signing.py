"""Atomic secondary-plan saves and plan signing (S49 slice 1).

Slice 1 only: revisioned secondary-plan text that never mutates the
immutable initial proposal in ``run_proposals``, plus signing of a current
succeeded run with a minimal frozen snapshot. Slice 2 adds the
failed/partial run denial matrix, slice 3 hardens the full freeze and
post-sign immutability, slice 4 adds original-signer addenda.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictInt
from sqlalchemy import text

from x_insight import db
from x_insight.cases.encounters import _baseline_changed_for
from x_insight.cases.history import validate_history_reconciliation
from x_insight.contracts import (
    canonical_json,
    content_hash,
    parse_idempotency_key,
    parse_if_match,
    to_utc_z,
    utc_now,
)
from x_insight.identity.hashing import hash_password, verify_password
from x_insight.identity.routes import _check_csrf, _request_id, _require_session
from x_insight.operations.audit import record_audit
from x_insight.reasoning.runs import _compute_stale, _fetch_proposal

router = APIRouter()

_SAVE_OPERATION = "encounter.secondary_plan.save"
_SIGN_OPERATION = "encounter.sign"
_ADDENDUM_OPERATION = "encounter.addendum"

MAX_SECONDARY_PLAN_CHARS = 20000


class SecondaryPlanSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class SignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    encounter_revision: StrictInt
    run_id: UUID
    secondary_plan_revision: StrictInt
    review_acknowledgments: list[Any]
    baseline_acknowledgment: bool | None = None


class AddendumCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str
    correction_text: str


def _addendum_payload(row: Any) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": str(data["id"]),
        "encounter_id": str(data["encounter_id"]),
        "author_id": str(data["author_id"]) if data["author_id"] else None,
        "reason": str(data["reason"]) if data["reason"] is not None else None,
        "correction_text": str(data["correction_text"])
        if data["correction_text"] is not None
        else None,
        "created_at": to_utc_z(data["created_at"]),
    }


def _plan_entry(row: Any) -> dict[str, Any]:
    data = dict(row)
    return {
        "encounter_id": str(data["encounter_id"]),
        "revision": int(data["revision"]),
        "text": str(data["text"]),
        "author_id": str(data["author_id"]) if data["author_id"] else None,
        "created_at": to_utc_z(data["created_at"]),
    }


def _latest_plan(conn: Any, encounter_id: str) -> list[Any]:
    rows = (
        conn.execute(
            text(
                "SELECT * FROM secondary_plan_revisions WHERE encounter_id = :eid "
                "ORDER BY revision, id"
            ),
            {"eid": encounter_id},
        )
        .mappings()
        .all()
    )
    return list(rows)


def _encounter_payload(row: Any) -> dict[str, Any]:
    data = dict(row)
    baseline = data.get("baseline_encounter_id")
    return {
        "id": str(data["id"]),
        "patient_id": str(data["patient_id"]),
        "kind": data["kind"],
        "author_id": str(data["author_id"]) if data["author_id"] else None,
        "state": data["state"],
        "revision": data["revision"],
        "baseline_encounter_id": str(baseline) if baseline else None,
        "draft_data": data.get("draft_data") or {},
        "created_at": to_utc_z(data["created_at"]),
        "updated_at": to_utc_z(data["updated_at"]),
    }


@router.patch("/encounters/{encounter_id}/secondary-plan")
def save_secondary_plan(
    encounter_id: UUID, body: SecondaryPlanSave, request: Request
) -> JSONResponse:
    plan_text = body.text.strip()
    if not plan_text:
        raise HTTPException(422, "Secondary plan text is required.")
    if len(plan_text) > MAX_SECONDARY_PLAN_CHARS:
        raise HTTPException(422, "Secondary plan text is too long.")
    with db.transaction() as conn:
        denied, actor = _require_session(request, conn)
        if denied is not None:
            return denied
        csrf_denied = _check_csrf(request, actor)
        if csrf_denied is not None:
            return csrf_denied
        key = parse_idempotency_key(request.headers)
        if key is None:
            raise HTTPException(422, "A valid Idempotency-Key is required.")
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
        actor_id = str(actor["user_id"])
        if str(row["author_id"]) != actor_id:
            raise HTTPException(403, "Only the draft author may edit.")
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
        scope = {
            "actor_id": actor_id,
            "operation": _SAVE_OPERATION,
            "idempotency_key": key,
            "encounter_id": str(encounter_id),
        }
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": canonical_json(scope).decode()},
        )
        fingerprint = canonical_json(
            {"encounter_id": str(encounter_id), "text": plan_text}
        ).decode()
        saved = (
            conn.execute(
                text(
                    "SELECT request_hash, result_payload, result_status "
                    "FROM audit_events "
                    "WHERE actor_id = :actor_id AND operation = :operation "
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
            payload = saved["result_payload"]
            saved_plan: Any = (
                payload.get("secondary_plan", {}) if isinstance(payload, dict) else {}
            )
            revision = (
                saved_plan.get("revision", 0) if isinstance(saved_plan, dict) else 0
            )
            return JSONResponse(
                status_code=int(saved["result_status"] or 200),
                content=payload,
                headers={"ETag": f'"{revision}"'},
            )
        rows = _latest_plan(conn, str(encounter_id))
        latest = int(rows[-1]["revision"]) if rows else 0
        expected = parse_if_match(request.headers)
        if latest == 0:
            if expected is not None and expected != "0":
                raise HTTPException(
                    412, "The plan changed. Reload and reconcile your edits."
                )
        elif expected != str(latest):
            raise HTTPException(
                412, "The plan changed. Reload and reconcile your edits."
            )
        created = (
            conn.execute(
                text(
                    "INSERT INTO secondary_plan_revisions "
                    "(encounter_id, revision, text, author_id) VALUES (:eid, "
                    ":revision, :text, :author_id) RETURNING *"
                ),
                {
                    "eid": str(encounter_id),
                    "revision": latest + 1,
                    "text": plan_text,
                    "author_id": actor_id,
                },
            )
            .mappings()
            .one()
        )
        result: dict[str, Any] = {
            "schema_version": 1,
            "secondary_plan": {
                "encounter_id": str(encounter_id),
                "revision": int(created["revision"]),
                "text": str(created["text"]),
            },
        }
        record_audit(
            conn,
            operation=_SAVE_OPERATION,
            actor_id=actor_id,
            idempotency_key=key,
            request_hash=hash_password(fingerprint),
            result_reference=str(encounter_id),
            request_id=_request_id(request),
            target_display=str(row["patient_id"]),
            result_payload=result,
            result_status=200,
        )
        return JSONResponse(
            status_code=200,
            content=result,
            headers={
                "ETag": f'"{created["revision"]}"',
                "Cache-Control": "private, no-store",
            },
        )


@router.get("/encounters/{encounter_id}/secondary-plan")
def read_secondary_plan(encounter_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        denied, _actor = _require_session(request, conn)
        if denied is not None:
            return denied
        exists = conn.execute(
            text("SELECT id FROM encounters WHERE id = :id"),
            {"id": str(encounter_id)},
        ).first()
        if exists is None:
            raise HTTPException(404, "Encounter not found.")
        rows = _latest_plan(conn, str(encounter_id))
        history = [_plan_entry(item) for item in rows]
        if history:
            current = history[-1]
            payload: dict[str, Any] = {
                "schema_version": 1,
                "secondary_plan": {
                    "encounter_id": str(encounter_id),
                    "revision": current["revision"],
                    "text": current["text"],
                    "history": history,
                },
                "current": {
                    "encounter_id": str(encounter_id),
                    "revision": current["revision"],
                    "text": current["text"],
                },
                "history": history,
            }
            etag = f'"{current["revision"]}"'
        else:
            payload = {
                "schema_version": 1,
                "secondary_plan": None,
                "current": None,
                "history": [],
            }
            etag = '"0"'
        return JSONResponse(
            payload,
            headers={"ETag": etag, "Cache-Control": "private, no-store"},
        )


@router.get("/encounters/{encounter_id}/signed-snapshot")
def read_signed_snapshot(encounter_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        denied, _actor = _require_session(request, conn)
        if denied is not None:
            return denied
        exists = conn.execute(
            text("SELECT id FROM encounters WHERE id = :id"),
            {"id": str(encounter_id)},
        ).first()
        if exists is None:
            raise HTTPException(404, "Encounter not found.")
        row = (
            conn.execute(
                text(
                    "SELECT snapshot, snapshot_hash FROM signed_snapshots "
                    "WHERE encounter_id = :eid"
                ),
                {"eid": str(encounter_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(404, "Signed snapshot not found.")
        stored = row["snapshot"]
        frozen = dict(stored) if isinstance(stored, dict) else {}
        if "snapshot_hash" not in frozen:
            frozen["snapshot_hash"] = str(row["snapshot_hash"])
        return JSONResponse(
            {"schema_version": 1, "signed_snapshot": frozen},
            headers={"Cache-Control": "private, no-store"},
        )


@router.post("/encounters/{encounter_id}/sign")
async def sign_encounter(encounter_id: UUID, request: Request) -> JSONResponse:
    try:
        raw = await request.json()
    except Exception as exc:
        raise HTTPException(422, "Invalid request body.") from exc
    try:
        body = SignRequest.model_validate(raw)
    except Exception as exc:
        raise HTTPException(422, "Invalid sign request.") from exc
    with db.transaction() as conn:
        denied, actor = _require_session(request, conn)
        if denied is not None:
            return denied
        csrf_denied = _check_csrf(request, actor)
        if csrf_denied is not None:
            return csrf_denied
        key = parse_idempotency_key(request.headers)
        if key is None:
            raise HTTPException(422, "A valid Idempotency-Key is required.")
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
        actor_id = str(actor["user_id"])
        scope = {
            "actor_id": actor_id,
            "operation": _SIGN_OPERATION,
            "idempotency_key": key,
            "encounter_id": str(encounter_id),
        }
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": canonical_json(scope).decode()},
        )
        fingerprint = canonical_json(
            {
                "encounter_id": str(encounter_id),
                "encounter_revision": int(body.encounter_revision),
                "run_id": str(body.run_id),
                "secondary_plan_revision": int(body.secondary_plan_revision),
                "review_acknowledgments": body.review_acknowledgments,
                "baseline_acknowledgment": body.baseline_acknowledgment,
            }
        ).decode()
        saved = (
            conn.execute(
                text(
                    "SELECT request_hash, result_payload, result_status "
                    "FROM audit_events "
                    "WHERE actor_id = :actor_id AND operation = :operation "
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
        if actor["role"] != "physician":
            raise HTTPException(403, "Physician access required.")
        if str(row["author_id"]) != actor_id:
            raise HTTPException(403, "Only the draft author may sign.")
        patient = (
            conn.execute(
                text("SELECT * FROM patients WHERE id = :id"),
                {"id": str(row["patient_id"])},
            )
            .mappings()
            .first()
        )
        if patient is not None and patient["archived"]:
            raise HTTPException(409, "Archived patient drafts are read-only.")
        if patient is None:
            raise HTTPException(404, "Encounter not found.")
        if row["state"] not in ("draft", "review_ready"):
            raise HTTPException(409, "Only draft encounters can be signed.")
        current_revision = int(row["revision"])
        if (
            parse_if_match(request.headers) != str(current_revision)
            or int(body.encounter_revision) != current_revision
        ):
            raise HTTPException(
                412, "The draft changed. Reload and reconcile your edits."
            )
        plan_rows = _latest_plan(conn, str(encounter_id))
        latest_plan = int(plan_rows[-1]["revision"]) if plan_rows else 0
        if int(body.secondary_plan_revision) != latest_plan:
            raise HTTPException(409, "The secondary plan changed. Reload it.")
        secondary_text = str(plan_rows[-1]["text"]) if plan_rows else None
        run = (
            conn.execute(
                text("SELECT * FROM runs WHERE id = :id"),
                {"id": str(body.run_id)},
            )
            .mappings()
            .first()
        )
        if run is None:
            raise HTTPException(404, "Run not found.")
        if str(run["encounter_id"]) != str(encounter_id):
            raise HTTPException(409, "The run does not belong to this encounter.")
        if str(run["status"]) != "succeeded":
            raise HTTPException(409, "Only a succeeded run can be signed.")
        proposal = (
            conn.execute(
                text("SELECT status FROM run_proposals WHERE run_id = :run_id"),
                {"run_id": str(body.run_id)},
            )
            .mappings()
            .first()
        )
        if proposal is None or str(proposal["status"]) != "succeeded":
            raise HTTPException(409, "Only a succeeded proposal can be signed.")
        if _compute_stale(conn, run):
            raise HTTPException(
                409,
                "The run is stale. Start a new run from the current draft.",
            )
        if not isinstance(body.review_acknowledgments, list):
            raise HTTPException(422, "Review acknowledgments must be a list.")
        if row["kind"] == "follow_up":
            if body.baseline_acknowledgment is not True:
                raise HTTPException(409, "Baseline reconciliation is required.")
            locked_draft = (
                row["draft_data"] if isinstance(row["draft_data"], dict) else {}
            )
            reconciliation = locked_draft.get("history_reconciliation")
            try:
                validate_history_reconciliation(reconciliation)
            except ValueError as exc:
                raise HTTPException(
                    409, "Baseline reconciliation is required."
                ) from exc
            if (
                not isinstance(reconciliation, dict)
                or reconciliation.get("status") != "confirmed"
            ):
                raise HTTPException(409, "Baseline reconciliation is required.")
            if _baseline_changed_for(conn, row):
                raise HTTPException(
                    409,
                    "Baseline changed. Reconcile against the current baseline.",
                )
        draft = row["draft_data"] if isinstance(row["draft_data"], dict) else {}
        draft_copy = json.loads(json.dumps(draft))
        medications_copy = (
            json.loads(json.dumps(draft.get("medications")))
            if draft.get("medications") is not None
            else None
        )
        ddi_copy = (
            json.loads(json.dumps(draft.get("ddi_report")))
            if draft.get("ddi_report") is not None
            else None
        )
        note_rows = (
            conn.execute(
                text(
                    "SELECT page, text, author_id, author_display, created_at "
                    "FROM encounter_notes WHERE encounter_id = :eid "
                    "ORDER BY created_at, id"
                ),
                {"eid": str(encounter_id)},
            )
            .mappings()
            .all()
        )
        notes_freeze = [
            {
                "page": str(item["page"]),
                "author_id": str(item["author_id"]),
                "author_display": str(item["author_display"]),
                "created_at": to_utc_z(item["created_at"]),
                "text": str(item["text"]),
            }
            for item in note_rows
        ]
        run_snapshot = run["snapshot"] if isinstance(run["snapshot"], dict) else {}
        pinned_raw = run_snapshot.get("pinned")
        pinned: dict[str, Any] = (
            dict(pinned_raw) if isinstance(pinned_raw, dict) else {}
        )
        pinned_copy = json.loads(json.dumps(pinned))
        proposal_dict = _fetch_proposal(conn, str(body.run_id))
        if proposal_dict is None:
            raise HTTPException(409, "Only a succeeded proposal can be signed.")
        initial_copy = json.loads(json.dumps(proposal_dict))
        patient_freeze = {
            "id": str(patient["id"]),
            "patient_id": str(patient["patient_id_text"]),
            "first_name": str(patient["first_name"]),
            "last_name": str(patient["last_name"]),
            "sex": str(patient["sex"]),
            "age": int(patient["age"]),
            "clinical_status": str(patient["clinical_status"]),
            "phone": patient["phone"],
        }
        content_versions: dict[str, Any] = {
            "bundle_hash": pinned.get("bundle_hash", run["bundle_hash"]),
            "pins": json.loads(json.dumps(pinned.get("pins", run["pins"]))),
            "provider_revision": pinned.get("provider_revision"),
            "pinned": pinned_copy,
        }
        signed_at = to_utc_z(utc_now())
        snapshot_body: dict[str, Any] = {
            "schema_version": 1,
            "encounter_id": str(encounter_id),
            "patient_id": str(row["patient_id"]),
            "kind": row["kind"],
            "encounter_revision": current_revision,
            "run_id": str(body.run_id),
            "patient": patient_freeze,
            "draft_data": draft_copy,
            "notes": notes_freeze,
            "medications": medications_copy,
            "ddi_report": ddi_copy,
            "content_versions": content_versions,
            "initial_proposal": initial_copy,
            "secondary_plan": {
                "revision": latest_plan,
                "text": secondary_text,
            },
            "signer_id": actor_id,
            "signed_at": signed_at,
        }
        snapshot_hash = content_hash(snapshot_body)
        frozen: dict[str, Any] = dict(snapshot_body)
        frozen["snapshot_hash"] = snapshot_hash
        conn.execute(
            text(
                "INSERT INTO signed_snapshots (encounter_id, run_id, snapshot, "
                "snapshot_hash, signer_id, encounter_revision, "
                "secondary_plan_revision) VALUES (:eid, :run_id, "
                "CAST(:snapshot AS jsonb), :snapshot_hash, :signer_id, "
                ":encounter_revision, :secondary_plan_revision) "
                "ON CONFLICT (encounter_id) DO NOTHING"
            ),
            {
                "eid": str(encounter_id),
                "run_id": str(body.run_id),
                "snapshot": json.dumps(frozen),
                "snapshot_hash": snapshot_hash,
                "signer_id": actor_id,
                "encounter_revision": current_revision,
                "secondary_plan_revision": latest_plan,
            },
        )
        signed = (
            conn.execute(
                text(
                    "UPDATE encounters SET state = 'signed', "
                    "revision = revision + 1, updated_at = now() "
                    "WHERE id = :id RETURNING *"
                ),
                {"id": str(encounter_id)},
            )
            .mappings()
            .one()
        )
        result: dict[str, Any] = {
            "schema_version": 1,
            "encounter": _encounter_payload(signed),
            "signed_snapshot": frozen,
            "signature": snapshot_hash,
            "snapshot_hash": snapshot_hash,
        }
        record_audit(
            conn,
            operation=_SIGN_OPERATION,
            actor_id=actor_id,
            idempotency_key=key,
            request_hash=hash_password(fingerprint),
            result_reference=str(encounter_id),
            request_id=_request_id(request),
            target_display=str(row["patient_id"]),
            result_payload=result,
            result_status=201,
        )
        return JSONResponse(
            status_code=201,
            content=result,
            headers={
                "ETag": f'"{signed["revision"]}"',
                "Cache-Control": "private, no-store",
            },
        )


@router.post("/encounters/{encounter_id}/addenda")
def create_addendum(
    encounter_id: UUID, body: AddendumCreate, request: Request
) -> JSONResponse:
    reason = body.reason.strip()
    correction = body.correction_text.strip()
    with db.transaction() as conn:
        denied, actor = _require_session(request, conn)
        if denied is not None:
            return denied
        csrf_denied = _check_csrf(request, actor)
        if csrf_denied is not None:
            return csrf_denied
        key = parse_idempotency_key(request.headers)
        if key is None:
            raise HTTPException(422, "A valid Idempotency-Key is required.")
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
        actor_id = str(actor["user_id"])
        scope = {
            "actor_id": actor_id,
            "operation": _ADDENDUM_OPERATION,
            "idempotency_key": key,
            "encounter_id": str(encounter_id),
        }
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": canonical_json(scope).decode()},
        )
        fingerprint = canonical_json(
            {
                "encounter_id": str(encounter_id),
                "reason": reason,
                "correction": correction,
            }
        ).decode()
        saved = (
            conn.execute(
                text(
                    "SELECT request_hash, result_payload, result_status "
                    "FROM audit_events "
                    "WHERE actor_id = :actor_id AND operation = :operation "
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
        if row["state"] != "signed":
            raise HTTPException(409, "Only signed encounters can have addenda.")
        signed_row = (
            conn.execute(
                text(
                    "SELECT signer_id FROM signed_snapshots WHERE encounter_id = :eid"
                ),
                {"eid": str(encounter_id)},
            )
            .mappings()
            .first()
        )
        if signed_row is None:
            raise HTTPException(409, "Only signed encounters can have addenda.")
        signer_id = str(signed_row["signer_id"]) if signed_row["signer_id"] else None
        if signer_id != actor_id:
            raise HTTPException(403, "Only the original signer may add addenda.")
        if not reason or not correction:
            raise HTTPException(422, "Reason and correction text are required.")
        created = (
            conn.execute(
                text(
                    "INSERT INTO encounter_addenda "
                    "(encounter_id, author_id, reason, correction_text) "
                    "VALUES (:eid, :aid, :reason, :correction) RETURNING *"
                ),
                {
                    "eid": str(encounter_id),
                    "aid": actor_id,
                    "reason": reason,
                    "correction": correction,
                },
            )
            .mappings()
            .one()
        )
        result: dict[str, Any] = {
            "schema_version": 1,
            "addendum": _addendum_payload(created),
        }
        record_audit(
            conn,
            operation=_ADDENDUM_OPERATION,
            actor_id=actor_id,
            idempotency_key=key,
            request_hash=hash_password(fingerprint),
            result_reference=str(encounter_id),
            request_id=_request_id(request),
            target_display=str(row["patient_id"]),
            result_payload=result,
            result_status=201,
        )
        return JSONResponse(status_code=201, content=result)


@router.get("/encounters/{encounter_id}/addenda")
def list_addenda(encounter_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        denied, _actor = _require_session(request, conn)
        if denied is not None:
            return denied
        exists = conn.execute(
            text("SELECT id FROM encounters WHERE id = :id"),
            {"id": str(encounter_id)},
        ).first()
        if exists is None:
            raise HTTPException(404, "Encounter not found.")
        rows = (
            conn.execute(
                text(
                    "SELECT * FROM encounter_addenda "
                    "WHERE encounter_id = :eid ORDER BY created_at, id"
                ),
                {"eid": str(encounter_id)},
            )
            .mappings()
            .all()
        )
        return JSONResponse(
            {"schema_version": 1, "items": [_addendum_payload(r) for r in rows]},
            headers={"Cache-Control": "private, no-store"},
        )
