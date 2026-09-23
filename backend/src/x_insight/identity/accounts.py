"""Admin-only physician commands and safe account reads."""

from collections.abc import Mapping
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from x_insight import db
from x_insight.contracts import (
    canonical_json,
    content_hash,
    parse_idempotency_key,
    parse_if_match,
    to_utc_z,
)
from x_insight.identity.hashing import hash_password, verify_password
from x_insight.identity.routes import _check_csrf, _request_id, _require_session
from x_insight.identity.store import normalize_username
from x_insight.operations.audit import record_audit

router = APIRouter()


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        if not normalize_username(value):
            raise ValueError("Username is required.")
        # Preserve the submitted spelling for idempotency conflict detection.
        # Normalize only when storing the account.
        return value


class AccountEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str | None = Field(default=None, min_length=1)
    password: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def valid_edit(self) -> "AccountEdit":
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Provide nonempty credentials to change.")
        if self.username is not None:
            AccountCreate.valid_username(self.username)
        return self


class DeactivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_action: Literal["retain", "discard"]
    draft_set_revision: str = Field(min_length=1)
    confirm_discard: StrictBool = False

    @model_validator(mode="after")
    def confirmed(self) -> "DeactivateRequest":
        if self.draft_action == "discard" and not self.confirm_discard:
            raise ValueError("Explicit discard confirmation is required.")
        return self


class ReactivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def require_admin(request: Request, conn: Connection) -> Any:
    denied, actor = _require_session(request, conn)
    if denied is not None:
        raise HTTPException(401, "Authentication required.")
    if actor["role"] != "admin":
        raise HTTPException(403, "Administrator access required.")
    if request.method != "GET" and _check_csrf(request, actor) is not None:
        raise HTTPException(403, "CSRF token missing or invalid.")
    return actor


def safe_account(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": str(row["id"]),
        "username": row["username"],
        "role": row["role"],
        "active": row["active"],
        "revision": row["revision"],
    }


def account_response(row: Mapping[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(
        safe_account(row),
        status_code=status,
        headers={"ETag": f'"{row["revision"]}"', "Cache-Control": "private, no-store"},
    )


def physician(conn: Connection, account_id: UUID, *, lock: bool = False) -> Any:
    row = (
        conn.execute(
            text(
                "SELECT * FROM users WHERE id = :id AND role = 'physician'"
                + (" FOR UPDATE" if lock else "")
            ),
            {"id": account_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(404, "Physician not found.")
    return row


def check_revision(request: Request, row: Mapping[str, Any]) -> None:
    if parse_if_match(request.headers) != str(row["revision"]):
        raise HTTPException(412, "Account changed. Reload and reconcile.")


def draft_review(conn: Connection, row: Mapping[str, Any]) -> dict[str, Any]:
    # S51: real non-terminal draft set for the physician, locked in the
    # caller's transaction. Any new draft/review_ready row changes the
    # content hash, so a stale draft_set_revision is rejected with 412.
    rows = (
        conn.execute(
            text(
                "SELECT id, kind, state, revision FROM encounters "
                "WHERE author_id = CAST(:id AS uuid) "
                "AND state IN ('draft', 'review_ready') "
                "ORDER BY created_at, id"
            ),
            {"id": str(row["id"])},
        )
        .mappings()
        .all()
    )
    drafts = [
        {
            "id": str(item["id"]),
            "encounter_id": str(item["id"]),
            "kind": item["kind"],
            "state": item["state"],
            "revision": item["revision"],
        }
        for item in rows
    ]
    review = {
        "schema_version": 1,
        "physician_id": str(row["id"]),
        "account_revision": row["revision"],
        "drafts": drafts,
    }
    return {**review, "draft_set_revision": content_hash(review)}


def _cancel_queued_work(conn: Connection, author_id: UUID) -> None:
    # S51/S47: queued work for a deactivated author is never eligible.
    # Runs go terminal-cancelled (history preserved); queued/claimed jobs
    # leave the claimable pool so no late commit can succeed; outstanding
    # MCP question grants are revoked.
    from x_insight.reasoning.queue import ACTIVE_RUN_STATUSES

    active = ", ".join(f"'{status}'" for status in sorted(ACTIVE_RUN_STATUSES))
    conn.execute(
        text(
            "UPDATE runs SET status = 'cancelled', updated_at = now() "
            "WHERE author_id = CAST(:id AS uuid) "
            f"AND status IN ({active})"
        ),
        {"id": str(author_id)},
    )
    conn.execute(
        text(
            "UPDATE reasoning_jobs SET status = 'cancelled', "
            "lease_token = NULL, lease_deadline = NULL, updated_at = now() "
            "WHERE author_id = CAST(:id AS uuid) "
            "AND status IN ('queued', 'claimed')"
        ),
        {"id": str(author_id)},
    )
    conn.execute(
        text(
            "UPDATE mcp_question_grants SET revoked_at = now(), "
            "updated_at = now() WHERE actor_id = CAST(:id AS uuid) "
            "AND revoked_at IS NULL"
        ),
        {"id": str(author_id)},
    )


def start_command(
    conn: Connection,
    request: Request,
    operation: str,
    body: BaseModel,
    account_id: UUID | None = None,
) -> tuple[dict[str, Any], JSONResponse | None]:
    actor = require_admin(request, conn)
    key = parse_idempotency_key(request.headers)
    if key is None:
        raise HTTPException(422, "A valid Idempotency-Key is required.")
    scope = {
        "actor_id": str(actor["id"]),
        "operation": operation,
        "idempotency_key": key,
    }
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": canonical_json(scope).decode()},
    )
    payload = canonical_json(
        {
            "body": body.model_dump(),
            "target": str(account_id),
            "revision": parse_if_match(request.headers),
        }
    ).decode()
    saved = (
        conn.execute(
            text(
                "SELECT request_hash, result_payload, result_status FROM audit_events "
                "WHERE actor_id = :actor_id AND operation = :operation "
                "AND idempotency_key = :idempotency_key"
            ),
            scope,
        )
        .mappings()
        .first()
    )
    if saved is not None:
        if not verify_password(payload, saved["request_hash"]):
            raise HTTPException(409, "Idempotency key was used for another request.")
        return {}, account_response(saved["result_payload"], saved["result_status"])
    # Credential-bearing command fingerprints need salted, slow hashing too;
    # never put plaintext or a fast password digest in the audit/replay store.
    return {
        **scope,
        "request_hash": hash_password(payload),
        "request_id": _request_id(request),
    }, None


def finish_command(
    conn: Connection,
    command: dict[str, Any],
    row: Mapping[str, Any],
    status: int = 200,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    record_audit(
        conn,
        **command,
        result_reference=str(row["id"]),
        target_display=row["username"],
        details=details,
        result_payload=safe_account(row),
        result_status=status,
    )
    return account_response(row, status)


@router.get("/physicians")
def list_physicians(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: UUID | None = None,
) -> JSONResponse:
    with db.transaction() as conn:
        require_admin(request, conn)
        rows = (
            conn.execute(
                text(
                    "SELECT * FROM users WHERE role = 'physician' "
                    "AND (CAST(:cursor AS uuid) IS NULL OR id > :cursor) "
                    "ORDER BY id LIMIT :limit"
                ),
                {"cursor": cursor, "limit": limit + 1},
            )
            .mappings()
            .all()
        )
        return JSONResponse(
            {
                "schema_version": 1,
                "items": [safe_account(r) for r in rows[:limit]],
                "next_cursor": str(rows[limit - 1]["id"])
                if len(rows) > limit
                else None,
            },
            headers={"Cache-Control": "private, no-store"},
        )


@router.get("/physicians/{account_id}")
def get_physician(account_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        require_admin(request, conn)
        return account_response(physician(conn, account_id))


@router.get("/physicians/{account_id}/deactivation-review")
def review_deactivation(account_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        require_admin(request, conn)
        return JSONResponse(
            draft_review(conn, physician(conn, account_id)),
            headers={"Cache-Control": "private, no-store"},
        )


@router.post("/physicians")
def create_physician(body: AccountCreate, request: Request) -> JSONResponse:
    try:
        with db.transaction() as conn:
            command, replay = start_command(conn, request, "physician.create", body)
            if replay is not None:
                return replay
            row = (
                conn.execute(
                    text(
                        "INSERT INTO users (username, role, password_hash) "
                        "VALUES (:username, 'physician', :password_hash) RETURNING *"
                    ),
                    {
                        "username": normalize_username(body.username),
                        "password_hash": hash_password(body.password),
                    },
                )
                .mappings()
                .one()
            )
            return finish_command(conn, command, row, 201)
    except IntegrityError as exc:
        if (
            getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            != "ix_users_username"
        ):
            raise
        raise HTTPException(409, "Username already exists.") from None


@router.patch("/physicians/{account_id}")
def edit_physician(
    account_id: UUID, body: AccountEdit, request: Request
) -> JSONResponse:
    try:
        with db.transaction() as conn:
            command, replay = start_command(
                conn, request, "physician.edit", body, account_id
            )
            if replay is not None:
                return replay
            current = physician(conn, account_id, lock=True)
            check_revision(request, current)
            row = (
                conn.execute(
                    text(
                        "UPDATE users SET username = COALESCE(:username, username), "
                        "password_hash = COALESCE(:password_hash, password_hash), "
                        "revision = revision + 1, "
                        "credential_revision = credential_revision + 1, "
                        "updated_at = now() "
                        "WHERE id = :id RETURNING *"
                    ),
                    {
                        "id": account_id,
                        "username": normalize_username(body.username)
                        if body.username is not None
                        else None,
                        "password_hash": hash_password(body.password)
                        if body.password is not None
                        else None,
                    },
                )
                .mappings()
                .one()
            )
            conn.execute(
                text(
                    "UPDATE sessions SET revoked_at = now() "
                    "WHERE user_id = :id AND revoked_at IS NULL"
                ),
                {"id": account_id},
            )
            return finish_command(conn, command, row)
    except IntegrityError as exc:
        if (
            getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            != "ix_users_username"
        ):
            raise
        raise HTTPException(409, "Username already exists.") from None


def change_active(
    account_id: UUID,
    request: Request,
    *,
    active: bool,
    disposition: DeactivateRequest | None = None,
) -> JSONResponse:
    with db.transaction() as conn:
        operation = "physician.reactivate" if active else "physician.deactivate"
        command, replay = start_command(
            conn, request, operation, disposition or ReactivateRequest(), account_id
        )
        if replay is not None:
            return replay
        current = physician(conn, account_id, lock=True)
        check_revision(request, current)
        if current["active"] == active:
            raise HTTPException(409, "Account is already in that state.")
        if (
            disposition is not None
            and disposition.draft_set_revision
            != draft_review(conn, current)["draft_set_revision"]
        ):
            raise HTTPException(412, "Draft review changed. Review it again.")
        if (
            not active
            and disposition is not None
            and disposition.draft_action == "discard"
        ):
            # Explicitly confirmed discard only: tombstone the author's
            # non-terminal drafts in place (content + author preserved,
            # revision bumped). Retain leaves drafts untouched. Discarded
            # rows are terminal and never resurrected by reactivation.
            conn.execute(
                text(
                    "UPDATE encounters SET state = 'discarded', "
                    "revision = revision + 1, updated_at = now() "
                    "WHERE author_id = CAST(:id AS uuid) "
                    "AND state IN ('draft', 'review_ready')"
                ),
                {"id": str(account_id)},
            )
        if not active:
            _cancel_queued_work(conn, account_id)
        row = (
            conn.execute(
                text(
                    "UPDATE users SET active = :active, revision = revision + 1, "
                    "credential_revision = credential_revision + 1, updated_at = now() "
                    "WHERE id = :id RETURNING *"
                ),
                {"id": account_id, "active": active},
            )
            .mappings()
            .one()
        )
        conn.execute(
            text(
                "UPDATE sessions SET revoked_at = now() "
                "WHERE user_id = :id AND revoked_at IS NULL"
            ),
            {"id": account_id},
        )
        return finish_command(
            conn,
            command,
            row,
            details=disposition.model_dump() if disposition else None,
        )


@router.post("/physicians/{account_id}/deactivate")
def deactivate(
    account_id: UUID, body: DeactivateRequest, request: Request
) -> JSONResponse:
    return change_active(account_id, request, active=False, disposition=body)


@router.post("/physicians/{account_id}/reactivate")
def reactivate(
    account_id: UUID, request: Request, body: ReactivateRequest = ReactivateRequest()
) -> JSONResponse:
    return change_active(account_id, request, active=True)


@router.get("/audit-events")
def list_audit_events(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: UUID | None = None,
    operation: str | None = None,
) -> JSONResponse:
    # S04 safe account-audit read; S52 completes filters, views and DB grants.
    with db.transaction() as conn:
        require_admin(request, conn)
        rows = (
            conn.execute(
                text(
                    "SELECT id, occurred_at, actor_id, actor_display, operation, "
                    "result_reference, target_display, details, request_id "
                    "FROM audit_events WHERE "
                    "(CAST(:operation AS text) IS NULL OR operation = :operation) "
                    "AND (CAST(:cursor AS uuid) IS NULL OR (occurred_at, id) > "
                    "(SELECT occurred_at, id FROM audit_events WHERE id = :cursor)) "
                    "ORDER BY occurred_at, id LIMIT :limit"
                ),
                {"operation": operation, "cursor": cursor, "limit": limit + 1},
            )
            .mappings()
            .all()
        )
        return JSONResponse(
            {
                "schema_version": 1,
                "items": [
                    {**r, "id": str(r["id"]), "occurred_at": to_utc_z(r["occurred_at"])}
                    for r in rows[:limit]
                ],
                "next_cursor": str(rows[limit - 1]["id"])
                if len(rows) > limit
                else None,
            },
            headers={"Cache-Control": "private, no-store"},
        )
