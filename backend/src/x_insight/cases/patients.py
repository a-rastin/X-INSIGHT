"""Patient registration (S06 slice 1: create patient + registration draft)."""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from x_insight import db
from x_insight.contracts import (
    canonical_json,
    parse_idempotency_key,
    parse_if_match,
    to_utc_z,
)
from x_insight.identity.hashing import hash_password, verify_password
from x_insight.identity.routes import _check_csrf, _request_id, _require_session
from x_insight.operations.audit import record_audit

router = APIRouter()

_PATIENT_ID_RE = re.compile(r"[0-9]{10}")


class PatientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: StrictStr = Field(min_length=1)
    last_name: StrictStr = Field(min_length=1)
    sex: Literal["M", "F"]
    age: StrictInt = Field(ge=18, le=99)
    patient_id: StrictStr = Field(min_length=1)
    clinical_status: Literal["first_time", "established"]
    phone: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def _letters_only(cls, v: str) -> str:
        v = unicodedata.normalize("NFC", v)
        if not v or not all(c.isalpha() for c in v):
            raise ValueError("Must contain Unicode letters only.")
        return v

    @field_validator("patient_id")
    @classmethod
    def _patient_id_ascii_digits(cls, v: str) -> str:
        if _PATIENT_ID_RE.fullmatch(v) is None:
            raise ValueError("Must be exactly 10 ASCII digits.")
        return v


class PatientPhonePatch(BaseModel):
    """S12 slice 2: physician-only optional phone text update.

    Phone is plain optional text with no country/format validation
    (plan 2.2). Stored verbatim; explicit null clears. Names, ID, sex,
    age, and clinical status are never touched here.
    """

    model_config = ConfigDict(extra="forbid")
    phone: str | None


def _patient_payload(patient: Any) -> dict[str, Any]:
    row: dict[str, Any] = dict(patient)
    return {
        "id": str(row["id"]),
        "patient_id": row["patient_id_text"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "sex": row["sex"],
        "age": row["age"],
        "clinical_status": row["clinical_status"],
        "phone": row["phone"],
        "archived": row["archived"],
        "revision": row["revision"],
        "created_at": to_utc_z(row["created_at"]),
        "updated_at": to_utc_z(row["updated_at"]),
    }


def _encounter_payload(encounter: Any) -> dict[str, Any]:
    row: dict[str, Any] = dict(encounter)
    return {
        "id": str(row["id"]),
        "patient_id": str(row["patient_id"]),
        "kind": row["kind"],
        "state": row["state"],
        "revision": row["revision"],
        "created_at": to_utc_z(row["created_at"]),
        "updated_at": to_utc_z(row["updated_at"]),
    }


@router.get("/patients")
def list_patients(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: UUID | None = None,
    q: str | None = None,
    clinical_status: Literal["first_time", "established"] | None = None,
    archived: bool = False,
) -> JSONResponse:
    with db.transaction() as conn:
        denied, _actor = _require_session(request, conn)
        if denied is not None:
            return denied
        rows = (
            conn.execute(
                text(
                    "SELECT * FROM patients "
                    "WHERE archived = :archived "
                    "AND (CAST(:status AS text) IS NULL "
                    "OR clinical_status = :status) "
                    "AND (CAST(:q AS text) IS NULL "
                    "OR first_name ILIKE '%' || :q || '%' "
                    "OR last_name ILIKE '%' || :q || '%' "
                    "OR patient_id_text ILIKE '%' || :q || '%') "
                    "AND (CAST(:cursor AS uuid) IS NULL OR id > :cursor) "
                    "ORDER BY id LIMIT :limit"
                ),
                {
                    "archived": archived,
                    "status": clinical_status,
                    "q": q,
                    "cursor": cursor,
                    "limit": limit + 1,
                },
            )
            .mappings()
            .all()
        )
        return JSONResponse(
            {
                "schema_version": 1,
                "items": [_patient_payload(r) for r in rows[:limit]],
                "next_cursor": str(rows[limit - 1]["id"])
                if len(rows) > limit
                else None,
            },
            headers={"Cache-Control": "private, no-store"},
        )


@router.patch("/patients/{patient_id}")
def patch_patient_phone(
    patient_id: UUID, body: PatientPhonePatch, request: Request
) -> JSONResponse:
    """Update only the optional phone text (S12 slice 2, minimal).

    Mirrors the S07 author/revision pattern for encounters: session +
    physician role required (anonymous 401, admin 403), If-Match revision
    required (stale 412), revision bumped, attributed patient.update audit.
    Follow-up copy semantics belong to S14.
    """
    with db.transaction() as conn:
        denied, actor = _require_session(request, conn)
        if denied is not None:
            return denied
        if actor["role"] != "physician":
            raise HTTPException(403, "Physician access required.")
        csrf_denied = _check_csrf(request, actor)
        if csrf_denied is not None:
            return csrf_denied
        row = (
            conn.execute(
                text("SELECT * FROM patients WHERE id = :id FOR UPDATE"),
                {"id": str(patient_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(404, "Patient not found.")
        if parse_if_match(request.headers) != str(row["revision"]):
            raise HTTPException(
                412, "The patient changed. Reload and reconcile your edits."
            )
        updated = (
            conn.execute(
                text(
                    "UPDATE patients SET phone = :phone, "
                    " revision = revision + 1, updated_at = now() "
                    "WHERE id = :id RETURNING *"
                ),
                {"id": str(patient_id), "phone": body.phone},
            )
            .mappings()
            .one()
        )
        record_audit(
            conn,
            operation="patient.update",
            actor_id=str(actor["id"]),
            request_id=_request_id(request),
            result_reference=str(updated["id"]),
            target_display=str(updated["patient_id_text"]),
        )
        return JSONResponse(
            {"schema_version": 1, "patient": _patient_payload(updated)},
            headers={
                "ETag": f'"{updated["revision"]}"',
                "Cache-Control": "private, no-store",
            },
        )


@router.post("/patients")
def create_patient(body: PatientCreate, request: Request) -> JSONResponse:
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
        scope = {
            "actor_id": str(actor["id"]),
            "operation": "patient.create",
            "idempotency_key": key,
        }
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": canonical_json(scope).decode()},
        )
        fingerprint = canonical_json({"body": body.model_dump()}).decode()
        saved = (
            conn.execute(
                text(
                    "SELECT request_hash, result_payload, result_status "
                    "FROM audit_events "
                    "WHERE actor_id = :actor_id AND operation = :operation "
                    "AND idempotency_key = :idempotency_key"
                ),
                scope,
            )
            .mappings()
            .first()
        )
        if saved is not None:
            if not verify_password(fingerprint, saved["request_hash"]):
                raise HTTPException(
                    409, "Idempotency key was used for another request."
                )
            return JSONResponse(
                status_code=saved["result_status"],
                content=saved["result_payload"],
            )
        try:
            patient = (
                conn.execute(
                    text(
                        "INSERT INTO patients (patient_id_text, first_name, "
                        " last_name, sex, age, clinical_status, phone) "
                        "VALUES (:patient_id, :first_name, :last_name, :sex, "
                        " :age, :clinical_status, :phone) RETURNING *"
                    ),
                    {
                        "patient_id": body.patient_id,
                        "first_name": body.first_name,
                        "last_name": body.last_name,
                        "sex": body.sex,
                        "age": body.age,
                        "clinical_status": body.clinical_status,
                        "phone": body.phone,
                    },
                )
                .mappings()
                .one()
            )
            encounter = (
                conn.execute(
                    text(
                        "INSERT INTO encounters (patient_id, kind, author_id, "
                        " state) VALUES (:patient_id, 'registration', "
                        " :author_id, 'draft') RETURNING *"
                    ),
                    {
                        "patient_id": str(patient["id"]),
                        "author_id": str(actor["id"]),
                    },
                )
                .mappings()
                .one()
            )
        except IntegrityError as exc:
            name = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
            if name and "patient_id" in name:
                raise HTTPException(409, "Patient ID already exists.") from None
            raise
        result: dict[str, object] = {
            "schema_version": 1,
            "patient": _patient_payload(patient),
            "encounter": _encounter_payload(encounter),
        }
        record_audit(
            conn,
            operation="patient.create",
            actor_id=str(actor["id"]),
            idempotency_key=key,
            request_hash=hash_password(fingerprint),
            result_reference=str(patient["id"]),
            request_id=_request_id(request),
            target_display=str(patient["patient_id_text"]),
            result_payload=result,
            result_status=201,
        )
        return JSONResponse(status_code=201, content=result)
