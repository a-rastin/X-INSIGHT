"""Identity persistence: users, sessions, singleton admin seed.

Usernames are normalized with strip().lower() for uniqueness/lookup; passwords
are never trimmed. Sessions store only SHA-256 of the opaque token.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from x_insight.identity.hashing import hash_password

ADMIN_USERNAME = "admin"
ADMIN_ROLE = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"


def normalize_username(username: str) -> str:
    """Normalize for uniqueness/lookup (passwords never use this)."""
    return username.strip().lower()


def token_hash(token: str) -> str:
    """SHA-256 hex of the opaque session token (stored server-side)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_admin_seeded(conn: Connection) -> None:
    """Insert the singleton admin once; never overwrite an existing password.

    Idempotent: second call preserves a changed password. The partial unique
    index on role='admin' rejects a second admin row at the database level.
    """
    existing = conn.execute(
        text("SELECT id FROM users WHERE username = :u"),
        {"u": ADMIN_USERNAME},
    ).first()
    if existing is not None:
        return
    default_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
    conn.execute(
        text(
            "INSERT INTO users (username, role, active, password_hash, "
            " credential_revision, theme) "
            "VALUES (:u, :r, TRUE, :h, 1, 'light') "
            "ON CONFLICT DO NOTHING"
        ),
        {"u": ADMIN_USERNAME, "r": ADMIN_ROLE, "h": default_hash},
    )


def get_user_by_username(conn: Connection, username: str) -> Any | None:
    """Return the user row for a raw username (normalized), or None."""
    return (
        conn.execute(
            text("SELECT * FROM users WHERE username = :u"),
            {"u": normalize_username(username)},
        )
        .mappings()
        .first()
    )


def get_user_by_id(conn: Connection, user_id: str) -> Any | None:
    """Return the user row by UUID text, or None."""
    return (
        conn.execute(
            text("SELECT * FROM users WHERE id = :i"),
            {"i": user_id},
        )
        .mappings()
        .first()
    )


def create_session(conn: Connection, user_id: str, cred_rev: int) -> tuple[str, str]:
    """Create a session; return (opaque_token, csrf_token)."""
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    conn.execute(
        text(
            "INSERT INTO sessions (user_id, token_hash, csrf_token, "
            " credential_revision) "
            "VALUES (:uid, :th, :csrf, :rev)"
        ),
        {"uid": user_id, "th": token_hash(token), "csrf": csrf, "rev": cred_rev},
    )
    return token, csrf


def get_valid_session(conn: Connection, token: str) -> Any | None:
    """Return session+user when active, unrevoked, revision-matching; else None.

    No idle/absolute timeout is applied (NFR-02). Active-account and revision
    checks are the only lifetime gates besides explicit revocation.
    """
    row = (
        conn.execute(
            text(
                "SELECT s.id AS session_id, s.user_id, s.csrf_token, "
                " s.credential_revision AS session_rev, s.revoked_at, "
                " u.id AS id, u.username, u.role, u.active, "
                " u.credential_revision AS user_rev, u.theme "
                "FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = :th"
            ),
            {"th": token_hash(token)},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    if row["revoked_at"] is not None:
        return None
    if not row["active"]:
        return None
    if row["session_rev"] != row["user_rev"]:
        return None
    return row
