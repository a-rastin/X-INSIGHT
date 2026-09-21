"""S09 slice 3 (RED): below-threshold warning acknowledgment over autosave (T1+T2).

SYNTHETIC FIXTURES ONLY. Answers below are the hand-worked
symptom-count-only case from tests/assessments/test_diagnosis.py
(shared_one_month_active_phase False, so criterion A fails and the
evaluator reports threshold_met False). Never clinical data.

Proposed minimal contract under test (no new tables, no new route):
- Autosave path only: PATCH /api/v1/encounters/{id} with If-Match and
  GET /api/v1/encounters/{id} for reads. Validation lives in
  cases/encounters.py PATCH, reusing assessments/diagnosis.py (threshold)
  and contracts.content_hash (canonical JSON sha256).
- draft_data["diagnosis"] = {"answers": {...10 required ids...},
  "warning_ack": None | {"actor_id", "acknowledged_at",
  "assessed_revision", "answers_hash"}}. "bypass" is reserved None
  (future S49 sign gate), not covered here.
- Client requests an ack with {"warning_ack": {"confirm": true}} only.
  The server stamps actor_id (session user_id), acknowledged_at (server
  UTC Z), assessed_revision (new encounter revision), answers_hash
  (content_hash(answers)). Any client-supplied attestation field
  (actor_id/acknowledged_at/assessed_revision/answers_hash) is 422
  INVALID_CONTENT; revision stays untouched.
- PATCH normalizes a present diagnosis block missing warning_ack to an
  explicit None, so "assessed, unacknowledged" is observable via GET.
- Below-threshold without ack still saves (200); the draft stays
  unacknowledged (sign blocked later in S49, not here).
- Any answers change without a fresh confirm clears a prior ack to None
  (stale revision/hash never revalidates; the client never echoes a
  stamped ack to revalidate it).

Current backend stores draft_data verbatim, so the 422/stamp/clear
assertions below fail (200 with forged or missing attestation).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.assessments.diagnosis import evaluate_diagnosis
from x_insight.contracts import content_hash
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_diagnosis():
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, audit_events"
            )
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


def synthetic_below_threshold_answers():
    """SYNTHETIC: 2 domains, no shared 1-month phase; A-E fail on paper."""
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


def test_below_threshold_without_ack_stays_unacknowledged():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "diag-create-doctor-1")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0799111111", "diag-patient-1")
        encounter_id = encounter["id"]
        answers = synthetic_below_threshold_answers()

        patched = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"diagnosis": {"answers": answers}}},
            headers=draft_headers(physician, "1"),
        )
        assert patched.status_code == 200
        assert encounter_body(patched.json())["revision"] == 2

        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        diagnosis = encounter_body(fetched.json())["draft_data"]["diagnosis"]
        assert diagnosis["answers"] == answers
        assert evaluate_diagnosis(diagnosis["answers"])["threshold_met"] is False
        # Server normalizes "assessed, unacknowledged" to explicit None.
        assert "warning_ack" in diagnosis
        assert diagnosis["warning_ack"] is None


def test_forged_warning_ack_rejected():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "diag-create-doctor-2")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0799222222", "diag-patient-2")
        encounter_id = encounter["id"]
        answers = synthetic_below_threshold_answers()

        forged = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={
                "draft_data": {
                    "diagnosis": {
                        "answers": answers,
                        "warning_ack": {
                            "actor_id": "00000000-0000-4000-8000-000000000000",
                            "acknowledged_at": "2030-01-01T00:00:00Z",
                            "assessed_revision": 999,
                            "answers_hash": content_hash(answers),
                        },
                    }
                }
            },
            headers=draft_headers(physician, "1"),
        )
        assert forged.status_code == 422
        assert forged.json()["code"] == "INVALID_CONTENT"

        # Rejected saves leave revision and content untouched.
        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        seen = encounter_body(fetched.json())
        assert seen["revision"] == 1
        assert seen["draft_data"] == {}


def test_answers_change_invalidates_prior_ack():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "diag-create-doctor-3")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0799333333", "diag-patient-3")
        encounter_id = encounter["id"]
        author_id = encounter_body(
            physician.get(f"/api/v1/encounters/{encounter_id}").json()
        )["author_id"]
        answers_v1 = synthetic_below_threshold_answers()

        acked = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={
                "draft_data": {
                    "diagnosis": {
                        "answers": answers_v1,
                        "warning_ack": {"confirm": True},
                    }
                }
            },
            headers=draft_headers(physician, "1"),
        )
        assert acked.status_code == 200
        stamped = encounter_body(acked.json())["draft_data"]["diagnosis"]["warning_ack"]
        assert stamped["actor_id"] == author_id
        assert stamped["acknowledged_at"].endswith("Z")
        assert stamped["assessed_revision"] == 2
        assert stamped["answers_hash"] == content_hash(answers_v1)

        # Relevant edit (diagnosis answers change) without fresh confirm.
        answers_v2 = dict(answers_v1)
        answers_v2["functional_decline"] = True
        assert answers_v2 != answers_v1
        edited = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"diagnosis": {"answers": answers_v2}}},
            headers=draft_headers(physician, "2"),
        )
        assert edited.status_code == 200
        assert encounter_body(edited.json())["revision"] == 3

        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        diagnosis = encounter_body(fetched.json())["draft_data"]["diagnosis"]
        assert diagnosis["answers"] == answers_v2
        assert evaluate_diagnosis(diagnosis["answers"])["threshold_met"] is False
        assert "warning_ack" in diagnosis
        assert diagnosis["warning_ack"] is None


# S09 slice 4 (RED): diagnosis bypass persistence over autosave (T1).
#
# Proposed minimal contract under test (mirrors slice-3 warning_ack):
# - Autosave path only: PATCH /api/v1/encounters/{id} with If-Match and
#   GET for reads. No new tables, no new route, no reason field.
# - Client requests bypass with {"bypass": {"confirm": True}} only, with
#   partial or empty answers (no threshold evaluation, no warning_ack).
# - Server stamps bypass {actor_id (session user_id), bypassed_at (server
#   UTC Z), status "bypassed", assessed_revision (new encounter revision)}.
#   Any client-supplied bypass field (actor_id/bypassed_at/status/reason,
#   or anything beyond exactly {"confirm": True}) is 422 INVALID_CONTENT;
#   revision stays untouched.
#
# Current encounters.py passes bypass through untouched (no stamping, no
# 422), so both tests below fail (missing stamp / forged accepted).


def test_bypass_without_reason_succeeds_and_survives_resume():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "diag-create-doctor-4")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0799444444", "diag-patient-4")
        encounter_id = encounter["id"]
        author_id = encounter_body(
            physician.get(f"/api/v1/encounters/{encounter_id}").json()
        )["author_id"]

        # SYNTHETIC: empty answers (partial) bypassed with no reason field.
        patched = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={
                "draft_data": {
                    "diagnosis": {"answers": {}, "bypass": {"confirm": True}}
                }
            },
            headers=draft_headers(physician, "1"),
        )
        assert patched.status_code == 200
        seen = encounter_body(patched.json())
        assert seen["revision"] == 2
        diagnosis = seen["draft_data"]["diagnosis"]
        # Bypass does not require warning_ack.
        assert diagnosis.get("warning_ack") is None
        bypass = diagnosis["bypass"]
        assert bypass["actor_id"] == author_id
        assert bypass["bypassed_at"].endswith("Z")
        assert bypass["status"] == "bypassed"
        assert bypass["assessed_revision"] == 2
        assert "reason" not in bypass

        # Survives GET resume with identical values.
        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        resumed = encounter_body(fetched.json())["draft_data"]["diagnosis"]
        assert resumed["bypass"] == bypass
        assert resumed.get("warning_ack") is None


def test_forged_bypass_rejected():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "diag-create-doctor-5")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0799445555", "diag-patient-5")
        encounter_id = encounter["id"]

        forged = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={
                "draft_data": {
                    "diagnosis": {
                        "answers": {},
                        "bypass": {
                            "confirm": True,
                            "actor_id": "00000000-0000-4000-8000-000000000000",
                            "bypassed_at": "2030-01-01T00:00:00Z",
                            "status": "bypassed",
                            "reason": "synthetic",
                        },
                    }
                }
            },
            headers=draft_headers(physician, "1"),
        )
        assert forged.status_code == 422
        assert forged.json()["code"] == "INVALID_CONTENT"

        # Rejected saves leave revision and content untouched.
        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        seen = encounter_body(fetched.json())
        assert seen["revision"] == 1
        assert seen["draft_data"] == {}
