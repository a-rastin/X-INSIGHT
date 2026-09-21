"""Identity HTTP routes (S03: login, sessions, own credentials)."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from x_insight import db
from x_insight.contracts import error_body
from x_insight.identity import throttle
from x_insight.identity.hashing import hash_password, verify_password
from x_insight.identity.store import (
    create_session,
    ensure_admin_seeded,
    get_user_by_username,
    get_valid_session,
    normalize_username,
)
from x_insight.operations.audit import record_audit

router = APIRouter()

SESSION_COOKIE = "xinsight_session"
CSRF_COOKIE = "xinsight_csrf"

GENERIC_LOGIN_MESSAGE = "Invalid username, password, or role."

RESEARCH_NOTICE = (
    "This is a research app and is not intended to be used as the sole basis "
    "for treating patients."
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    role: str = Field(min_length=1)


class PreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: str = Field(pattern="^(light|dark)$")


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


def _request_id(request: Request) -> str:
    scope_id = request.scope.get("request_id")
    if isinstance(scope_id, str) and scope_id:
        return scope_id
    return request.headers.get("x-request-id", "unknown")


def _secure_cookie(request: Request) -> bool:
    # Secure under HTTPS; plain on localhost development.
    if request.url.scheme == "https":
        return True
    forwarded = request.headers.get("x-forwarded-proto", "")
    return forwarded.split(",")[0].strip().lower() == "https"


def _session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def _client_key(request: Request, username: str) -> str:
    ip = "unknown"
    try:
        if request.client is not None and request.client.host:
            ip = request.client.host
    except Exception:
        ip = "unknown"
    return f"{normalize_username(username)}|{ip}"


def _generic_login_denied(request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=error_body("UNAUTHENTICATED", GENERIC_LOGIN_MESSAGE, request_id),
    )


def _require_session(
    request: Request, conn: Connection
) -> tuple[JSONResponse | None, Any]:
    token = _session_token(request)
    if not token:
        return (
            JSONResponse(
                status_code=401,
                content=error_body(
                    "UNAUTHENTICATED",
                    "Authentication required.",
                    _request_id(request),
                ),
            ),
            None,
        )
    row = get_valid_session(conn, token)
    if row is None:
        return (
            JSONResponse(
                status_code=401,
                content=error_body(
                    "UNAUTHENTICATED",
                    "Authentication required.",
                    _request_id(request),
                ),
            ),
            None,
        )
    return None, row


def _check_csrf(
    request: Request, session_row: Mapping[str, Any]
) -> JSONResponse | None:
    header = request.headers.get("x-csrf-token")
    expected = str(session_row["csrf_token"])
    if not header or not hmac.compare_digest(header, expected):
        return JSONResponse(
            status_code=403,
            content=error_body(
                "FORBIDDEN", "CSRF token missing or invalid.", _request_id(request)
            ),
        )
    return None


@router.post("/auth/login")
def login(body: LoginRequest, request: Request) -> JSONResponse:
    request_id = _request_id(request)
    key = _client_key(request, body.username)
    if throttle.throttled(key):
        try:
            with db.transaction() as conn:
                probe = get_user_by_username(conn, body.username)
                actor = str(probe["id"]) if probe is not None else None
                ref = actor or normalize_username(body.username)
                record_audit(
                    conn,
                    operation="auth.login_failure",
                    actor_id=actor,
                    request_id=request_id,
                    result_reference=ref,
                )
        except Exception:
            pass
        return JSONResponse(
            status_code=429,
            content=error_body(
                "RATE_LIMITED",
                "Too many login attempts. Retry later.",
                request_id,
                retryable=True,
            ),
        )
    try:
        with db.transaction() as conn:
            ensure_admin_seeded(conn)
            user = get_user_by_username(conn, body.username)
            if user is None or not user["active"]:
                throttle.record_failure(key)
                record_audit(
                    conn,
                    operation="auth.login_failure",
                    actor_id=str(user["id"]) if user is not None else None,
                    request_id=request_id,
                    result_reference=str(user["id"])
                    if user is not None
                    else normalize_username(body.username),
                )
                return _generic_login_denied(request_id)
            # Passwords are compared exactly; never trimmed.
            if not verify_password(body.password, user["password_hash"]):
                throttle.record_failure(key)
                record_audit(
                    conn,
                    operation="auth.login_failure",
                    actor_id=str(user["id"]),
                    request_id=request_id,
                    result_reference=str(user["id"]),
                )
                return _generic_login_denied(request_id)
            if body.role != user["role"]:
                throttle.record_failure(key)
                record_audit(
                    conn,
                    operation="auth.login_failure",
                    actor_id=str(user["id"]),
                    request_id=request_id,
                    result_reference=str(user["id"]),
                )
                return _generic_login_denied(request_id)
            throttle.clear(key)
            token, csrf = create_session(
                conn, str(user["id"]), int(user["credential_revision"])
            )
            record_audit(
                conn,
                operation="auth.login_success",
                actor_id=str(user["id"]),
                request_id=request_id,
                result_reference=str(user["id"]),
            )
            payload: dict[str, object] = {
                "user": {
                    "id": str(user["id"]),
                    "username": user["username"],
                    "role": user["role"],
                    "theme": user["theme"],
                }
            }
            if user["role"] == "physician":
                payload["research_notice"] = RESEARCH_NOTICE
            response = JSONResponse(status_code=200, content=payload)
            secure = _secure_cookie(request)
            response.set_cookie(
                SESSION_COOKIE,
                token,
                httponly=True,
                samesite="lax",
                secure=secure,
                path="/",
            )
            response.set_cookie(
                CSRF_COOKIE,
                csrf,
                httponly=False,
                samesite="lax",
                secure=secure,
                path="/",
            )
            return response
    except Exception:
        return JSONResponse(
            status_code=500,
            content=error_body("INTERNAL_ERROR", "Internal error.", request_id),
        )


@router.get("/me")
def me(request: Request) -> JSONResponse:
    with db.transaction() as conn:
        ensure_admin_seeded(conn)
        denied, row = _require_session(request, conn)
        if denied is not None or row is None:
            assert denied is not None
            return denied
        return JSONResponse(
            status_code=200,
            content={
                "id": str(row["id"]),
                "username": row["username"],
                "role": row["role"],
                "theme": row["theme"],
            },
        )


@router.post("/auth/logout")
def logout(request: Request) -> JSONResponse:
    request_id = _request_id(request)
    with db.transaction() as conn:
        ensure_admin_seeded(conn)
        denied, row = _require_session(request, conn)
        if denied is not None or row is None:
            assert denied is not None
            return denied
        csrf_denied = _check_csrf(request, row)
        if csrf_denied is not None:
            return csrf_denied
        conn.execute(
            text("UPDATE sessions SET revoked_at = now() WHERE id = :i"),
            {"i": str(row["session_id"])},
        )
        record_audit(
            conn,
            operation="auth.logout",
            actor_id=str(row["user_id"]),
            request_id=request_id,
            result_reference=str(row["user_id"]),
        )
        response = JSONResponse(status_code=200, content={"status": "ok"})
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(CSRF_COOKIE, path="/")
        return response


@router.post("/me/password")
def change_password(body: PasswordChangeRequest, request: Request) -> JSONResponse:
    """Change own password; revokes all other sessions, keeps the current one."""
    request_id = _request_id(request)
    with db.transaction() as conn:
        ensure_admin_seeded(conn)
        denied, row = _require_session(request, conn)
        if denied is not None or row is None:
            assert denied is not None
            return denied
        csrf_denied = _check_csrf(request, row)
        if csrf_denied is not None:
            return csrf_denied
        user_id = str(row["user_id"])
        current = (
            conn.execute(
                text(
                    "SELECT password_hash, credential_revision FROM users WHERE id = :i"
                ),
                {"i": user_id},
            )
            .mappings()
            .first()
        )
        assert current is not None
        # Exact comparison; no trimming, no complexity rule.
        if not verify_password(body.current_password, str(current["password_hash"])):
            return JSONResponse(
                status_code=403,
                content=error_body(
                    "FORBIDDEN", "Current password is incorrect.", request_id
                ),
            )
        new_hash = hash_password(body.new_password)
        new_rev = int(current["credential_revision"]) + 1
        conn.execute(
            text(
                "UPDATE users SET password_hash = :h, credential_revision = :r, "
                " updated_at = now() WHERE id = :i"
            ),
            {"h": new_hash, "r": new_rev, "i": user_id},
        )
        conn.execute(
            text(
                "UPDATE sessions SET revoked_at = now() "
                "WHERE user_id = :u AND id != :s AND revoked_at IS NULL"
            ),
            {"u": user_id, "s": str(row["session_id"])},
        )
        conn.execute(
            text("UPDATE sessions SET credential_revision = :r WHERE id = :s"),
            {"r": new_rev, "s": str(row["session_id"])},
        )
        record_audit(
            conn,
            operation="auth.password_change",
            actor_id=user_id,
            request_id=request_id,
            result_reference=user_id,
        )
        return JSONResponse(status_code=200, content={"status": "ok"})


@router.patch("/me/preferences")
def update_preferences(body: PreferencesRequest, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        ensure_admin_seeded(conn)
        denied, row = _require_session(request, conn)
        if denied is not None or row is None:
            assert denied is not None
            return denied
        csrf_denied = _check_csrf(request, row)
        if csrf_denied is not None:
            return csrf_denied
        conn.execute(
            text("UPDATE users SET theme = :t, updated_at = now() WHERE id = :i"),
            {"t": body.theme, "i": str(row["user_id"])},
        )
        updated = (
            conn.execute(
                text("SELECT id, username, role, theme FROM users WHERE id = :i"),
                {"i": str(row["user_id"])},
            )
            .mappings()
            .first()
        )
        assert updated is not None
        return JSONResponse(
            status_code=200,
            content={
                "id": str(updated["id"]),
                "username": updated["username"],
                "role": updated["role"],
                "theme": updated["theme"],
            },
        )
