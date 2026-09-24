"""S57 slice 2 (RED): fresh Linux startup, explicit migrations, one-time
admin seed, fail-soft generation, HTTPS outside localhost.

Scope: docs/dev/tasks.md S57 item 2; seams T1/T8/T9/T10 only. No docker
daemon, no live provider credentials; real PostgreSQL (xinsight_test) via
TestClient for the behavioral slice. SYNTHETIC VALUES ONLY.

Behavior under test (NOT implemented -- expect RED on items 1-3):
1. Fresh-install mechanics: an explicit migration entrypoint exists for
   production (deploy/*.sh running `alembic upgrade head`, or the prod
   compose app/worker running it). The dev-only `make migrate` target
   (no prod compose reference) does NOT satisfy this.
2. One-time admin seed: app startup wires `ensure_admin_seeded` outside
   the login paths, so a fresh database has an admin without any login
   POST first (idempotent: never overwrites an existing password).
3. Fail-soft generation: with NO provider configured and NO bundle
   active, run creation answers with an explicit unavailable-generation
   signal (503/422 with a machine-readable UNAVAILABLE/GENERATION
   code -- never 500/traceback), while chart reads (GET /patients,
   GET /encounters/{id}) and admin reads still succeed.
4. HTTPS outside localhost (green guards from slice 1): plain HTTP only
   for localhost/127.0.0.1, port-80 default_server 301-redirects to
   https, 443 server sets Strict-Transport-Security.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_DIR = REPO_ROOT / "deploy"
PROD_COMPOSE = DEPLOY_DIR / "compose.prod.yaml"
NGINX_CONF = DEPLOY_DIR / "edge" / "nginx.conf"
APP_PY = REPO_ROOT / "backend" / "src" / "x_insight" / "app.py"


@pytest.fixture(autouse=True)
def clean_deployment_startup():
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, runs, run_questions, reasoning_jobs, "
                "reasoning_attempts, run_question_artifacts, run_proposals, "
                "audit_events, model_bundle_pointers, model_bundle_events, "
                "mcp_question_grants, provider_configs, "
                "provider_config_pointer, queue_fairness, ddi_dataset_releases, "
                "networks, network_versions"
            )
        )
    reset_all()
    yield
    reset_all()


def _login(client, username="admin", password="admin", role="admin"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _mutation_headers(client, *, key=None, revision=None):
    headers = {"X-CSRF-Token": client.cookies.get("xinsight_csrf")}
    if key is not None:
        headers["Idempotency-Key"] = key
    if revision is not None:
        headers["If-Match"] = str(revision)
    return headers


# ---------------------------------------------------------------------------
# 1. Fresh-install mechanics: explicit production migration entrypoint.
# ---------------------------------------------------------------------------


def test_prod_migration_entrypoint_exists():
    """S57 item 2 (RED): production has an explicit migration entrypoint."""
    setup_sh = DEPLOY_DIR / "setup.sh"
    setup_runs_migrations = setup_sh.is_file() and (
        "alembic upgrade head" in setup_sh.read_text(encoding="utf-8")
    )
    compose_runs_migrations = PROD_COMPOSE.is_file() and (
        "alembic upgrade head" in PROD_COMPOSE.read_text(encoding="utf-8")
    )
    assert setup_runs_migrations or compose_runs_migrations, (
        "no explicit production migration entrypoint: expected deploy/setup.sh "
        "running `alembic upgrade head` or a prod-compose app/worker migrate "
        "hook (dev-only `make migrate` with no prod compose reference is not "
        "sufficient for fresh Linux startup)"
    )


# ---------------------------------------------------------------------------
# 2. One-time admin seed at startup, without requiring a login first.
# ---------------------------------------------------------------------------


def test_startup_seeds_admin_without_login_first():
    """S57 item 2 (RED): fresh startup seeds the admin without a login POST."""
    # Behavioral (T1): fresh users table, no login attempted yet.
    # (DELETE, not TRUNCATE: encounter_notes FK-blocks truncating users.)
    with db.transaction() as conn:
        conn.execute(text("DELETE FROM sessions"))
        conn.execute(text("DELETE FROM users"))
    with TestClient(app) as anon:
        ready = anon.get("/api/v1/ready")
        assert ready.status_code in (200, 503)
    with db.transaction() as conn:
        admin = conn.execute(
            text("SELECT id FROM users WHERE username = 'admin'")
        ).first()
    assert admin is not None, (
        "fresh startup did not seed the admin without a login first "
        "(ensure_admin_seeded is only reachable via login paths)"
    )
    # Wiring: the application startup path itself must call the seed.
    app_src = APP_PY.read_text(encoding="utf-8")
    assert "ensure_admin_seeded" in app_src, (
        "backend/src/x_insight/app.py never wires ensure_admin_seeded at "
        "startup (only identity/routes.py login paths call it)"
    )


# ---------------------------------------------------------------------------
# 3. Fail-soft generation: unavailable signal, charts/admin still usable.
# ---------------------------------------------------------------------------


def test_failsoft_generation_unavailable_but_charts_usable():
    """S57 item 2 (RED): no provider/bundle -> clean unavailable signal (T1).

    Real PostgreSQL via TestClient: with zero provider_configs and zero
    model_bundle_pointers, POST /encounters/{id}/runs must answer 503/422
    with a machine-readable UNAVAILABLE/GENERATION code (never 500), while
    GET /patients, GET /encounters/{id}, and admin reads still succeed.
    """
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        created = admin.post(
            "/api/v1/physicians",
            json={"username": "s57slicedoc", "password": "secret"},
            headers=_mutation_headers(admin, key="s57-slice2-create-doc"),
        )
        assert created.status_code == 201, created.text
        _login(physician, "s57slicedoc", "secret", "physician")
        made = physician.post(
            "/api/v1/patients",
            json={
                "first_name": "Anna",
                "last_name": "Muller",
                "sex": "F",
                "age": 30,
                "patient_id": "0057000001",
                "clinical_status": "first_time",
            },
            headers=_mutation_headers(physician, key="s57-slice2-patient"),
        )
        assert made.status_code == 201, made.text
        encounter = made.json()["encounter"]
        encounter_id = encounter["id"]
        revision = int(encounter["revision"])

        # Fixture setup (disposable storage init): guarantee NO provider and
        # NO bundle are configured; assertions below stay on T1 HTTP.
        with db.transaction() as conn:
            conn.execute(text("DELETE FROM provider_config_pointer"))
            conn.execute(text("DELETE FROM provider_configs"))
            conn.execute(text("DELETE FROM model_bundle_pointers"))

        # Chart reads stay usable without generation (green guards).
        chart_list = physician.get("/api/v1/patients")
        assert chart_list.status_code == 200, chart_list.text
        chart_read = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert chart_read.status_code == 200, chart_read.text
        admin_read = admin.get("/api/v1/patients")
        assert admin_read.status_code == 200, admin_read.text

        # Run creation must fail soft with an explicit unavailable signal.
        started = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(
                physician, key="s57-slice2-run-1", revision=revision
            ),
        )
        assert started.status_code in (503, 422), (
            f"expected an explicit unavailable-generation signal (503/422), "
            f"got {started.status_code}: {started.text}"
        )
        body = started.json()
        code = str(body.get("code", ""))
        assert "UNAVAIL" in code or "GENERATION" in code, (
            f"expected a machine-readable UNAVAILABLE/GENERATION code, got {body!r}"
        )


# ---------------------------------------------------------------------------
# 4. HTTPS outside localhost (green guards from slice 1).
# ---------------------------------------------------------------------------


def _nginx_text() -> str:
    assert NGINX_CONF.is_file(), f"missing edge config {NGINX_CONF}"
    return NGINX_CONF.read_text(encoding="utf-8")


def test_https_localhost_plain_http_only():
    """S57 item 2 guard: plain HTTP is served for localhost/127.0.0.1."""
    conf = _nginx_text()
    localhost_block = re.search(
        r"server\s*\{\s*listen 80;\s*server_name localhost 127\.0\.0\.1;",
        conf,
    )
    assert localhost_block, "no plain-HTTP localhost server block found"
    start = localhost_block.start()
    depth = 0
    end = start
    for i, ch in enumerate(conf[start:]):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = start + i
                break
    assert "return 301" not in conf[start:end], (
        "localhost plain-HTTP block must not redirect to HTTPS"
    )


def test_https_port80_redirects_outside_localhost():
    """S57 item 2 guard: port-80 default_server 301-redirects to https."""
    conf = _nginx_text()
    assert re.search(r"listen 80 default_server;", conf), (
        "no port-80 default_server block found"
    )
    assert re.search(r"return 301 https://\$host\$request_uri;", conf), (
        "port-80 default_server must 301-redirect to https"
    )


def test_https_hsts_on_443():
    """S57 item 2 guard: 443 server sets Strict-Transport-Security."""
    conf = _nginx_text()
    assert re.search(r"listen 443 ssl;", conf), "no 443 ssl server block found"
    assert "Strict-Transport-Security" in conf, (
        "443 server must set Strict-Transport-Security"
    )
