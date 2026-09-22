"""Admin network registry HTTP routes (S24 slice 1, seam T1)."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import text

from x_insight import db
from x_insight.contracts import canonical_json
from x_insight.identity.accounts import require_admin
from x_insight.identity.routes import _request_id
from x_insight.models.bundles import FOLLOWUP_ORDER, REGISTRATION_ORDER
from x_insight.models.registry import (
    load_network,
    load_version,
    load_versions,
    network_key,
    next_version,
    store_network,
    store_version,
)
from x_insight.models.semantics import check_admission, check_semantics
from x_insight.models.validation import XmlInputError, validate_xmlbif
from x_insight.operations.audit import record_audit

router = APIRouter()


class NetworkImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    xml: str


_WORKFLOWS: dict[str, list[str]] = {
    "registration": REGISTRATION_ORDER,
    "followup": FOLLOWUP_ORDER,
}


class BundlePin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_key: str
    network_version_id: str
    review: Any = None


class BundleActivate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow: str
    pins: list[BundlePin]
    expected_revision: int


class BundleRollback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow: str
    target_revision: int | None = None
    target_bundle_hash: str | None = None
    expected_revision: int

    @model_validator(mode="after")
    def _needs_target(self) -> BundleRollback:
        if self.target_revision is None and self.target_bundle_hash is None:
            raise ValueError("Provide target_revision or target_bundle_hash.")
        return self


def _bundle_body(
    workflow: str,
    revision: int,
    bundle_hash: str | None,
    pins: Any,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "workflow": workflow,
        "revision": revision,
        "bundle_hash": bundle_hash,
        "pins": pins if isinstance(pins, list) else [],
    }


def _load_pointer(conn: Any, workflow: str, *, lock: bool = False) -> Any | None:
    return (
        conn.execute(
            text(
                "SELECT * FROM model_bundle_pointers WHERE workflow = :w"
                + (" FOR UPDATE" if lock else "")
            ),
            {"w": workflow},
        )
        .mappings()
        .first()
    )


def _check_coverage(expected: list[str], pins: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    for pin in pins:
        key = pin.get("question_key") if isinstance(pin, dict) else None
        if not isinstance(key, str) or not key:
            raise HTTPException(422, "malformed_entry: pin missing question_key.")
        keys.append(key)
    expected_set = set(expected)
    counts: dict[str, int] = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    for key in expected:
        if key not in counts:
            raise HTTPException(
                422, f"missing_question: bundle missing question: {key}"
            )
    for key in counts:
        if key not in expected_set:
            raise HTTPException(
                422, f"unexpected_question: bundle has unexpected question: {key}"
            )
        if counts[key] > 1:
            raise HTTPException(
                422, f"duplicate_question: bundle duplicates question: {key}"
            )
    if keys != expected:
        raise HTTPException(422, "wrong_order: bundle questions out of order.")
    return keys


def _resolve_pins(
    conn: Any, expected: list[str], pins: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_key = {p["question_key"]: p for p in pins if isinstance(p, dict)}
    resolved: list[dict[str, Any]] = []
    stored: list[dict[str, Any]] = []
    for key in expected:
        pin = by_key[key]
        raw_id = pin.get("network_version_id")
        try:
            version_id = UUID(str(raw_id))
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(
                422, f"load_failed: invalid network version id for {key}"
            ) from None
        row = load_version(conn, version_id)
        if row is None:
            raise HTTPException(
                422, f"load_failed: network version not found for {key}"
            )
        semantic = row["semantic_report"]
        if not (isinstance(semantic, dict) and semantic.get("executable") is True):
            raise HTTPException(
                422,
                f"semantic_not_executable: network version for {key} is not executable",
            )
        admission = row["admission_report"]
        if not (isinstance(admission, dict) and admission.get("admitted") is True):
            raise HTTPException(
                422,
                f"admission_rejected: network version for {key} is not admitted",
            )
        review = pin.get("review")
        if not (
            isinstance(review, dict)
            and review.get("decision") == "approved"
            and isinstance(review.get("reviewer"), str)
            and str(review.get("reviewer")).strip() != ""
            and isinstance(review.get("date"), str)
            and str(review.get("date")).strip() != ""
        ):
            raise HTTPException(
                422,
                f"unreviewed_package: question {key} lacks an approved review",
            )
        resolved.append(
            {
                "question_key": key,
                "version": int(row["version"]),
                "network_hash": "sha256:" + str(row["sha256"]),
            }
        )
        stored.append(
            {
                "question_key": key,
                "network_version_id": str(raw_id),
                "review": review,
            }
        )
    return resolved, stored


def _bundle_hash(workflow: str, resolved: list[dict[str, Any]]) -> str:
    payload = {"workflow": workflow, "questions": resolved}
    return "sha256:" + hashlib.sha256(canonical_json(payload)).hexdigest()


def _write_bundle_event(
    conn: Any,
    workflow: str,
    revision: int,
    bundle_hash: str,
    stored: list[dict[str, Any]],
    actor_id: str,
    action: str,
) -> None:
    encoded = json.dumps(stored)
    conn.execute(
        text(
            "INSERT INTO model_bundle_events "
            "(workflow, revision, bundle_hash, pins, actor_id, action) "
            "VALUES (:w, :r, :h, CAST(:p AS jsonb), CAST(:a AS uuid), :act)"
        ),
        {
            "w": workflow,
            "r": revision,
            "h": bundle_hash,
            "p": encoded,
            "a": actor_id,
            "act": action,
        },
    )
    conn.execute(
        text(
            "INSERT INTO model_bundle_pointers "
            "(workflow, revision, bundle_hash, pins, updated_at) "
            "VALUES (:w, :r, :h, CAST(:p AS jsonb), now()) "
            "ON CONFLICT (workflow) DO UPDATE SET revision = EXCLUDED.revision, "
            "bundle_hash = EXCLUDED.bundle_hash, pins = EXCLUDED.pins, "
            "updated_at = now()"
        ),
        {"w": workflow, "r": revision, "h": bundle_hash, "p": encoded},
    )


def _check_expected_revision(current: int, expected: int) -> None:
    if expected != current:
        raise HTTPException(
            412,
            f"Stale revision: expected {expected}, current is {current}. "
            "Reload and reconcile.",
        )


def _normalize_pins(pins: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for pin in pins:
        if isinstance(pin, BaseModel):
            items.append(dict(pin.model_dump()))
        elif isinstance(pin, dict):
            items.append(dict(pin))
        else:
            raise HTTPException(422, "malformed_entry: pin must be an object.")
    return items


def _version_item(row: Any) -> dict[str, Any]:
    sha = str(row["sha256"])
    xsd = row["xsd_report"]
    valid = isinstance(xsd, dict) and xsd.get("valid") is True
    return {
        "version_id": str(row["id"]),
        "id": str(row["id"]),
        "version_number": int(row["version"]),
        "version": int(row["version"]),
        "sha256": sha,
        "source_sha256": sha,
        "byte_count": int(row["byte_count"]),
        "xsd_valid": valid,
    }


def _import_body(network_id: UUID, row: Any, xsd_valid: bool) -> dict[str, Any]:
    sha = str(row["sha256"])
    return {
        "schema_version": 1,
        "network_id": str(network_id),
        "id": str(network_id),
        "version_id": str(row["id"]),
        "version_number": int(row["version"]),
        "sha256": sha,
        "source_sha256": sha,
        "byte_count": int(row["byte_count"]),
        "xsd_valid": xsd_valid,
        "xsd_report": row["xsd_report"],
    }


def _store_imported(
    conn: Any,
    actor_id: str,
    request_id: str,
    key: str,
    xml_bytes: bytes,
    sha: str,
    byte_count: int,
    xsd_report: dict[str, Any],
    semantic_report: dict[str, Any],
    admission_report: dict[str, Any],
    operation: str,
    network_id: UUID | None = None,
) -> tuple[Any, Any]:
    if network_id is None:
        network = store_network(conn, key, actor_id)
        nid: UUID = network["id"]
        version_number = 1
    else:
        network = load_network(conn, network_id)
        if network is None:
            raise HTTPException(404, "Network not found.")
        nid = network_id
        version_number = next_version(conn, nid)
    version_row = store_version(
        conn,
        nid,
        version_number,
        xml_bytes,
        sha,
        byte_count,
        xsd_report,
        semantic_report,
        admission_report,
        actor_id,
    )
    record_audit(
        conn,
        operation=operation,
        actor_id=actor_id,
        request_id=request_id,
        result_reference=str(version_row["id"]),
        target_display=key,
        details={
            "network_id": str(nid),
            "version": version_number,
            "sha256": sha,
            "byte_count": byte_count,
            "xsd_valid": bool(xsd_report.get("valid") is True),
        },
        result_status=201,
    )
    return network, version_row


def _decode_and_validate(xml_text: str) -> tuple[bytes, dict[str, Any]]:
    xml_bytes = xml_text.encode("utf-8")
    try:
        validated = validate_xmlbif(xml_bytes)
    except XmlInputError as exc:
        raise HTTPException(422, str(exc)[:500]) from None
    return xml_bytes, validated


def _stored_bytes(row: Any) -> bytes:
    raw = row["xml"]
    if isinstance(raw, (bytes, bytearray, memoryview)):
        return bytes(raw)
    return bytes(bytearray(raw))


@router.post("/networks")
def import_network(body: NetworkImport, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        xml_bytes, validated = _decode_and_validate(body.xml)
        xsd_report = validated["xsd_report"]
        semantic_report = check_semantics(validated)
        admission_report = check_admission(validated)
        key = network_key(validated)
        sha = str(validated["source_sha256"])
        byte_count = int(validated["byte_count"])
        _, version_row = _store_imported(
            conn,
            str(actor["id"]),
            _request_id(request),
            key,
            xml_bytes,
            sha,
            byte_count,
            xsd_report,
            semantic_report,
            admission_report,
            "network.import",
        )
        payload = _import_body(
            version_row["network_id"],
            version_row,
            bool(xsd_report.get("valid") is True),
        )
        return JSONResponse(
            payload,
            status_code=201,
            headers={"ETag": f'"{sha}"', "Cache-Control": "private, no-store"},
        )


@router.get("/networks")
def list_networks(request: Request) -> JSONResponse:
    with db.transaction() as conn:
        require_admin(request, conn)
        rows = (
            conn.execute(text("SELECT * FROM networks ORDER BY created_at, id"))
            .mappings()
            .all()
        )
        items = [
            {
                "schema_version": 1,
                "id": str(r["id"]),
                "network_id": str(r["id"]),
                "key": str(r["key"]),
            }
            for r in rows
        ]
        return JSONResponse(
            {"schema_version": 1, "items": items},
            headers={"Cache-Control": "private, no-store"},
        )


@router.post("/networks/{network_id}/versions")
def add_version(
    network_id: UUID, body: NetworkImport, request: Request
) -> JSONResponse:
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        existing = load_network(conn, network_id)
        if existing is None:
            raise HTTPException(404, "Network not found.")
        xml_bytes, validated = _decode_and_validate(body.xml)
        xsd_report = validated["xsd_report"]
        semantic_report = check_semantics(validated)
        admission_report = check_admission(validated)
        key = network_key(validated)
        sha = str(validated["source_sha256"])
        byte_count = int(validated["byte_count"])
        _, version_row = _store_imported(
            conn,
            str(actor["id"]),
            _request_id(request),
            key,
            xml_bytes,
            sha,
            byte_count,
            xsd_report,
            semantic_report,
            admission_report,
            "network.version",
            network_id,
        )
        payload = _import_body(
            network_id, version_row, bool(xsd_report.get("valid") is True)
        )
        return JSONResponse(
            payload,
            status_code=201,
            headers={"ETag": f'"{sha}"', "Cache-Control": "private, no-store"},
        )


@router.get("/networks/{network_id}/versions")
def list_versions(network_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        require_admin(request, conn)
        if load_network(conn, network_id) is None:
            raise HTTPException(404, "Network not found.")
        rows = load_versions(conn, network_id)
        items = [_version_item(r) for r in rows]
        return JSONResponse(
            {"schema_version": 1, "items": items, "versions": items},
            headers={"Cache-Control": "private, no-store"},
        )


@router.get("/network-versions/{version_id}/xml")
def export_version_xml(version_id: UUID, request: Request) -> Response:
    with db.transaction() as conn:
        require_admin(request, conn)
        row = load_version(conn, version_id)
        if row is None:
            raise HTTPException(404, "Network version not found.")
        payload = _stored_bytes(row)
        return Response(content=payload, media_type="application/xml")


@router.get("/network-versions/{version_id}/graph")
def get_version_graph(version_id: UUID, request: Request) -> JSONResponse:
    """Read-only ordered graph view of a stored version (S24 slice 2)."""
    with db.transaction() as conn:
        require_admin(request, conn)
        row = load_version(conn, version_id)
        if row is None:
            raise HTTPException(404, "Network version not found.")
        try:
            validated = validate_xmlbif(_stored_bytes(row))
        except XmlInputError as exc:
            raise HTTPException(500, "Stored network bytes are unreadable.") from exc
        xsd_report = row["xsd_report"]
        semantic_report = row["semantic_report"]
        admission_report = row["admission_report"]
        if not isinstance(xsd_report, dict):
            xsd_report = {"valid": False, "errors": []}
        if not isinstance(semantic_report, dict):
            semantic_report = {"executable": False, "errors": []}
        if not isinstance(admission_report, dict):
            admission_report = {"admitted": False, "errors": []}
        xsd_valid = bool(xsd_report.get("valid") is True)
        executable = bool(semantic_report.get("executable") is True)
        admitted = bool(admission_report.get("admitted") is True)
        raw_edges = validated.get("edges", [])
        edges: list[list[str]] = []
        if isinstance(raw_edges, list):
            for item in raw_edges:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    edges.append([str(item[0]), str(item[1])])
        raw_nodes = validated.get("nodes", [])
        nodes = [str(n) for n in raw_nodes] if isinstance(raw_nodes, list) else []
        raw_states = validated.get("states", {})
        states = (
            {str(k): [str(s) for s in v] for k, v in raw_states.items()}
            if isinstance(raw_states, dict)
            else {}
        )
        return JSONResponse(
            {
                "schema_version": 1,
                "version_id": str(row["id"]),
                "network_id": str(row["network_id"]),
                "version_number": int(row["version"]),
                "version": int(row["version"]),
                "sha256": str(row["sha256"]),
                "source_sha256": str(row["sha256"]),
                "byte_count": int(row["byte_count"]),
                "nodes": nodes,
                "edges": edges,
                "states": states,
                "xsd_valid": xsd_valid,
                "xsd_report": xsd_report,
                "semantic": {"executable": executable},
                "semantic_report": semantic_report,
                "admission": {"admitted": admitted},
                "admission_report": admission_report,
                "executable": executable,
                "admitted": admitted,
                "validation_status": "valid" if xsd_valid else "invalid",
            },
            headers={"Cache-Control": "private, no-store"},
        )


@router.post("/network-versions/{version_id}/validate")
def validate_version(version_id: UUID, request: Request) -> JSONResponse:
    """Recompute validation reports from stored bytes without mutation."""
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        row = load_version(conn, version_id)
        if row is None:
            raise HTTPException(404, "Network version not found.")
        try:
            validated = validate_xmlbif(_stored_bytes(row))
        except XmlInputError as exc:
            raise HTTPException(500, "Stored network bytes are unreadable.") from exc
        xsd_report = validated["xsd_report"]
        semantic_report = check_semantics(validated)
        admission_report = check_admission(validated)
        executable = bool(semantic_report.get("executable") is True)
        admitted = bool(admission_report.get("admitted") is True)
        record_audit(
            conn,
            operation="network.validate",
            actor_id=str(actor["id"]),
            request_id=_request_id(request),
            result_reference=str(row["id"]),
            target_display=str(row["network_id"]),
            details={
                "network_id": str(row["network_id"]),
                "version": int(row["version"]),
                "sha256": str(row["sha256"]),
                "xsd_valid": bool(xsd_report.get("valid") is True),
                "executable": executable,
                "admitted": admitted,
            },
            result_status=200,
        )
        return JSONResponse(
            {
                "schema_version": 1,
                "version_id": str(row["id"]),
                "network_id": str(row["network_id"]),
                "xsd_report": xsd_report,
                "semantic_report": semantic_report,
                "admission_report": admission_report,
                "xsd_valid": bool(xsd_report.get("valid") is True),
                "executable": executable,
                "admitted": admitted,
            },
            headers={"Cache-Control": "private, no-store"},
        )


@router.get("/model-bundles/{workflow}")
def get_bundle_pointer(workflow: str, request: Request) -> JSONResponse:
    """Read the current bundle pointer for a workflow (no audit)."""
    with db.transaction() as conn:
        require_admin(request, conn)
        if workflow not in _WORKFLOWS:
            raise HTTPException(
                404, f"unknown_workflow: unknown workflow: {workflow!r}"
            )
        row = _load_pointer(conn, workflow)
        if row is None:
            body = _bundle_body(workflow, 0, None, [])
        else:
            body = _bundle_body(
                workflow, int(row["revision"]), row["bundle_hash"], row["pins"]
            )
        return JSONResponse(body, headers={"Cache-Control": "private, no-store"})


@router.post("/model-bundles/activate")
def activate_bundle(body: BundleActivate, request: Request) -> JSONResponse:
    """Atomically activate a complete reviewed workflow bundle."""
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        expected = _WORKFLOWS.get(body.workflow)
        if expected is None:
            raise HTTPException(
                404, f"unknown_workflow: unknown workflow: {body.workflow!r}"
            )
        current = _load_pointer(conn, body.workflow, lock=True)
        current_revision = int(current["revision"]) if current is not None else 0
        _check_expected_revision(current_revision, body.expected_revision)
        pins = _normalize_pins(list(body.pins))
        _check_coverage(expected, pins)
        resolved, stored = _resolve_pins(conn, expected, pins)
        bundle_hash = _bundle_hash(body.workflow, resolved)
        revision = current_revision + 1
        _write_bundle_event(
            conn,
            body.workflow,
            revision,
            bundle_hash,
            stored,
            str(actor["id"]),
            "activate",
        )
        record_audit(
            conn,
            operation="model_bundle.activate",
            actor_id=str(actor["id"]),
            request_id=_request_id(request),
            result_reference=bundle_hash,
            target_display=body.workflow,
            details={"workflow": body.workflow, "revision": revision},
            result_status=200,
        )
        return JSONResponse(
            _bundle_body(body.workflow, revision, bundle_hash, stored),
            headers={"Cache-Control": "private, no-store"},
        )


@router.post("/model-bundles/rollback")
def rollback_bundle(body: BundleRollback, request: Request) -> JSONResponse:
    """Rollback as a new activation event selecting prior valid versions."""
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        expected = _WORKFLOWS.get(body.workflow)
        if expected is None:
            raise HTTPException(
                404, f"unknown_workflow: unknown workflow: {body.workflow!r}"
            )
        current = _load_pointer(conn, body.workflow, lock=True)
        current_revision = int(current["revision"]) if current is not None else 0
        _check_expected_revision(current_revision, body.expected_revision)
        if body.target_revision is not None:
            target = (
                conn.execute(
                    text(
                        "SELECT * FROM model_bundle_events "
                        "WHERE workflow = :w AND revision = :r"
                    ),
                    {"w": body.workflow, "r": body.target_revision},
                )
                .mappings()
                .first()
            )
        else:
            target = (
                conn.execute(
                    text(
                        "SELECT * FROM model_bundle_events "
                        "WHERE workflow = :w AND bundle_hash = :h "
                        "ORDER BY revision DESC LIMIT 1"
                    ),
                    {"w": body.workflow, "h": body.target_bundle_hash},
                )
                .mappings()
                .first()
            )
        if target is None:
            raise HTTPException(404, "Target bundle revision not found.")
        raw_pins = target["pins"]
        if not isinstance(raw_pins, list):
            raise HTTPException(422, "content_mismatch: target pins are unreadable.")
        pins = _normalize_pins(list(raw_pins))
        _check_coverage(expected, pins)
        resolved, stored = _resolve_pins(conn, expected, pins)
        bundle_hash = _bundle_hash(body.workflow, resolved)
        revision = current_revision + 1
        _write_bundle_event(
            conn,
            body.workflow,
            revision,
            bundle_hash,
            stored,
            str(actor["id"]),
            "rollback",
        )
        record_audit(
            conn,
            operation="model_bundle.rollback",
            actor_id=str(actor["id"]),
            request_id=_request_id(request),
            result_reference=bundle_hash,
            target_display=body.workflow,
            details={
                "workflow": body.workflow,
                "revision": revision,
                "target_revision": int(target["revision"]),
            },
            result_status=200,
        )
        return JSONResponse(
            _bundle_body(body.workflow, revision, bundle_hash, stored),
            headers={"Cache-Control": "private, no-store"},
        )
