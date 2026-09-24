"""S58 slice 1 (RED): safe operational metrics for administrators.

Scope: plan.md S58 item 3; seams T1/T8/T10 approved, this slice uses T1
only (authenticated HTTP against real PostgreSQL). No new seam: the route
under test lives under /api/v1, which is within T1.

Behavior under test (no implementation exists yet; all fail 404 in red):
- Admin GET /api/v1/ops-metrics -> 200 with {"schema_version": 1} plus
  safe operational sections only: queue age (oldest eligible job age in
  seconds, or null when empty), heartbeat (last heartbeat age, or a
  missing flag when never seen), provider retry/auth-failure counters,
  inference limit counters, disk usage percent, last backup success
  time/status, save-failure counter. No clinical payloads (no patient
  names, notes, CPTs) and no secrets/keys/tracebacks.
- Physician GET -> 403, anonymous GET -> 401.
- Alert conditions are evaluable from the payload: missing heartbeat
  (>120s), eligible queue age (>300s), repeated provider auth failure,
  disk usage (>80%). On a fresh system (no jobs, no heartbeats, no
  provider failures) the payload reports an empty queue (null age), a
  missing heartbeat, zero provider failures, and alert booleans
  reflecting exactly that seeded state.
- The response body contains no api_key/ciphertext/password/hash/
  traceback material.

All fixtures are synthetic; no live provider or owner patient data.
Assertions read the HTTP JSON; direct SQL is used only for per-test
isolation (TRUNCATE sessions/users/audit), never for behavior
assertions.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all

OPS_METRICS_PATH = "/api/v1/ops-metrics"

FORBIDDEN_SUBSTRINGS = ("api_key", "ciphertext", "password", "hash", "traceback")
FORBIDDEN_KEYS = (
    "patient",
    "patients",
    "patient_name",
    "first_name",
    "last_name",
    "notes",
    "cpt",
    "cpts",
    "api_key",
    "ciphertext",
    "password",
    "traceback",
)


@pytest.fixture(autouse=True)
def clean_ops_metrics():
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, runs, run_questions, reasoning_jobs, "
                "reasoning_attempts, run_question_artifacts, run_proposals, "
                "audit_events, model_bundle_pointers, model_bundle_events, "
                "mcp_question_grants, provider_configs, "
                "provider_config_pointer, queue_fairness, ddi_dataset_releases, "
                "recovery_jobs"
            )
        )
    reset_all()
    yield
    reset_all()


def login(client: TestClient, username="admin", password="admin", role="admin"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_physician(admin: TestClient, username: str):
    response = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": "synthetic-s58-secret-one"},
        headers={
            "X-CSRF-Token": admin.cookies.get("xinsight_csrf"),
            "Idempotency-Key": f"s58-ops-{username}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _all_keys(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key).lower())
            found |= _all_keys(value)
    elif isinstance(node, list):
        for item in node:
            found |= _all_keys(item)
    return found


def test_admin_gets_safe_operational_metrics_schema():
    with TestClient(app) as admin:
        login(admin)
        response = admin.get(OPS_METRICS_PATH)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["schema_version"] == 1

        queue = body["queue"]
        assert queue["oldest_eligible_age_seconds"] is None

        heartbeat = body["heartbeat"]
        assert heartbeat["missing"] is True
        assert heartbeat["last_heartbeat_age_seconds"] is None

        provider = body["provider"]
        assert provider["retries"] == 0
        assert provider["auth_failures"] == 0

        inference = body["inference"]
        assert inference["limit_rejections"] == 0

        disk = body["disk"]
        assert 0 <= disk["usage_percent"] <= 100

        backup = body["backup"]
        assert backup["last_success_at"] is None
        assert isinstance(backup["status"], str)

        saves = body["saves"]
        assert saves["failures"] == 0

        alerts = body["alerts"]
        assert alerts["missing_heartbeat"] is True
        assert alerts["queue_age_exceeded"] is False
        assert alerts["provider_auth_failure"] is False
        assert alerts["disk_high"] is False
        assert alerts["missing_heartbeat"] == heartbeat["missing"]
        assert alerts["disk_high"] == (disk["usage_percent"] > 80)


def test_physician_denied_and_anonymous_unauthenticated():
    with (
        TestClient(app) as admin,
        TestClient(app) as physician,
        TestClient(app) as anon,
    ):
        login(admin)
        create_physician(admin, "s58metricsdoc")
        login(
            physician,
            "s58metricsdoc",
            "synthetic-s58-secret-one",
            "physician",
        )

        assert physician.get(OPS_METRICS_PATH).status_code == 403
        assert anon.get(OPS_METRICS_PATH).status_code == 401


def test_metrics_contain_no_secrets_or_clinical_payloads():
    with TestClient(app) as admin:
        login(admin)
        response = admin.get(OPS_METRICS_PATH)
        assert response.status_code == 200, response.text
        lowered = response.text.lower()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in lowered
        keys = _all_keys(response.json())
        for clinical in FORBIDDEN_KEYS:
            assert clinical not in keys
