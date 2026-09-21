"""S10 slice 3 (RED): PANSS autosave validation + resume completeness (T1).

SYNTHETIC FIXTURES ONLY. All answers below are conspicuously synthetic
uniform-1 arithmetic checks (7 positive P1-P7 + 7 negative N1-N7 + 16
general G1-G16, each 1-7), never clinical data. Expected sums are
independent hand-worked literals (positive 7, negative 7, general 16,
total 30). Skip persistence is left to frontend e2e; not covered here.

Proposed minimal contract under test (no new tables, no new route):
- Autosave path only: PATCH /api/v1/encounters/{id} with If-Match and
  GET /api/v1/encounters/{id} for reads. Validation lives in
  cases/encounters.py PATCH, reusing assessments/panss.py evaluate_panss.
- draft_data["panss"] = {"answers": {...30 required ids...}}.
- PATCH validates draft_data["panss"]["answers"] via evaluate_panss when
  a panss block is present: statuses partial/complete/not_assessed persist
  verbatim (200); ValueError maps to 422 INVALID_CONTENT with revision
  and draft_data untouched.
- Partial (29 of 30) persists verbatim and GET resume shows the same
  answers; evaluate_panss over resumed answers still reports partial
  with scores None. Full all-1 persists and resumes complete
  (7/7/16/30).

Current backend stores draft_data verbatim with diagnosis-only validation,
so the invalid-content test below fails (200 instead of 422).
"""

from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.assessments.panss import evaluate_panss
from x_insight.identity.throttle import reset_all

POSITIVE_IDS = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]
NEGATIVE_IDS = ["N1", "N2", "N3", "N4", "N5", "N6", "N7"]
GENERAL_IDS = [
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "G6",
    "G7",
    "G8",
    "G9",
    "G10",
    "G11",
    "G12",
    "G13",
    "G14",
    "G15",
    "G16",
]
ALL_30_IDS = POSITIVE_IDS + NEGATIVE_IDS + GENERAL_IDS


def _all_1_answers() -> dict[str, int]:
    """SYNTHETIC: uniform 1s arithmetic check, not clinical data."""
    return {item_id: 1 for item_id in ALL_30_IDS}


def _partial_29_answers() -> dict[str, int]:
    """SYNTHETIC: uniform 1s minus G16, not clinical data."""
    return {item_id: 1 for item_id in ALL_30_IDS if item_id != "G16"}


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def clean_panss():
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


def test_invalid_panss_rejected_server_side():
    with TestClient(app) as admin, TestClient(app) as physician:
        encounter_id = _setup_encounter(
            admin, physician, "doctor", "0799555511", "panss-invalid"
        )
        bad = _all_1_answers()
        bad["P1"] = 0  # SYNTHETIC: out-of-range value, not clinical data.

        rejected = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"panss": {"answers": bad}}},
            headers=draft_headers(physician, "1"),
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "INVALID_CONTENT"

        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        seen = encounter_body(fetched.json())
        assert seen["revision"] == 1
        assert seen["draft_data"] == {}


def test_partial_persists_and_resume_preserves_completeness():
    with TestClient(app) as admin, TestClient(app) as physician:
        encounter_id = _setup_encounter(
            admin, physician, "doctor", "0799555522", "panss-partial"
        )
        answers = _partial_29_answers()

        patched = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"panss": {"answers": answers}}},
            headers=draft_headers(physician, "1"),
        )
        assert patched.status_code == 200
        assert encounter_body(patched.json())["revision"] == 2

        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        resumed = encounter_body(fetched.json())["draft_data"]["panss"]["answers"]
        assert resumed == answers
        result = evaluate_panss(resumed)
        assert result["status"] == "partial"
        assert result["missing_item_ids"] == ["G16"]
        assert result["scores"] is None


def test_full_all_1_persists_and_resumes_complete():
    with TestClient(app) as admin, TestClient(app) as physician:
        encounter_id = _setup_encounter(
            admin, physician, "doctor", "0799555533", "panss-full"
        )
        answers = _all_1_answers()

        patched = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"panss": {"answers": answers}}},
            headers=draft_headers(physician, "1"),
        )
        assert patched.status_code == 200
        assert encounter_body(patched.json())["revision"] == 2

        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        resumed = encounter_body(fetched.json())["draft_data"]["panss"]["answers"]
        assert resumed == answers
        assert evaluate_panss(resumed)["scores"] == {
            "positive": 7,
            "negative": 7,
            "general": 16,
            "total": 30,
        }
