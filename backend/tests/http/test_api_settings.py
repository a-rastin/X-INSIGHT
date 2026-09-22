"""S42 provider settings red tests (T1/T7, real PostgreSQL, real HTTP).

Assumed contracts (no implementation exists yet; all fail 404 in red phase):
- PUT /api/v1/api-settings {base_url, model, key_action, api_key?}
  key_action in {"replace","unchanged","clear"}; replace requires api_key;
  the redacted placeholder "****" is never accepted as a real key.
- GET /api/v1/api-settings -> {base_url, model, revision, key_configured,
  test_status} with ETag revision header; never echoes the key. test_status
  in {"untested","verified","failed"}; saving never marks verified.
- POST /api/v1/api-settings/test -> {credential_ok, model_ok, tool_ok,
  json_ok, diagnostic}; no secret echo; uses the real HTTP client against
  base_url (one inbound request per test call).
- GET /api/v1/api-settings/versions lists revisions;
  GET /api/v1/api-settings/versions/{revision} reads one old revision;
  DELETE .../versions/{revision} of an active/referenced revision fails
  explicitly (400/409/422 with affected-run hint).
- PUT requires If-Match of the current revision once a revision exists;
  stale/missing revisions fail 412. Admin only (physician 403, anonymous 401).
  Mutations require the X-CSRF-Token header; no Idempotency-Key required.
- Operator flag X_INSIGHT_PROVIDER_ALLOW_LOCAL=true permits http://localhost
  / http://127.0.0.1 destinations, read per request. Forbidden: non-http(s)
  schemes, metadata/link-local hosts and redirects resolving to them.
- Storage table names are not pinned: the encryption assertion scans every
  public.provider% table for the plaintext instead of naming columns.

All secrets are synthetic fixtures; no live provider is ever called: the
only outbound HTTP targets are in-test localhost servers or rejected
forbidden URLs that must fail before any request is sent.
"""

from __future__ import annotations

import http.server
import socketserver
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all

FORBIDDEN_BASE_URLS = [
    "file:///etc/passwd",
    "ftp://example.com/model",
    "http://169.254.169.254/latest/meta-data/",
    "http://metadata.google.internal/",
]

PLACEHOLDER_KEY = "****"
SYNTHETIC_KEY = "synthetic-provider-key-s42-001"
SYNTHETIC_KEY_2 = "synthetic-provider-key-s42-002"


@pytest.fixture(autouse=True)
def clean_settings():
    _truncate_all()
    reset_all()
    yield
    reset_all()


def _truncate_all() -> None:
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, audit_events"
            )
        )
        provider_tables = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename LIKE 'provider%'"
                )
            ).all()
        ]
    for table in provider_tables:
        with db.transaction() as conn:
            conn.execute(text(f"TRUNCATE {table}"))


def login(client: TestClient, username="admin", password="admin", role="admin"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 200, response.text
    return response.json()


def csrf_headers(client: TestClient, etag: str | None = None) -> dict[str, str]:
    headers = {"X-CSRF-Token": client.cookies.get("xinsight_csrf")}
    if etag is not None:
        headers["If-Match"] = etag
    return headers


def create_physician(
    admin: TestClient, username: str, password: str = "synthetic-secret"
):
    response = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": password},
        headers={
            "X-CSRF-Token": admin.cookies.get("xinsight_csrf"),
            "Idempotency-Key": f"s42-{username}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def revision_of(response) -> str:
    body = response.json()
    assert "revision" in body, response.text
    return str(body["revision"])


def etag_of(response) -> str:
    return (response.headers.get("etag") or "").strip().strip('"')


class _ProbeHandler(http.server.BaseHTTPRequestHandler):
    """Synthetic OpenAI-compatible probe: /capable, /redirect, else 404."""

    seen: list = []

    def _record(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.seen.append(
            {"method": self.command, "path": self.path, "length": len(body)}
        )
        return body

    def _send_json(self, payload: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self._record()
        if self.path == "/redirect":
            self.send_response(307)
            self.send_header("Location", "http://169.254.169.254/forbidden")
            self.end_headers()
            return
        if self.path == "/capable":
            self._send_json(
                b'{"choices": [{"message": {"role": "assistant", '
                b'"content": "{\\"ok\\": true}", "tool_calls": '
                b'[{"id": "call_1", "type": "function", "function": '
                b'{"name": "noop", "arguments": "{}"}}]}}], '
                b'"model": "synthetic-model"}'
            )
            return
        self.send_response(404)
        self.end_headers()

    do_POST = do_GET

    def log_message(self, *args) -> None:  # suppress stderr noise
        pass


@pytest.fixture()
def probe_server():
    seen: list = []
    handler = type("BoundProbe", (_ProbeHandler,), {"seen": seen})
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    try:
        host, port = server.server_address
        yield {"base": f"http://{host}:{port}", "seen": seen}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _provider_text_contains(conn, needle: str) -> bool:
    tables = [
        row[0]
        for row in conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename LIKE 'provider%'"
            )
        ).all()
    ]
    assert tables, "provider settings were not persisted to any provider% table"
    for table in tables:
        rows = conn.execute(text(f"SELECT * FROM {table}")).mappings().all()
        for row in rows:
            for value in row.values():
                raw = bytes(value) if isinstance(value, (bytes, bytearray)) else None
                if raw is not None and needle.encode() in raw:
                    return True
                if isinstance(value, str) and needle in value:
                    return True
                if isinstance(value, dict) and needle in str(value):
                    return True
    return False


# Slice 1: masked admin save, explicit key actions, revision fencing, encryption.


def test_admin_saves_settings_masked_with_explicit_key_actions_and_revision():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "drsliceone")
        login(physician, "drsliceone", "synthetic-secret", "physician")

        assert physician.get("/api/v1/api-settings").status_code == 403
        assert (
            physician.put(
                "/api/v1/api-settings",
                json={"base_url": "https://example.com/v1", "model": "m"},
                headers=csrf_headers(physician),
            ).status_code
            == 403
        )

        saved = admin.put(
            "/api/v1/api-settings",
            json={
                "base_url": "https://provider.example/v1",
                "model": "synthetic-model",
                "key_action": "replace",
                "api_key": SYNTHETIC_KEY,
            },
            headers=csrf_headers(admin),
        )
        assert saved.status_code == 200, saved.text
        assert SYNTHETIC_KEY not in saved.text
        rev1 = revision_of(saved)

        current = admin.get("/api/v1/api-settings")
        assert current.status_code == 200, current.text
        body = current.json()
        assert body["key_configured"] is True
        assert body["base_url"] == "https://provider.example/v1"
        assert body["model"] == "synthetic-model"
        assert SYNTHETIC_KEY not in current.text
        assert "api_key" not in current.json()

        # Replace requires a real key; the redacted placeholder never counts.
        assert (
            admin.put(
                "/api/v1/api-settings",
                json={
                    "base_url": "https://provider.example/v1",
                    "model": "synthetic-model",
                    "key_action": "replace",
                },
                headers=csrf_headers(admin, etag_of(current) or rev1),
            ).status_code
            == 422
        )
        assert (
            admin.put(
                "/api/v1/api-settings",
                json={
                    "base_url": "https://provider.example/v1",
                    "model": "synthetic-model",
                    "key_action": "replace",
                    "api_key": PLACEHOLDER_KEY,
                },
                headers=csrf_headers(admin, etag_of(current) or rev1),
            ).status_code
            == 422
        )

        # Unchanged preserves the stored key without re-sending it.
        kept = admin.put(
            "/api/v1/api-settings",
            json={
                "base_url": "https://provider.example/v1",
                "model": "synthetic-model-2",
                "key_action": "unchanged",
            },
            headers=csrf_headers(admin, etag_of(current) or rev1),
        )
        assert kept.status_code == 200, kept.text
        assert admin.get("/api/v1/api-settings").json()["key_configured"] is True

        # Explicit clear removes the key.
        cleared = admin.put(
            "/api/v1/api-settings",
            json={"key_action": "clear"},
            headers=csrf_headers(admin, etag_of(kept) or revision_of(kept)),
        )
        assert cleared.status_code == 200, cleared.text
        assert admin.get("/api/v1/api-settings").json()["key_configured"] is False

        # Stale revision fencing on a live revision.
        resaved = admin.put(
            "/api/v1/api-settings",
            json={
                "base_url": "https://provider.example/v1",
                "model": "synthetic-model",
                "key_action": "replace",
                "api_key": SYNTHETIC_KEY_2,
            },
            headers=csrf_headers(admin, etag_of(cleared) or revision_of(cleared)),
        )
        assert resaved.status_code == 200, resaved.text
        assert (
            admin.put(
                "/api/v1/api-settings",
                json={"key_action": "clear"},
                headers=csrf_headers(admin, "stale-revision"),
            ).status_code
            == 412
        )

        # Encrypted at rest: plaintext appears nowhere via HTTP or in storage.
        assert SYNTHETIC_KEY_2 not in admin.get("/api/v1/api-settings").text
        with db.transaction() as conn:
            assert not _provider_text_contains(conn, SYNTHETIC_KEY_2)


# Slice 2: allowlist enforced by the real HTTP client; allowed local works.


def test_forbidden_destinations_rejected_and_allowed_local_succeeds(
    probe_server, monkeypatch
):
    with TestClient(app) as admin:
        login(admin)
        admin.put(
            "/api/v1/api-settings",
            json={
                "base_url": "https://provider.example/v1",
                "model": "synthetic-model",
                "key_action": "replace",
                "api_key": SYNTHETIC_KEY,
            },
            headers=csrf_headers(admin),
        )

        for forbidden in FORBIDDEN_BASE_URLS:
            test_response = admin.post(
                "/api/v1/api-settings/test",
                json={"base_url": forbidden},
                headers=csrf_headers(admin),
            )
            assert test_response.status_code in (400, 422), (
                forbidden,
                test_response.status_code,
                test_response.text,
            )
            save_response = admin.put(
                "/api/v1/api-settings",
                json={
                    "base_url": forbidden,
                    "model": "synthetic-model",
                    "key_action": "unchanged",
                },
                headers=csrf_headers(admin),
            )
            assert save_response.status_code in (400, 422), (
                forbidden,
                save_response.status_code,
                save_response.text,
            )

        monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
        redirect_response = admin.post(
            "/api/v1/api-settings/test",
            json={"base_url": f"{probe_server['base']}/redirect"},
            headers=csrf_headers(admin),
        )
        assert redirect_response.status_code in (400, 422), redirect_response.text

        before = len(probe_server["seen"])
        allowed = admin.post(
            "/api/v1/api-settings/test",
            json={"base_url": f"{probe_server['base']}/capable"},
            headers=csrf_headers(admin),
        )
        assert allowed.status_code == 200, allowed.text
        assert len(probe_server["seen"]) > before


# Slice 3: synthetic capability exchange; save claims nothing; one client path.


def test_capability_exchange_reports_support_without_claiming_on_save(
    probe_server, monkeypatch
):
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    with TestClient(app) as admin:
        login(admin)
        saved = admin.put(
            "/api/v1/api-settings",
            json={
                "base_url": f"{probe_server['base']}/capable",
                "model": "synthetic-model",
                "key_action": "replace",
                "api_key": SYNTHETIC_KEY,
            },
            headers=csrf_headers(admin),
        )
        assert saved.status_code == 200, saved.text
        stored = admin.get("/api/v1/api-settings").json()
        assert stored["test_status"] == "untested"
        assert stored.get("last_test") is None

        before = len(probe_server["seen"])
        tested = admin.post(
            "/api/v1/api-settings/test", json={}, headers=csrf_headers(admin)
        )
        assert tested.status_code == 200, tested.text
        result = tested.json()
        for field in ("credential_ok", "model_ok", "tool_ok", "json_ok"):
            assert isinstance(result[field], bool), result
        assert result["diagnostic"]
        assert SYNTHETIC_KEY not in tested.text
        # Exactly one adapter request per test call: no second permanent client.
        assert len(probe_server["seen"]) == before + 1

        assert admin.get("/api/v1/api-settings").json()["test_status"] in (
            "verified",
            "failed",
        )


# Slice 4: version retention, explicit removal handling, redacted audit.


def test_config_versions_retained_with_explicit_removal_and_redacted_audit():
    with TestClient(app) as admin:
        login(admin)
        first = admin.put(
            "/api/v1/api-settings",
            json={
                "base_url": "https://provider.example/v1",
                "model": "synthetic-model-a",
                "key_action": "replace",
                "api_key": SYNTHETIC_KEY,
            },
            headers=csrf_headers(admin),
        )
        assert first.status_code == 200, first.text
        rev1 = revision_of(first)

        second = admin.put(
            "/api/v1/api-settings",
            json={
                "base_url": "https://provider.example/v1",
                "model": "synthetic-model-b",
                "key_action": "unchanged",
            },
            headers=csrf_headers(admin, etag_of(first) or rev1),
        )
        assert second.status_code == 200, second.text
        rev2 = revision_of(second)
        assert rev2 != rev1

        versions = admin.get("/api/v1/api-settings/versions")
        assert versions.status_code == 200, versions.text
        revisions = [str(item.get("revision")) for item in versions.json()["items"]]
        assert rev1 in revisions and rev2 in revisions

        old = admin.get(f"/api/v1/api-settings/versions/{rev1}")
        assert old.status_code == 200, old.text
        assert old.json()["model"] == "synthetic-model-a"
        assert SYNTHETIC_KEY not in old.text

        cleared = admin.put(
            "/api/v1/api-settings",
            json={"key_action": "clear"},
            headers=csrf_headers(admin, etag_of(second) or rev2),
        )
        assert cleared.status_code == 200, cleared.text
        retained = admin.get("/api/v1/api-settings/versions").json()["items"]
        assert {rev1, rev2} <= {str(item.get("revision")) for item in retained}

        delete_active = admin.delete(
            f"/api/v1/api-settings/versions/{revision_of(cleared)}",
            headers=csrf_headers(admin),
        )
        assert delete_active.status_code in (400, 409, 422), delete_active.text
        lowered = delete_active.text.lower()
        assert "run" in lowered or "referenc" in lowered or "affect" in lowered

        audit = admin.get("/api/v1/audit-events")
        assert audit.status_code == 200, audit.text
        assert SYNTHETIC_KEY not in audit.text
