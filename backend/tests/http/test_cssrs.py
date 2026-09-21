"""S11 slice 1 (RED): C-SSRS autosave validation + skip resume (T1).

SYNTHETIC FIXTURES ONLY. All answers below are conspicuously synthetic
empty/skip-only/invalid-type checks, never clinical data. Level ids L1-L5
mirror the approved severity ordering from docs/medical-docs/CSSRS.md; no
intensity/behavior/lethality is covered here (slices 2-3).

Proposed minimal contract under test (no new tables, no new route):
- Autosave path only: PATCH /api/v1/encounters/{id} with If-Match and
  GET /api/v1/encounters/{id} for reads. Validation lives in
  cases/encounters.py PATCH, reusing assessments/cssrs.py evaluate_cssrs.
- draft_data["cssrs"] = {"answers": {L1..L5 each {"endorsed": bool, ...}}}
  or skip shape {"not_assessed": True} at the cssrs level (no answers key).
- PATCH validates the cssrs block when present: skip persists verbatim
  (200, rev+1); ValueError maps to 422 INVALID_CONTENT with revision and
  draft_data untouched.
- Invalid endorsed type (e.g. "yes" instead of bool) must be 422.

Current backend stores draft_data verbatim with diagnosis+PANSS-only
validation, so the invalid-content test below fails (200 instead of 422).
"""

import pytest  # noqa: E402
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_cssrs():
    with db.transaction() as conn:
        conn.execute(
            text("TRUNCATE sessions, users, patients, encounters, audit_events")
        )
    reset_all()
    yield
    reset_all()


def login(client, username="admin", password="admin", role="admin"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 200
    return response.json()


def patient_headers(client, key):
    return {
        "X-CSRF-Token": client.cookies.get("xinsight_csrf"),
        "Idempotency-Key": key,
    }


def draft_headers(client, revision=None):
    headers = {"X-CSRF-Token": client.cookies.get("xinsight_csrf")}
    if revision is not None:
        headers["If-Match"] = str(revision)
    return headers


def create_physician(admin, username, key):
    created = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": "secret"},
        headers=patient_headers(admin, key),
    )
    assert created.status_code == 201


def create_patient(physician, patient_id, key):
    body = {
        "first_name": "Anna",
        "last_name": "Muller",
        "sex": "F",
        "age": 30,
        "patient_id": patient_id,
        "clinical_status": "first_time",
    }
    response = physician.post(
        "/api/v1/patients", json=body, headers=patient_headers(physician, key)
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["patient"], payload["encounter"]


def encounter_body(payload):
    if isinstance(payload, dict) and isinstance(payload.get("encounter"), dict):
        return payload["encounter"]
    return payload


def _setup_encounter(admin, physician, username, patient_id, key_prefix):
    login(admin)
    create_physician(admin, username, f"{key_prefix}-create")
    login(physician, username, "secret", "physician")
    _, encounter = create_patient(physician, patient_id, f"{key_prefix}-patient")
    return encounter["id"]


def test_invalid_cssrs_rejected():
    with TestClient(app) as admin, TestClient(app) as physician:
        encounter_id = _setup_encounter(
            admin, physician, "doctor", "0799555541", "cssrs-invalid"
        )
        # SYNTHETIC: endorsed must be bool; "yes" is an invalid type.
        bad_answers = {"L1": {"endorsed": "yes"}}

        rejected = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"cssrs": {"answers": bad_answers}}},
            headers=draft_headers(physician, "1"),
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "INVALID_CONTENT"

        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        seen = encounter_body(fetched.json())
        assert seen["revision"] == 1
        assert seen["draft_data"] == {}


def test_skip_persists_and_resumes():
    with TestClient(app) as admin, TestClient(app) as physician:
        encounter_id = _setup_encounter(
            admin, physician, "doctor", "0799555542", "cssrs-skip"
        )

        patched = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"cssrs": {"not_assessed": True}}},
            headers=draft_headers(physician, "1"),
        )
        assert patched.status_code == 200
        assert encounter_body(patched.json())["revision"] == 2

        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        resumed = encounter_body(fetched.json())["draft_data"]["cssrs"]
        assert resumed == {"not_assessed": True}


def test_period_validation_and_persistence():
    # SYNTHETIC: invalid period rejected, valid historical/current persist.
    with TestClient(app) as admin, TestClient(app) as physician:
        encounter_id = _setup_encounter(
            admin, physician, "doctor", "0799555543", "cssrs-period"
        )
        bad_answers = {"L1": {"endorsed": True, "period": "last-week"}}
        rejected = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"cssrs": {"answers": bad_answers}}},
            headers=draft_headers(physician, "1"),
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "INVALID_CONTENT"

        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        seen = encounter_body(fetched.json())
        assert seen["revision"] == 1
        assert seen["draft_data"] == {}

        good_answers = {
            "L3": {"endorsed": True, "period": "historical"},
            "L4": {"endorsed": True, "period": "current"},
        }
        patched = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"cssrs": {"answers": good_answers}}},
            headers=draft_headers(physician, "1"),
        )
        assert patched.status_code == 200
        assert encounter_body(patched.json())["revision"] == 2

        resumed = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert resumed.status_code == 200
        persisted = encounter_body(resumed.json())["draft_data"]["cssrs"]["answers"]
        assert persisted == good_answers
        assert persisted["L3"]["period"] == "historical"
        assert persisted["L4"]["period"] == "current"
