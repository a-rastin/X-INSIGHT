"""S12 slice 1 (RED): typed history persistence and provenance (T1).

This test uses only the conspicuously synthetic released fixture under
``tests/fixtures/content/history``. It exercises POST patient followed by
PATCH/GET encounter against real PostgreSQL; persistence is observed only
through HTTP.

Contract under test:
- ``draft_data.history`` pins the released definition version and contains
  declared typed values.
- ``known`` carries a boolean; ``unknown`` and ``not_assessed`` carry null.
  In particular, observed false remains distinct from either missing state.
- The server derives history provenance from the authenticated write: actor,
  server time, and the resulting encounter revision. The client does not send
  provenance.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all

SYNTHETIC_HISTORY_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "content" / "history"
)


@pytest.fixture(autouse=True)
def clean_history(monkeypatch):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(SYNTHETIC_HISTORY_DIR))
    with db.transaction() as conn:
        conn.execute(
            text("TRUNCATE sessions, users, patients, encounters, audit_events")
        )
    reset_all()
    yield
    reset_all()


def _login(client, username="admin", password="admin", role="admin"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 200


def _mutation_headers(client, *, key=None, revision=None):
    headers = {"X-CSRF-Token": client.cookies.get("xinsight_csrf")}
    if key is not None:
        headers["Idempotency-Key"] = key
    if revision is not None:
        headers["If-Match"] = str(revision)
    return headers


def _encounter(payload):
    return payload["encounter"]


def test_declared_history_values_round_trip_with_server_provenance():
    values = {
        "synthetic_flag_false": {"status": "known", "value": False},
        "synthetic_flag_true": {"status": "known", "value": True},
        "synthetic_flag_unknown": {"status": "unknown", "value": None},
        "synthetic_flag_not_assessed": {
            "status": "not_assessed",
            "value": None,
        },
    }

    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        created_physician = admin.post(
            "/api/v1/physicians",
            json={"username": "historydoc", "password": "secret"},
            headers=_mutation_headers(admin, key="history-create-physician"),
        )
        assert created_physician.status_code == 201

        _login(physician, "historydoc", "secret", "physician")
        created_patient = physician.post(
            "/api/v1/patients",
            json={
                "first_name": "Anna",
                "last_name": "Muller",
                "sex": "F",
                "age": 30,
                "patient_id": "0799555551",
                "clinical_status": "first_time",
            },
            headers=_mutation_headers(physician, key="history-create-patient"),
        )
        assert created_patient.status_code == 201
        encounter = created_patient.json()["encounter"]
        created_encounter = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert created_encounter.status_code == 200
        expected_actor_id = _encounter(created_encounter.json())["author_id"]

        saved = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={
                "draft_data": {
                    "history": {
                        "definition_version": "synthetic-history-v1",
                        "values": values,
                    }
                }
            },
            headers=_mutation_headers(physician, revision=encounter["revision"]),
        )
        assert saved.status_code == 200

        fetched = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert fetched.status_code == 200
        persisted = _encounter(fetched.json())
        history = persisted["draft_data"]["history"]

        assert history["definition_version"] == "synthetic-history-v1"
        assert history["values"] == values
        assert (
            history["values"]["synthetic_flag_false"]
            != history["values"]["synthetic_flag_unknown"]
        )
        assert (
            history["values"]["synthetic_flag_unknown"]
            != history["values"]["synthetic_flag_not_assessed"]
        )
        assert history["provenance"]["actor_id"] == expected_actor_id
        assert history["provenance"]["encounter_revision"] == 2
        assert history["provenance"]["recorded_at"].endswith("Z")


def test_effect_status_and_severity_validation_round_trips_with_provenance():
    valid_effects = {
        "tardive_dyskinesia": {
            "status": "present",
            "severity": "synthetic_tardive_severity_one",
        },
        "akathisia": {"status": "absent", "severity": None},
        "parkinsonism": {"status": "not_assessed", "severity": None},
        "acute_dystonia": {
            "status": "present",
            "severity": "synthetic_dystonia_severity_two",
        },
    }

    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        created_physician = admin.post(
            "/api/v1/physicians",
            json={"username": "effectsdoc", "password": "secret"},
            headers=_mutation_headers(admin, key="effects-create-physician"),
        )
        assert created_physician.status_code == 201

        _login(physician, "effectsdoc", "secret", "physician")
        created_patient = physician.post(
            "/api/v1/patients",
            json={
                "first_name": "Anna",
                "last_name": "Muller",
                "sex": "F",
                "age": 30,
                "patient_id": "0799555552",
                "clinical_status": "first_time",
            },
            headers=_mutation_headers(physician, key="effects-create-patient"),
        )
        assert created_patient.status_code == 201
        encounter = created_patient.json()["encounter"]
        created_encounter = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert created_encounter.status_code == 200
        expected_actor_id = _encounter(created_encounter.json())["author_id"]

        present_without_severity = dict(valid_effects)
        present_without_severity["tardive_dyskinesia"] = {
            "status": "present",
            "severity": None,
        }
        rejected_present = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={
                "draft_data": {
                    "effects": {
                        "definition_version": "synthetic-history-v1",
                        "values": present_without_severity,
                    }
                }
            },
            headers=_mutation_headers(physician, revision=1),
        )
        assert rejected_present.status_code == 422

        after_present_rejection = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert after_present_rejection.status_code == 200
        unchanged = _encounter(after_present_rejection.json())
        assert unchanged["revision"] == 1
        assert unchanged["draft_data"] == {}

        absent_with_severity = dict(valid_effects)
        absent_with_severity["akathisia"] = {
            "status": "absent",
            "severity": "synthetic_akathisia_severity_one",
        }
        rejected_absent = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={
                "draft_data": {
                    "effects": {
                        "definition_version": "synthetic-history-v1",
                        "values": absent_with_severity,
                    }
                }
            },
            headers=_mutation_headers(physician, revision=1),
        )
        assert rejected_absent.status_code == 422

        after_absent_rejection = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert after_absent_rejection.status_code == 200
        unchanged = _encounter(after_absent_rejection.json())
        assert unchanged["revision"] == 1
        assert unchanged["draft_data"] == {}

        saved = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={
                "draft_data": {
                    "effects": {
                        "definition_version": "synthetic-history-v1",
                        "values": valid_effects,
                    }
                }
            },
            headers=_mutation_headers(physician, revision=1),
        )
        assert saved.status_code == 200

        fetched = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert fetched.status_code == 200
        persisted = _encounter(fetched.json())
        assert persisted["revision"] == 2
        effects = persisted["draft_data"]["effects"]
        assert effects["definition_version"] == "synthetic-history-v1"
        assert effects["values"] == valid_effects
        assert effects["provenance"]["actor_id"] == expected_actor_id
        assert effects["provenance"]["encounter_revision"] == 2
        assert effects["provenance"]["recorded_at"].endswith("Z")


def test_effect_status_change_requires_explicit_severity_clear():
    present_effects = {
        "tardive_dyskinesia": {
            "status": "present",
            "severity": "synthetic_tardive_severity_one",
        },
        "akathisia": {"status": "absent", "severity": None},
        "parkinsonism": {"status": "not_assessed", "severity": None},
        "acute_dystonia": {
            "status": "present",
            "severity": "synthetic_dystonia_severity_one",
        },
    }

    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        created_physician = admin.post(
            "/api/v1/physicians",
            json={"username": "transitiondoc", "password": "secret"},
            headers=_mutation_headers(admin, key="transition-create-physician"),
        )
        assert created_physician.status_code == 201

        _login(physician, "transitiondoc", "secret", "physician")
        created_patient = physician.post(
            "/api/v1/patients",
            json={
                "first_name": "Anna",
                "last_name": "Muller",
                "sex": "F",
                "age": 30,
                "patient_id": "0799555553",
                "clinical_status": "first_time",
            },
            headers=_mutation_headers(physician, key="transition-create-patient"),
        )
        assert created_patient.status_code == 201
        encounter = created_patient.json()["encounter"]

        saved_present = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={
                "draft_data": {
                    "effects": {
                        "definition_version": "synthetic-history-v1",
                        "values": present_effects,
                    }
                }
            },
            headers=_mutation_headers(physician, revision=1),
        )
        assert saved_present.status_code == 200
        assert _encounter(saved_present.json())["revision"] == 2

        omitted_clear = dict(present_effects)
        omitted_clear["tardive_dyskinesia"] = {"status": "absent"}
        rejected = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={
                "draft_data": {
                    "effects": {
                        "definition_version": "synthetic-history-v1",
                        "values": omitted_clear,
                    }
                }
            },
            headers=_mutation_headers(physician, revision=2),
        )
        assert rejected.status_code == 422

        after_rejection = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert after_rejection.status_code == 200
        unchanged = _encounter(after_rejection.json())
        assert unchanged["revision"] == 2
        assert unchanged["draft_data"]["effects"]["values"] == present_effects
        assert unchanged["draft_data"]["effects"]["values"]["tardive_dyskinesia"] == {
            "status": "present",
            "severity": "synthetic_tardive_severity_one",
        }

        explicitly_cleared = dict(present_effects)
        explicitly_cleared["tardive_dyskinesia"] = {
            "status": "absent",
            "severity": None,
        }
        cleared = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={
                "draft_data": {
                    "effects": {
                        "definition_version": "synthetic-history-v1",
                        "values": explicitly_cleared,
                    }
                }
            },
            headers=_mutation_headers(physician, revision=2),
        )
        assert cleared.status_code == 200
        assert _encounter(cleared.json())["revision"] == 3

        fetched = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert fetched.status_code == 200
        persisted = _encounter(fetched.json())
        assert persisted["revision"] == 3
        assert persisted["draft_data"]["effects"]["values"]["tardive_dyskinesia"] == {
            "status": "absent",
            "severity": None,
        }
