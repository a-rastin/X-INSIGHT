"""S57 slice 4 (RED): independent restarts, queue recovery, health, log hygiene.

Scope: docs/dev/tasks.md S57 item 4; seams T1/T8/T9/T10 only. Real
PostgreSQL (xinsight_test) via TestClient for the behavioral slices. No
docker daemon, no live provider credentials. SYNTHETIC VALUES ONLY.

Slices:
1. App restart preserves an acknowledged draft (T1).
2. Worker restart recovers an expired lease via the public run_once/queue
   claim API at a coarse level (T8). Coverage note: lease-expiry reclaim
   with old-token fencing is already covered in depth by
   backend/tests/worker/test_queue.py::test_expired_lease_reclaimed_old_token_cannot_commit
   (public run_once + queue.complete_job + T1 GET); S47's
   backend/tests/worker/test_recovery.py covers retry budgets, not leases.
   This test does NOT duplicate those internals: one expired claimed job
   (setup-only direct SQL), one simulated worker restart, one run_once
   reclaim asserting same job / fresh token / fencing+1 / preserved
   attempt counters.
3. Health semantics (T1): /health is liveness-only (static: never touches
   db) and 200 live; /ready is 200 on the migrated test DB.
4. Container logs carry no record text or secrets (T10): dynamic caplog
   drive (login + patient create + draft save + provider-key save) plus a
   static scan of backend logging calls for sensitive fields.
5. KNOWN DEFECT A (RED): prod compose runs the worker as
   ``python -m x_insight.reasoning.worker`` but reasoning/worker.py is a
   run_once() library with no ``__main__`` loop/CLI, so the container
   would import-and-exit immediately.
6. KNOWN DEFECT B (RED): edge ``location /`` proxies to app:8000 but the
   app serves no frontend route and prod compose wires no web build, so
   same-origin ``/`` has nothing to serve.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
SRC_ROOT = BACKEND_DIR / "src" / "x_insight"
DEPLOY_DIR = REPO_ROOT / "deploy"
PROD_COMPOSE = DEPLOY_DIR / "compose.prod.yaml"
NGINX_CONF = DEPLOY_DIR / "edge" / "nginx.conf"
APP_PY = SRC_ROOT / "app.py"
WORKER_PY = SRC_ROOT / "reasoning" / "worker.py"
SETUP_SH = DEPLOY_DIR / "setup.sh"
WEB_DOCKERFILE = REPO_ROOT / "web" / "Dockerfile"

SENTINEL_PASSWORD = "S57Slice4PhysicianSecret001"
SENTINEL_FIRST = "AckAlpha"
SENTINEL_LAST = "AckBeta"
SENTINEL_PHONE = "SYNTH-PHONE-S57-004"
SENTINEL_DRAFT = "synthetic-s57-slice4-draft"
SENTINEL_API_KEY = "sk-s57-slice4-synthetic-key-001"


@pytest.fixture(autouse=True)
def clean_deployment_restart():
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, runs, run_questions, reasoning_jobs, "
                "reasoning_attempts, run_question_artifacts, run_proposals, "
                "audit_events, model_bundle_pointers, model_bundle_events, "
                "mcp_question_grants, provider_configs, "
                "provider_config_pointer, queue_fairness, ddi_dataset_releases"
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


def _mutation_headers(client, *, key=None, revision=None):
    headers = {"X-CSRF-Token": client.cookies.get("xinsight_csrf")}
    if key is not None:
        headers["Idempotency-Key"] = key
    if revision is not None:
        headers["If-Match"] = str(revision)
    return headers


def _make_physician(admin, username, password=SENTINEL_PASSWORD):
    created = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": password},
        headers=_mutation_headers(admin, key=f"s57-s4-{username}-create"),
    )
    assert created.status_code == 201, created.text


def _create_patient(physician, patient_id, key):
    response = physician.post(
        "/api/v1/patients",
        json={
            "first_name": SENTINEL_FIRST,
            "last_name": SENTINEL_LAST,
            "sex": "F",
            "age": 30,
            "patient_id": patient_id,
            "clinical_status": "first_time",
            "phone": SENTINEL_PHONE,
        },
        headers=_mutation_headers(physician, key=key),
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return payload["patient"], payload["encounter"]


def _encounter_body(payload):
    if isinstance(payload, dict) and isinstance(payload.get("encounter"), dict):
        return payload["encounter"]
    return payload


def _below_threshold_answers():
    """SYNTHETIC diagnosis answers (same shape as the S09 diagnosis suite)."""
    return {
        "active_phase_domains": ["delusions", "hallucinations"],
        "shared_one_month_active_phase": False,
        "active_phase_abbreviated_by_intervention": False,
        "functional_decline": False,
        "continuous_months": 2,
        "active_phase_included": False,
        "concurrent_mood_episode_with_psychosis": True,
        "mood_episodes_minority_of_course": False,
        "substance_or_medical_cause": True,
        "autism_or_childhood_communication_history": False,
    }


# ---------------------------------------------------------------------------
# 1. App restart preserves an acknowledged draft (T1).
# ---------------------------------------------------------------------------


def test_app_restart_preserves_acknowledged_draft():
    """S57 item 4: acknowledged draft survives an app restart (T1).

    Physician creates a patient, PATCHes an acknowledged revision
    (diagnosis warning_ack confirm -> server-stamped ack), then the app
    "restarts" (engines disposed, brand-new TestClient on the same DB).
    GET must return the identical revision and draft_data.
    """
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "s57restartdoc")
        _login(physician, "s57restartdoc", SENTINEL_PASSWORD, "physician")
        _, encounter = _create_patient(physician, "0057000004", "s57-s4-patient-1")
        encounter_id = encounter["id"]
        answers = _below_threshold_answers()

        acked = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={
                "draft_data": {
                    "diagnosis": {
                        "answers": answers,
                        "warning_ack": {"confirm": True},
                    }
                }
            },
            headers=_mutation_headers(physician, key="s57-s4-ack", revision=1),
        )
        assert acked.status_code == 200, acked.text
        saved = _encounter_body(acked.json())
        assert saved["revision"] == 2
        stamped = saved["draft_data"]["diagnosis"]["warning_ack"]
        assert isinstance(stamped, dict) and stamped["assessed_revision"] == 2
        saved_draft = saved["draft_data"]

        # Simulate an independent app restart: drop pooled connections and
        # continue with a brand-new HTTP client on the same database.
        db.dispose_engines()
        session_cookie = physician.cookies.get("xinsight_session")
        csrf_cookie = physician.cookies.get("xinsight_csrf")
        assert session_cookie and csrf_cookie
        with TestClient(
            app,
            cookies={
                "xinsight_session": session_cookie,
                "xinsight_csrf": csrf_cookie,
            },
        ) as restarted:
            fetched = restarted.get(f"/api/v1/encounters/{encounter_id}")
            assert fetched.status_code == 200, fetched.text
            seen = _encounter_body(fetched.json())
            assert seen["revision"] == saved["revision"] == 2
            assert seen["draft_data"] == saved_draft
            assert seen["draft_data"]["diagnosis"]["warning_ack"] == stamped


# ---------------------------------------------------------------------------
# 2. Worker restart recovers an expired lease (T8, coarse public-API level).
# ---------------------------------------------------------------------------


def test_worker_restart_recovers_lease():
    """S57 item 4: an expired lease is reclaimable after a worker restart.

    Coarse public-API check only (no duplicated internals): one expired
    claimed job with attempt_count=2 (setup-only direct SQL), one
    simulated worker restart (dispose_engines), one public run_once()
    reclaim. The same job must be served with a fresh token, fencing+1,
    and the preserved attempt counter (next attempt_index == 3).
    """
    from x_insight.reasoning.worker import run_once

    run_id = str(uuid.uuid4())
    encounter_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    old_token = "s57-s4-old-token"
    old_fencing = 4
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO runs (id, encounter_id, encounter_revision, "
                "workflow, snapshot, snapshot_hash, fingerprint, bundle_hash, "
                "pins, status) VALUES (:id, :eid, 2, 'registration', "
                "CAST(:snapshot AS jsonb), :shash, :fp, :bhash, "
                "CAST(:pins AS jsonb), 'queued')"
            ),
            {
                "id": run_id,
                "eid": encounter_id,
                "snapshot": json.dumps({"synthetic": "s57-s4"}),
                "shash": "synthetic-shash-s57-s4",
                "fp": "synthetic-fp-s57-s4",
                "bhash": "synthetic-bhash-s57-s4",
                "pins": json.dumps({}),
            },
        )
        conn.execute(
            text(
                "INSERT INTO reasoning_jobs (id, run_id, encounter_id, "
                "question_key, ordinal, status, available_at, lease_token, "
                "lease_deadline, last_heartbeat, fencing_generation, "
                "attempt_count) VALUES (:id, :run_id, :eid, 's57_q1', 0, "
                "'claimed', now() - interval '1 hour', :token, "
                "now() - interval '1 hour', now() - interval '1 hour', "
                ":fencing, 2)"
            ),
            {
                "id": job_id,
                "run_id": run_id,
                "eid": encounter_id,
                "token": old_token,
                "fencing": old_fencing,
            },
        )

    # Simulate an independent worker restart: drop pooled connections, then
    # reclaim through the public worker entry (no MCP, no live provider:
    # an explicit test-only adapter proves the call path).
    db.dispose_engines()
    out = run_once(
        provider_adapter=lambda claim: {"ok": True},
        worker_id="s57-s4-restart-worker",
    )
    assert out.get("claimed") is True, (
        "an expired claimed lease must be reclaimable after a worker restart"
    )
    assert out.get("job_id") == job_id, "reclaim must serve the SAME job"
    new_token = out.get("lease_token")
    assert new_token is not None and new_token != old_token, (
        "reclaim must mint a fresh lease token"
    )
    assert out.get("fencing_generation") == old_fencing + 1, (
        "reclaim must bump the fencing generation by exactly one"
    )
    assert out.get("attempt_index") == 3, (
        "attempt counters must survive the restart (2 prior + this one)"
    )


# ---------------------------------------------------------------------------
# 3. Health semantics (T1).
# ---------------------------------------------------------------------------


def _health_fn_body() -> str:
    src = APP_PY.read_text(encoding="utf-8")
    start = src.index("def health()")
    rest = src[start:]
    marker = "\n@app."
    end = rest.find(marker)
    body = rest if end == -1 else rest[:end]
    # Strip the docstring/prose so the check inspects code references only
    # (the docstring itself says "never touches the database").
    body = re.sub(r'"""(.*?)"""', "", body, flags=re.DOTALL)
    body = re.sub(r"#.*", "", body)
    return body


def test_health_semantics():
    """S57 item 4: /health is liveness-only; /ready gates on the database."""
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200, health.text
        assert health.json() == {"status": "ok"}
        ready = client.get("/api/v1/ready")
        assert ready.status_code == 200, ready.text
        assert ready.json() == {"status": "ready"}
    body = _health_fn_body()
    assert "db." not in body, "health() must never touch the database"
    assert "database" not in body.lower(), "health() must never touch the database"
    assert "check_readiness" not in body, "health() must never check readiness"


# ---------------------------------------------------------------------------
# 4. Logs carry no record text or secrets (T10).
# ---------------------------------------------------------------------------


_SENSITIVE_LOG_TOKENS = (
    "password",
    "passwd",
    "api_key",
    "apikey",
    "first_name",
    "last_name",
    "phone",
    "draft_data",
    "plaintext",
    "ciphertext",
    "authorization",
    "bearer",
)


def _logging_call_lines():
    hits = []
    pattern = re.compile(
        r"(logger\.(debug|info|warning|error|exception|critical)|print\s*\()"
    )
    for path in sorted(SRC_ROOT.rglob("*.py")):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                hits.append((path, lineno, line))
    return hits


def test_logs_contain_no_record_text_or_secrets(caplog):
    """S57 item 4: login/chart/provider flows must not leak into logs (T10)."""
    with caplog.at_level(logging.WARNING):
        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s57logdoc")
            _login(physician, "s57logdoc", SENTINEL_PASSWORD, "physician")
            _, encounter = _create_patient(
                physician, "0057000005", "s57-s4-log-patient"
            )
            encounter_id = encounter["id"]
            patched = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": {"complaint": SENTINEL_DRAFT}},
                headers=_mutation_headers(
                    physician, key="s57-s4-log-draft", revision=1
                ),
            )
            assert patched.status_code == 200, patched.text
            saved_key = admin.put(
                "/api/v1/api-settings",
                json={
                    "base_url": "https://api.synthetic-s57.invalid/v1",
                    "model": "synthetic-s57-model",
                    "key_action": "replace",
                    "api_key": SENTINEL_API_KEY,
                },
                headers=_mutation_headers(admin, key="s57-s4-log-key"),
            )
            assert saved_key.status_code == 200, saved_key.text
    captured = caplog.text
    for secret in (
        SENTINEL_PASSWORD,
        SENTINEL_FIRST,
        SENTINEL_LAST,
        SENTINEL_PHONE,
        SENTINEL_DRAFT,
        SENTINEL_API_KEY,
    ):
        assert secret not in captured, (
            f"captured logs leak sensitive record text: {secret!r}"
        )

    # Static: no backend logging call may interpolate sensitive fields.
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}"
        for path, lineno, line in _logging_call_lines()
        if any(token in line.lower() for token in _SENSITIVE_LOG_TOKENS)
    ]
    assert not offenders, (
        "backend logging calls interpolate record text/secrets:\n"
        + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# 5. KNOWN DEFECT A (RED): worker module has no __main__ entrypoint.
# ---------------------------------------------------------------------------


def test_worker_entrypoint_exists():
    """S57 item 4 / defect A: compose runs `python -m x_insight.reasoning.worker`.

    A real module entrypoint must exist: a ``__main__`` guard (or main())
    in reasoning/worker.py plus a working ``--help`` CLI. Currently the
    module is a run_once() library only, so the prod worker container
    would import-and-exit instead of running.
    """
    src = WORKER_PY.read_text(encoding="utf-8")
    assert "__main__" in src and "def main(" in src, (
        "reasoning/worker.py defines run_once() only: no __main__ entrypoint "
        "for `python -m x_insight.reasoning.worker`"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "x_insight.reasoning.worker", "--help"],
        cwd=str(BACKEND_DIR),
        env={"PYTHONPATH": str(BACKEND_DIR / "src"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"`python -m x_insight.reasoning.worker --help` must exit 0, "
        f"got {proc.returncode}: {proc.stderr[-2000:]}"
    )
    combined = (proc.stdout + proc.stderr).lower()
    assert "usage" in combined and ("once" in combined or "worker" in combined), (
        "worker --help must describe a real worker CLI (usage text); "
        f"got stdout={proc.stdout[-1000:]!r} stderr={proc.stderr[-1000:]!r}"
    )


# ---------------------------------------------------------------------------
# 6. KNOWN DEFECT B (RED): nothing serves the frontend at ``/``.
# ---------------------------------------------------------------------------


def _location_root_blocks(conf: str) -> list[str]:
    blocks = []
    for match in re.finditer(r"location /\s*\{", conf):
        start = match.end()
        depth = 1
        pos = start
        while pos < len(conf) and depth > 0:
            if conf[pos] == "{":
                depth += 1
            elif conf[pos] == "}":
                depth -= 1
            pos += 1
        blocks.append(conf[start : pos - 1])
    return blocks


def test_edge_serves_frontend():
    """S57 item 4 / defect B: same-origin ``/`` must serve the web bundle.

    Either the app serves a static frontend route, or edge+compose serve a
    prebuilt web bundle (nginx ``location /`` static root + compose edge
    web-dist mount + a web build step in setup.sh or a web Dockerfile
    build stage). Currently ``location /`` only proxies to app:8000, the
    app has no static route, and no web build exists.
    """
    app_src = APP_PY.read_text(encoding="utf-8")
    web_src = "".join(
        p.read_text(encoding="utf-8") for p in sorted(SRC_ROOT.rglob("*.py"))
    )
    app_serves_frontend = (
        "StaticFiles" in app_src or 'mount("/"' in app_src or "index.html" in web_src
    )

    conf = NGINX_CONF.read_text(encoding="utf-8")
    root_blocks = _location_root_blocks(conf)
    assert root_blocks, "nginx.conf has no `location /` block at all"
    nginx_static = any("root" in block or "try_files" in block for block in root_blocks)

    compose = PROD_COMPOSE.read_text(encoding="utf-8")
    compose_mount = any(
        token in compose
        for token in ("web-dist", "web_dist", "/usr/share/nginx/html", "dist/")
    )

    setup = SETUP_SH.read_text(encoding="utf-8") if SETUP_SH.is_file() else ""
    web_docker = (
        WEB_DOCKERFILE.read_text(encoding="utf-8") if WEB_DOCKERFILE.is_file() else ""
    )
    build_step = (
        ("npm run build" in setup or "npm run build" in web_docker)
        or ("AS build" in web_docker or "AS builder" in web_docker)
        or ("dist" in setup and "web" in setup)
    )

    assert app_serves_frontend or (nginx_static and compose_mount and build_step), (
        "nothing serves the frontend at `/`: app.py has no static route "
        f"(app_serves_frontend={app_serves_frontend}); nginx `location /` "
        f"has no static root (nginx_static={nginx_static}); compose edge "
        f"mounts no web-dist volume (compose_mount={compose_mount}); no "
        f"web build step exists (build_step={build_step})"
    )
