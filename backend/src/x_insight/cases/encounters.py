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
from x_insight.assessments.cssrs import evaluate_cssrs
from x_insight.assessments.diagnosis import evaluate_diagnosis
from x_insight.assessments.panss import evaluate_panss
from x_insight.cases.history import (
    validate_and_stamp_effects,
    validate_and_stamp_history,
    validate_ddi_report,
    validate_history_reconciliation,
    validate_medications,
)
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


class FollowupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_encounter_id: UUID


def _payload(row: Any, baseline_changed: bool = False) -> dict[str, Any]:
    data = dict(row)
    baseline = data.get("baseline_encounter_id")
    return {
        "schema_version": 1,
        "encounter": {
            "id": str(data["id"]),
            "patient_id": str(data["patient_id"]),
            "kind": data["kind"],
            "author_id": str(data["author_id"]) if data["author_id"] else None,
            "state": data["state"],
            "revision": data["revision"],
            "baseline_encounter_id": str(baseline) if baseline else None,
            "baseline_changed": bool(baseline_changed),
            "draft_data": data.get("draft_data") or {},
            "created_at": to_utc_z(data["created_at"]),
            "updated_at": to_utc_z(data["updated_at"]),
        },
    }


def _has_newer_signed(conn: Any, patient_id: str, baseline_id: str) -> bool:
    row = (
        conn.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM encounters b JOIN encounters s "
                "ON s.patient_id = :pid WHERE b.id = :bid "
                "AND s.patient_id = :pid AND s.state = 'signed' "
                "AND s.id != b.id AND (s.created_at > b.created_at OR "
                "(s.created_at = b.created_at AND s.id::text > b.id::text)))"
            ),
            {"pid": str(patient_id), "bid": str(baseline_id)},
        )
        .mappings()
        .first()
    )
    if row is None:
        return False
    return bool(list(row.values())[0])


def _baseline_changed_for(conn: Any, row: Any) -> bool:
    try:
        data = dict(row)
        if data.get("kind") != "follow_up":
            return False
        baseline = data.get("baseline_encounter_id")
        if not baseline:
            return False
        return _has_newer_signed(conn, str(data["patient_id"]), str(baseline))
    except Exception:
        return False


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
                "items": [
                    _payload(r, _baseline_changed_for(conn, r))["encounter"]
                    for r in rows
                ],
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
        payload = _payload(row, _baseline_changed_for(conn, row))
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


def _apply_panss_validation(incoming: dict[str, Any]) -> dict[str, Any]:
    """Validate PANSS answers on autosave (S10 slice 3, arithmetic-only).

    If draft_data contains a panss dict with an answers dict, validate via
    evaluate_panss; partial/complete/not_assessed persist verbatim (200),
    ValueError maps to 422 with revision untouched. Also accepts the skip
    shape {not_assessed: True} at panss level (no answers key), validated
    as {not_assessed: True} answers; stored verbatim on success. Missing
    panss or non-dict panss is left untouched for other flows.
    """
    if "panss" not in incoming:
        return incoming
    panss = incoming["panss"]
    if not isinstance(panss, dict):
        return incoming
    if "answers" in panss:
        answers = panss["answers"]
        if not isinstance(answers, dict):
            raise HTTPException(422, "Invalid PANSS content.")
        try:
            evaluate_panss(answers)
        except ValueError as exc:
            raise HTTPException(422, "Invalid PANSS content.") from exc
        return incoming
    if set(panss.keys()) == {"not_assessed"} and panss.get("not_assessed") is True:
        try:
            evaluate_panss({"not_assessed": True})
        except ValueError as exc:
            raise HTTPException(422, "Invalid PANSS content.") from exc
        return incoming
    return incoming


def _apply_cssrs_validation(incoming: dict[str, Any]) -> dict[str, Any]:
    """Validate C-SSRS answers on autosave (S11 slice 1, ideation-only).

    If draft_data contains a cssrs dict with an answers dict, validate via
    evaluate_cssrs; ValueError maps to 422 with revision untouched.
    Also accepts the skip shape {not_assessed: True} at cssrs level,
    validated as {not_assessed: True} answers; stored verbatim on success.
    Missing cssrs or non-dict cssrs is left untouched for other flows.
    """
    if "cssrs" not in incoming:
        return incoming
    cssrs = incoming["cssrs"]
    if not isinstance(cssrs, dict):
        return incoming
    if "answers" in cssrs:
        answers = cssrs["answers"]
        if not isinstance(answers, dict):
            raise HTTPException(422, "Invalid C-SSRS content.")
        try:
            evaluate_cssrs(answers)
        except ValueError as exc:
            raise HTTPException(422, "Invalid C-SSRS content.") from exc
        return incoming
    if set(cssrs.keys()) == {"not_assessed"} and cssrs.get("not_assessed") is True:
        try:
            evaluate_cssrs({"not_assessed": True})
        except ValueError as exc:
            raise HTTPException(422, "Invalid C-SSRS content.") from exc
        return incoming
    return incoming


def _apply_history_validation(
    incoming: dict[str, Any], actor_id: str, new_revision: int
) -> dict[str, Any]:
    if "history" not in incoming:
        return incoming
    try:
        history = validate_and_stamp_history(
            incoming["history"],
            actor_id=actor_id,
            encounter_revision=new_revision,
        )
    except ValueError as exc:
        raise HTTPException(422, "Invalid history content.") from exc
    updated = dict(incoming)
    updated["history"] = history
    return updated


def _apply_effects_validation(
    incoming: dict[str, Any], actor_id: str, new_revision: int
) -> dict[str, Any]:
    if "effects" not in incoming:
        return incoming
    try:
        effects = validate_and_stamp_effects(
            incoming["effects"],
            actor_id=actor_id,
            encounter_revision=new_revision,
        )
    except ValueError as exc:
        raise HTTPException(422, "Invalid adverse-effect content.") from exc
    updated = dict(incoming)
    updated["effects"] = effects
    return updated


def _apply_medications_guard(incoming: dict[str, Any]) -> dict[str, Any]:
    if "medications" not in incoming:
        return incoming
    try:
        validate_medications(incoming["medications"])
    except ValueError as exc:
        raise HTTPException(422, "Invalid medication content.") from exc
    return incoming


def _apply_ddi_report_guard(incoming: dict[str, Any]) -> dict[str, Any]:
    if "ddi_report" not in incoming:
        return incoming
    try:
        validate_ddi_report(incoming["ddi_report"])
    except ValueError as exc:
        raise HTTPException(422, "Invalid DDI report content.") from exc
    return incoming


def _apply_reconciliation_guard(incoming: dict[str, Any]) -> dict[str, Any]:
    if "history_reconciliation" not in incoming:
        return incoming
    try:
        validate_history_reconciliation(incoming["history_reconciliation"])
    except ValueError as exc:
        raise HTTPException(422, "Invalid history reconciliation.") from exc
    return incoming


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
        actor_id = str(actor["user_id"])
        new_revision = int(row["revision"]) + 1
        new_draft = _apply_reconciliation_guard(
            _apply_ddi_report_guard(
                _apply_medications_guard(
                    _apply_effects_validation(
                        _apply_history_validation(
                            _apply_cssrs_validation(
                                _apply_panss_validation(
                                    _apply_diagnosis_ack(
                                        dict(body.draft_data),
                                        stored_draft,
                                        actor_id,
                                        new_revision,
                                    )
                                )
                            ),
                            actor_id,
                            new_revision,
                        ),
                        actor_id,
                        new_revision,
                    )
                )
            )
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
        payload = _payload(updated, _baseline_changed_for(conn, updated))
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
            _payload(discarded, _baseline_changed_for(conn, discarded)),
            headers={
                "ETag": f'"{discarded["revision"]}"',
                "Cache-Control": "private, no-store",
            },
        )


@router.post("/patients/{patient_id}/encounters")
def create_followup(
    patient_id: UUID, body: FollowupCreate, request: Request
) -> JSONResponse:
    with db.transaction() as conn:
        denied, actor = _require_session(request, conn)
        if denied is not None:
            return denied
        if actor["role"] != "physician":
            raise HTTPException(403, "Physician access required.")
        csrf_denied = _check_csrf(request, actor)
        if csrf_denied is not None:
            return csrf_denied
        key = parse_idempotency_key(request.headers)
        if key is None:
            raise HTTPException(422, "A valid Idempotency-Key is required.")
        patient = (
            conn.execute(
                text("SELECT * FROM patients WHERE id = :id FOR UPDATE"),
                {"id": str(patient_id)},
            )
            .mappings()
            .first()
        )
        if patient is None:
            raise HTTPException(404, "Patient not found.")
        baseline = (
            conn.execute(
                text("SELECT * FROM encounters WHERE id = :id"),
                {"id": str(body.baseline_encounter_id)},
            )
            .mappings()
            .first()
        )
        if baseline is None or str(baseline["patient_id"]) != str(patient_id):
            raise HTTPException(404, "Baseline encounter not found.")
        if patient["archived"]:
            raise HTTPException(409, "Archived patient drafts are read-only.")
        if baseline["state"] != "signed":
            raise HTTPException(409, "Only signed baselines can start a follow-up.")
        actor_id = str(actor["user_id"])
        scope = {
            "actor_id": actor_id,
            "operation": "encounter.followup_create",
            "idempotency_key": key,
            "patient_id": str(patient_id),
            "baseline_encounter_id": str(body.baseline_encounter_id),
        }
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": canonical_json(scope).decode()},
        )
        fingerprint = canonical_json(
            {
                "patient_id": str(patient_id),
                "baseline_encounter_id": str(body.baseline_encounter_id),
            }
        ).decode()
        saved = (
            conn.execute(
                text(
                    "SELECT request_hash, result_payload, result_status "
                    "FROM audit_events "
                    "WHERE actor_id = :actor_id AND operation = :operation "
                    "AND idempotency_key = :idempotency_key"
                ),
                {
                    "actor_id": actor_id,
                    "operation": "encounter.followup_create",
                    "idempotency_key": key,
                },
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
        baseline_draft = baseline["draft_data"]
        if not isinstance(baseline_draft, dict):
            baseline_draft = {}
        new_draft: dict[str, Any] = {}
        stored_history = baseline_draft.get("history")
        if (
            isinstance(stored_history, dict)
            and isinstance(stored_history.get("definition_version"), str)
            and isinstance(stored_history.get("values"), dict)
        ):
            new_draft["history"] = {
                "definition_version": stored_history["definition_version"],
                "values": stored_history["values"],
                "provenance": {
                    "actor_id": actor_id,
                    "recorded_at": to_utc_z(utc_now()),
                    "encounter_revision": 1,
                },
            }
        stored_medications = baseline_draft.get("medications")
        if isinstance(stored_medications, list):
            new_draft["medications"] = [
                dict(m) if isinstance(m, dict) else m for m in stored_medications
            ]
        new_draft["history_reconciliation"] = {
            "status": "pending",
            "baseline_encounter_id": str(body.baseline_encounter_id),
        }
        created = (
            conn.execute(
                text(
                    "INSERT INTO encounters (patient_id, kind, author_id, "
                    " state, baseline_encounter_id, draft_data) VALUES (:patient_id, "
                    " 'follow_up', :author_id, 'draft', :baseline_id, "
                    " CAST(:data AS jsonb)) "
                    "RETURNING *"
                ),
                {
                    "patient_id": str(patient_id),
                    "author_id": actor_id,
                    "baseline_id": str(body.baseline_encounter_id),
                    "data": json.dumps(new_draft),
                },
            )
            .mappings()
            .one()
        )
        result = _payload(created, _baseline_changed_for(conn, created))
        record_audit(
            conn,
            operation="encounter.followup_create",
            actor_id=actor_id,
            idempotency_key=key,
            request_hash=hash_password(fingerprint),
            result_reference=str(created["id"]),
            request_id=_request_id(request),
            target_display=str(patient_id),
            result_payload=result,
            result_status=201,
        )
        return JSONResponse(status_code=201, content=result)
