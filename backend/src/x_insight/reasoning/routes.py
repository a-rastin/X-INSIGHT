"""Admin provider-settings HTTP routes (S42, seam T1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.engine import Connection

from x_insight import db
from x_insight.contracts import parse_if_match, to_utc_z
from x_insight.identity.accounts import require_admin
from x_insight.identity.routes import _request_id
from x_insight.operations.audit import record_audit
from x_insight.reasoning.provider_config import (
    PLACEHOLDER_KEY,
    ProviderURLBlocked,
    check_capabilities,
    decrypt_api_key,
    encrypt_api_key,
    validate_url_for_save,
)

router = APIRouter()


class SettingsSave(BaseModel):
    # key_action stays a plain optional here (validated in-handler) so that
    # administrator authorization runs before body-shape rejection: a
    # physician must see 403, not 422, even for a malformed save body.
    model_config = ConfigDict(extra="forbid")
    base_url: str | None = None
    model: str | None = None
    key_action: str | None = None
    api_key: str | None = None


class SettingsTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str | None = None


def _clean(value: str | None) -> str | None:
    """Strip optional text fields; blank counts as absent."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _version_item(row: Any) -> dict[str, Any]:
    return _masked(row)


def _active(conn: Connection) -> Any:
    pointer = (
        conn.execute(text("SELECT * FROM provider_config_pointer WHERE id = 1"))
        .mappings()
        .first()
    )
    if pointer is None or pointer["active_config_id"] is None:
        return None
    row = (
        conn.execute(
            text("SELECT * FROM provider_configs WHERE id = :id"),
            {"id": pointer["active_config_id"]},
        )
        .mappings()
        .first()
    )
    return row


def _masked(row: Any) -> dict[str, Any]:
    last_test = row["last_test_at"] if "last_test_at" in row.keys() else None
    return {
        "schema_version": 1,
        "base_url": row["base_url"],
        "model": row["model"],
        "revision": row["revision"],
        "key_configured": bool(row["key_present"]),
        "test_status": row["test_status"],
        "last_test": to_utc_z(last_test) if last_test is not None else None,
    }


def _masked_response(row: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(
        _masked(row),
        status_code=status,
        headers={
            "ETag": f'"{row["revision"]}"',
            "Cache-Control": "private, no-store",
        },
    )


def _next_revision(conn: Connection) -> int:
    current = conn.execute(
        text("SELECT COALESCE(MAX(revision), 0) FROM provider_configs")
    ).scalar()
    return int(current or 0) + 1


@router.get("/api-settings")
def get_settings(request: Request) -> JSONResponse:
    with db.transaction() as conn:
        require_admin(request, conn)
        current = _active(conn)
        if current is None:
            raise HTTPException(404, "Provider settings are not configured.")
        return _masked_response(current)


@router.put("/api-settings")
def save_settings(body: SettingsSave, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        current = _active(conn)
        if body.key_action not in ("replace", "unchanged", "clear"):
            raise HTTPException(422, "key_action must be replace, unchanged or clear.")
        raw_base = _clean(body.base_url)
        raw_model = _clean(body.model)
        base_url = raw_base or (
            str(current["base_url"]) if current is not None else None
        )
        model = raw_model or (str(current["model"]) if current is not None else None)
        if not base_url or not model:
            raise HTTPException(422, "A base URL and model are required.")
        try:
            validate_url_for_save(base_url)
        except ProviderURLBlocked as exc:
            raise HTTPException(422, str(exc)) from None
        # Fencing is checked after destination validation so that forbidden
        # saves report 400/422 rather than a misleading 412.
        if current is not None and parse_if_match(request.headers) != str(
            current["revision"]
        ):
            raise HTTPException(412, "Provider settings changed. Reload and reconcile.")
        if body.key_action == "replace":
            if (
                body.api_key is None
                or not body.api_key.strip()
                or body.api_key == PLACEHOLDER_KEY
            ):
                raise HTTPException(
                    422, "Replacing the key requires sending a real API key."
                )
            ciphertext: str | None = encrypt_api_key(body.api_key)
            key_present = True
        elif body.key_action == "clear":
            ciphertext = None
            key_present = False
        else:
            ciphertext = (
                str(current["key_ciphertext"])
                if current is not None and current["key_ciphertext"] is not None
                else None
            )
            key_present = bool(current["key_present"]) if current is not None else False
        revision = _next_revision(conn)
        row = (
            conn.execute(
                text(
                    "INSERT INTO provider_configs "
                    "(revision, base_url, model, key_ciphertext, key_present, "
                    " test_status, created_by) "
                    "VALUES (:revision, :base_url, :model, :ciphertext, "
                    " :present, 'untested', :actor) RETURNING *"
                ),
                {
                    "revision": revision,
                    "base_url": base_url,
                    "model": model,
                    "ciphertext": ciphertext,
                    "present": key_present,
                    "actor": str(actor["id"]),
                },
            )
            .mappings()
            .one()
        )
        conn.execute(
            text(
                "INSERT INTO provider_config_pointer "
                "(id, active_config_id, active_revision) "
                "VALUES (1, :id, :revision) "
                "ON CONFLICT (id) DO UPDATE SET "
                "active_config_id = EXCLUDED.active_config_id, "
                "active_revision = EXCLUDED.active_revision"
            ),
            {"id": row["id"], "revision": revision},
        )
        record_audit(
            conn,
            operation="provider.config.save",
            actor_id=str(actor["id"]),
            request_id=_request_id(request),
            result_reference=str(row["id"]),
            target_display=base_url,
            details={
                "base_url": base_url,
                "model": model,
                "revision": revision,
                "key_configured": key_present,
                "test_status": "untested",
            },
            result_payload=_masked(row),
            result_status=200,
        )
        return _masked_response(row)


@router.post("/api-settings/test")
def test_settings(body: SettingsTest, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        current = _active(conn)
        if current is None:
            raise HTTPException(404, "Provider settings are not configured.")
        raw_override = _clean(body.base_url)
        target = raw_override or str(current["base_url"])
        api_key: str | None = None
        if current["key_ciphertext"] is not None:
            try:
                api_key = decrypt_api_key(str(current["key_ciphertext"]))
            except ValueError as exc:
                raise HTTPException(500, "Stored provider key is unreadable.") from exc
        try:
            result = check_capabilities(target, api_key, str(current["model"]))
        except ProviderURLBlocked as exc:
            raise HTTPException(422, str(exc)) from None
        passed = bool(
            result["credential_ok"]
            and result["model_ok"]
            and result["tool_ok"]
            and result["json_ok"]
        )
        status = "verified" if passed else "failed"
        conn.execute(
            text(
                "UPDATE provider_configs SET test_status = :status, "
                "last_test_at = now() WHERE id = :id"
            ),
            {"status": status, "id": current["id"]},
        )
        record_audit(
            conn,
            operation="provider.config.test",
            actor_id=str(actor["id"]),
            request_id=_request_id(request),
            result_reference=str(current["id"]),
            target_display=target,
            details={
                "base_url": target,
                "model": str(current["model"]),
                "revision": current["revision"],
                "test_status": status,
            },
            result_payload={
                "schema_version": 1,
                "revision": current["revision"],
                "test_status": status,
                "credential_ok": result["credential_ok"],
                "model_ok": result["model_ok"],
                "tool_ok": result["tool_ok"],
                "json_ok": result["json_ok"],
            },
            result_status=200,
        )
        return JSONResponse(
            {
                "schema_version": 1,
                "credential_ok": result["credential_ok"],
                "model_ok": result["model_ok"],
                "tool_ok": result["tool_ok"],
                "json_ok": result["json_ok"],
                "diagnostic": result["diagnostic"],
            },
            headers={"Cache-Control": "private, no-store"},
        )


def _revision_row(conn: Connection, revision: int) -> Any:
    return (
        conn.execute(
            text("SELECT * FROM provider_configs WHERE revision = :revision"),
            {"revision": revision},
        )
        .mappings()
        .first()
    )


@router.get("/api-settings/versions")
def list_versions(request: Request) -> JSONResponse:
    with db.transaction() as conn:
        require_admin(request, conn)
        rows = (
            conn.execute(text("SELECT * FROM provider_configs ORDER BY revision"))
            .mappings()
            .all()
        )
        return JSONResponse(
            {"schema_version": 1, "items": [_version_item(r) for r in rows]},
            headers={"Cache-Control": "private, no-store"},
        )


@router.get("/api-settings/versions/{revision}")
def get_version(revision: int, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        require_admin(request, conn)
        row = _revision_row(conn, revision)
        if row is None:
            raise HTTPException(404, "Provider configuration revision not found.")
        return JSONResponse(
            _masked(row), headers={"Cache-Control": "private, no-store"}
        )


def _runs_table_exists(conn: Connection) -> bool:
    return bool(
        conn.execute(text("SELECT to_regclass('public.runs') IS NOT NULL")).scalar()
    )


def _revision_referenced_by_run(conn: Connection, revision: int) -> bool:
    """Best-effort check for run references once the S44 runs table exists."""
    if not _runs_table_exists(conn):
        return False
    columns = {
        row[0]
        for row in conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'runs'"
            )
        ).all()
    }
    candidates = [
        column
        for column in (
            "provider_config_revision",
            "provider_revision",
            "config_revision",
        )
        if column in columns
    ]
    for column in candidates:
        count = conn.execute(
            text(f"SELECT COUNT(*) FROM runs WHERE {column} = :revision"),
            {"revision": revision},
        ).scalar()
        if int(count or 0) > 0:
            return True
    return False


@router.delete("/api-settings/versions/{revision}")
def delete_version(revision: int, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        row = _revision_row(conn, revision)
        if row is None:
            raise HTTPException(404, "Provider configuration revision not found.")
        current = _active(conn)
        is_active = current is not None and int(current["revision"]) == revision
        if is_active or _revision_referenced_by_run(conn, revision):
            raise HTTPException(
                409,
                "Revision is active or referenced by runs; it cannot be removed "
                "without explicit affected-run handling. Retire the affected "
                "runs first, then remove this revision.",
            )
        conn.execute(
            text("DELETE FROM provider_configs WHERE revision = :revision"),
            {"revision": revision},
        )
        record_audit(
            conn,
            operation="provider.config.delete",
            actor_id=str(actor["id"]),
            request_id=_request_id(request),
            result_reference=str(row["id"]),
            target_display=str(row["base_url"]),
            details={
                "base_url": str(row["base_url"]),
                "model": str(row["model"]),
                "revision": revision,
            },
            result_payload={"schema_version": 1, "deleted_revision": revision},
            result_status=200,
        )
        return JSONResponse(
            {"schema_version": 1, "deleted_revision": revision},
            headers={"Cache-Control": "private, no-store"},
        )
