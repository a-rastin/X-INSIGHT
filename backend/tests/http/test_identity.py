"""S03 identity suite (T1, real PostgreSQL). Slices grow cumulatively."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from x_insight import db
from x_insight.app import app
from x_insight.identity.hashing import hash_password, verify_password
from x_insight.identity.store import ensure_admin_seeded


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clean_identity():
    from x_insight.identity.throttle import reset_all

    try:
        with db.transaction() as conn:
            conn.execute(
                text(
                    "TRUNCATE encounter_notes, sessions, users, "
                    "patients, encounters, audit_events"
                )
            )
    except Exception:
        pass
    reset_all()
    yield
    try:
        with db.transaction() as conn:
            conn.execute(
                text(
                    "TRUNCATE encounter_notes, sessions, users, "
                    "patients, encounters, audit_events"
                )
            )
    except Exception:
        pass
    reset_all()


def _login(client: TestClient, username="admin", password="admin", role="admin"):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )


# Slice 1: singleton seeding + hashing.


def test_fresh_database_permits_admin_admin() -> None:
    with _client() as client:
        response = _login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "admin"
    assert "password" not in response.text.lower()
    assert "hash" not in response.text.lower()


def test_second_initialization_preserves_changed_password() -> None:
    new_hash = hash_password("changed-secret")
    with db.transaction() as conn:
        ensure_admin_seeded(conn)
        conn.execute(
            text("UPDATE users SET password_hash = :h WHERE username = 'admin'"),
            {"h": new_hash},
        )
    # Second initialization (triggered by next login) must not restore admin/admin.
    with _client() as client:
        assert _login(client, password="admin").status_code == 401
        assert _login(client, password="changed-secret").status_code == 200


def test_no_second_admin_can_be_provisioned() -> None:
    with db.transaction() as conn:
        ensure_admin_seeded(conn)
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO users (username, role, active, password_hash) "
                    "VALUES ('admin2', 'admin', TRUE, 'x')"
                )
            )


def test_admin_password_is_hashed() -> None:
    with db.transaction() as conn:
        ensure_admin_seeded(conn)
        stored = conn.execute(
            text("SELECT password_hash FROM users WHERE username = 'admin'")
        ).scalar_one()
    assert stored != "admin"
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password("admin", str(stored))
    assert not verify_password("Admin", str(stored))


# Slice 2: opaque cookie session + /me, generic errors, active checks, CSRF, throttling.


def test_login_sets_opaque_cookie_and_me() -> None:
    with _client() as client:
        login = _login(client)
        assert login.status_code == 200
        raw_cookie = login.headers.get("set-cookie", "")
        assert "xinsight_session=" in raw_cookie.lower()
        assert "httponly" in raw_cookie.lower()
        assert "samesite=lax" in raw_cookie.lower()
        session_cookie = login.cookies.get("xinsight_session")
        assert session_cookie and session_cookie != "admin"
        assert "admin" not in session_cookie
        me = client.get("/api/v1/me")
        assert me.status_code == 200
        assert me.json()["username"] == "admin"
        assert "password" not in me.text.lower()
        assert "hash" not in me.text.lower()


def test_wrong_credentials_and_role_mismatch_share_generic_error() -> None:
    with _client() as client:
        wrong_pw = _login(client, password="wrong")
        unknown = _login(client, username="nobody", password="x")
        wrong_role = _login(client, role="physician")
        for response in (wrong_pw, unknown, wrong_role):
            assert response.status_code == 401
            body = response.json()
            assert body["code"] == "UNAUTHENTICATED"
            assert body["message"] == "Invalid username, password, or role."
        # No session was granted.
        assert client.get("/api/v1/me").status_code == 401


def test_inactive_account_cannot_login() -> None:
    with db.transaction() as conn:
        ensure_admin_seeded(conn)
        conn.execute(text("UPDATE users SET active = FALSE WHERE username = 'admin'"))
    with _client() as client:
        response = _login(client)
        assert response.status_code == 401
        assert response.json()["message"] == "Invalid username, password, or role."


def test_mutation_requires_csrf_token() -> None:
    with _client() as client:
        assert _login(client).status_code == 200
        # Missing CSRF header must be denied.
        denied = client.patch("/api/v1/me/preferences", json={"theme": "dark"})
        assert denied.status_code == 403
        csrf = client.cookies.get("xinsight_csrf")
        assert csrf
        allowed = client.patch(
            "/api/v1/me/preferences",
            json={"theme": "dark"},
            headers={"X-CSRF-Token": csrf},
        )
        assert allowed.status_code == 200
        assert allowed.json()["theme"] == "dark"


def test_login_throttling_returns_429() -> None:
    with _client() as client:
        for _ in range(5):
            assert _login(client, password="wrong").status_code == 401
        throttled = _login(client, password="wrong")
        assert throttled.status_code == 429
        assert throttled.json()["code"] == "RATE_LIMITED"


# Slice 3: logout/password revocation, no timeout.


def test_logout_revokes_current_session() -> None:
    with _client() as client:
        assert _login(client).status_code == 200
        assert client.get("/api/v1/me").status_code == 200
        csrf = client.cookies.get("xinsight_csrf")
        logout = client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf or ""}
        )
        assert logout.status_code == 200
        assert client.get("/api/v1/me").status_code == 401


def test_password_change_revokes_prior_sessions() -> None:
    with _client() as first, _client() as second:
        assert _login(first).status_code == 200
        assert _login(second).status_code == 200
        csrf = first.cookies.get("xinsight_csrf")
        change = first.post(
            "/api/v1/me/password",
            json={"current_password": "admin", "new_password": "new-secret-1"},
            headers={"X-CSRF-Token": csrf or ""},
        )
        assert change.status_code == 200
        # Prior session on the second client is revoked; current stays valid.
        assert second.get("/api/v1/me").status_code == 401
        assert first.get("/api/v1/me").status_code == 200
        # Old password no longer works; new password does.
        with _client() as probe:
            assert _login(probe, password="admin").status_code == 401
            assert _login(probe, password="new-secret-1").status_code == 200


def test_session_has_no_idle_or_absolute_timeout() -> None:
    from x_insight.identity import clock

    with _client() as client:
        assert _login(client).status_code == 200
        assert client.get("/api/v1/me").status_code == 200
        base = clock.now()
        clock.set_now_fn(lambda: base + 30 * 24 * 3600.0)
        try:
            assert client.get("/api/v1/me").status_code == 200
        finally:
            clock.reset_now_fn()


def test_password_change_has_no_complexity_rule() -> None:
    with _client() as client:
        assert _login(client).status_code == 200
        csrf = client.cookies.get("xinsight_csrf")
        # Single-character password is allowed: no complexity rule.
        change = client.post(
            "/api/v1/me/password",
            json={"current_password": "admin", "new_password": "x"},
            headers={"X-CSRF-Token": csrf or ""},
        )
        assert change.status_code == 200


# Slice 4: username immutability, no self-registration, no trimming, audit safety.


def test_admin_username_mutation_is_denied() -> None:
    with _client() as client:
        assert _login(client).status_code == 200
        csrf = client.cookies.get("xinsight_csrf")
        response = client.patch(
            "/api/v1/me/preferences",
            json={"theme": "dark", "username": "hacker"},
            headers={"X-CSRF-Token": csrf or ""},
        )
        assert response.status_code == 422
        assert client.get("/api/v1/me").json()["username"] == "admin"


def test_self_registration_is_denied() -> None:
    with _client() as client:
        for path, body in (
            ("/api/v1/physicians", {"username": "doc", "password": "x"}),
            ("/api/v1/auth/register", {"username": "doc", "password": "x"}),
        ):
            response = client.post(path, json=body)
            assert response.status_code in (401, 403, 404, 405)


def test_empty_password_fails_without_trimming() -> None:
    with _client() as client:
        empty = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "", "role": "admin"},
        )
        assert empty.status_code == 422
    # Passwords with surrounding spaces are preserved, not trimmed.
    with db.transaction() as conn:
        from x_insight.identity.hashing import hash_password as _hp

        ensure_admin_seeded(conn)
        conn.execute(
            text("UPDATE users SET password_hash = :h WHERE username = 'admin'"),
            {"h": _hp(" secret ")},
        )
    with _client() as client:
        assert _login(client, password="secret").status_code == 401
        assert _login(client, password=" secret ").status_code == 200


def _audit_rows():
    with db.transaction() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT operation, actor_id, result_reference "
                    "FROM audit_events ORDER BY occurred_at"
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]


def test_audit_records_success_and_failure_without_credentials() -> None:
    with _client() as client:
        assert _login(client, password="wrong").status_code == 401
        assert _login(client).status_code == 200
        csrf = client.cookies.get("xinsight_csrf")
        assert (
            client.post(
                "/api/v1/me/password",
                json={"current_password": "admin", "new_password": "audit-secret"},
                headers={"X-CSRF-Token": csrf or ""},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf or ""}
            ).status_code
            == 200
        )
    rows = _audit_rows()
    operations = [r["operation"] for r in rows]
    assert "auth.login_failure" in operations
    assert "auth.login_success" in operations
    assert "auth.password_change" in operations
    assert "auth.logout" in operations
    blob = " ".join(str(v) for r in rows for v in r.values() if v is not None)
    assert "wrong" not in blob
    assert "audit-secret" not in blob
    # No password hash material in audit payloads.
    assert "pbkdf2" not in blob
