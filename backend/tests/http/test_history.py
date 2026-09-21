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
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, audit_events"
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


def test_undeclared_history_field_rejected_revision_unchanged():
    """S12 slice A: undeclared history field -> 422, revision/draft unchanged."""
    values = {
        "synthetic_flag_true": {"status": "known", "value": True},
        "undeclared_synthetic_field": {"status": "known", "value": True},
    }

    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        created_physician = admin.post(
            "/api/v1/physicians",
            json={"username": "undeclareddoc", "password": "secret"},
            headers=_mutation_headers(admin, key="undeclared-create-physician"),
        )
        assert created_physician.status_code == 201

        _login(physician, "undeclareddoc", "secret", "physician")
        created_patient = physician.post(
            "/api/v1/patients",
            json={
                "first_name": "Anna",
                "last_name": "Muller",
                "sex": "F",
                "age": 30,
                "patient_id": "0799555554",
                "clinical_status": "first_time",
            },
            headers=_mutation_headers(physician, key="undeclared-create-patient"),
        )
        assert created_patient.status_code == 201
        encounter = created_patient.json()["encounter"]

        rejected = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={
                "draft_data": {
                    "history": {
                        "definition_version": "synthetic-history-v1",
                        "values": values,
                    }
                }
            },
            headers=_mutation_headers(physician, revision=1),
        )
        assert rejected.status_code == 422

        fetched = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert fetched.status_code == 200
        unchanged = _encounter(fetched.json())
        assert unchanged["revision"] == 1
        assert unchanged["draft_data"] == {}


def test_excluded_medication_regimen_fields_rejected():
    """S12 slice A (RED): FR-14-excluded regimen fields -> 422, never stored.

    FR-14 excludes dose/unit/route/frequency/active/stopped from history and
    medication payloads (see content/history/history-effects-v0.1-draft.json
    source_derived_constraints.medication_regimen_exclusions). A medication
    entry carrying any of these fields must be rejected with 422 and must not
    bump the revision or persist. Currently no medication validator exists, so
    the payload is stored verbatim (200) -- this test fails red until
    dev-backend adds the guard.
    """
    medications = [
        {
            "catalog_drug_id": "synthetic-drug",
            "dose": "10",
            "unit": "mg",
            "route": "oral",
            "frequency": "daily",
            "active": True,
            "stopped": False,
        }
    ]

    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        created_physician = admin.post(
            "/api/v1/physicians",
            json={"username": "regimendoc", "password": "secret"},
            headers=_mutation_headers(admin, key="regimen-create-physician"),
        )
        assert created_physician.status_code == 201

        _login(physician, "regimendoc", "secret", "physician")
        created_patient = physician.post(
            "/api/v1/patients",
            json={
                "first_name": "Anna",
                "last_name": "Muller",
                "sex": "F",
                "age": 30,
                "patient_id": "0799555555",
                "clinical_status": "first_time",
            },
            headers=_mutation_headers(physician, key="regimen-create-patient"),
        )
        assert created_patient.status_code == 201
        encounter = created_patient.json()["encounter"]

        rejected = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={"draft_data": {"medications": medications}},
            headers=_mutation_headers(physician, revision=1),
        )
        assert rejected.status_code == 422

        fetched = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert fetched.status_code == 200
        unchanged = _encounter(fetched.json())
        assert unchanged["revision"] == 1
        assert unchanged["draft_data"] == {}


def test_physician_phone_update_via_patient_patch():
    """S12 slice B (RED): optional phone text update belongs to S12 step 4.

    Expected contract (plan.md 2.2/4.3): physician PATCH /patients/{id} updates
    the optional phone text (no country validation; plain text, not a number),
    guarded by session + physician role + If-Match revision. Admin PATCH is 403,
    anonymous is 401. No such route exists yet (patients.py has GET/POST only),
    so this fails red with 404/405 until dev-backend adds it. Open question for
    dev-backend (do NOT guess in this test): whether empty string clears the
    phone or is stored verbatim; S14 owns follow-up phone reconciliation.
    """
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        created_physician = admin.post(
            "/api/v1/physicians",
            json={"username": "phonedoc", "password": "secret"},
            headers=_mutation_headers(admin, key="phone-create-physician"),
        )
        assert created_physician.status_code == 201

        _login(physician, "phonedoc", "secret", "physician")
        created_patient = physician.post(
            "/api/v1/patients",
            json={
                "first_name": "Anna",
                "last_name": "Muller",
                "sex": "F",
                "age": 30,
                "patient_id": "0799555556",
                "clinical_status": "first_time",
            },
            headers=_mutation_headers(physician, key="phone-create-patient"),
        )
        assert created_patient.status_code == 201
        patient = created_patient.json()["patient"]

        updated = physician.patch(
            f"/api/v1/patients/{patient['id']}",
            json={"phone": "synthetic-phone-text"},
            headers=_mutation_headers(physician, revision=patient["revision"]),
        )
        assert updated.status_code == 200
        assert updated.json()["patient"]["phone"] == "synthetic-phone-text"

        forbidden = admin.patch(
            f"/api/v1/patients/{patient['id']}",
            json={"phone": "synthetic-admin-phone"},
            headers=_mutation_headers(admin, revision=patient["revision"]),
        )
        assert forbidden.status_code == 403


def test_history_reconciliation_shape_rejected_when_not_explicit():
    """S12 slice B (RED): reconciliation state must be validated, not verbatim.

    S12 step 4 requires a history reconciliation state for follow-up (copied
    history stays pending until explicitly confirmed/updated). No validator
    exists yet: any draft_data.history_reconciliation value is stored verbatim
    (200). This test pins only the shape rule -- a bare non-object marker must
    be 422 with revision unchanged -- and deliberately does NOT define the
    valid pending/confirmed enum or copy semantics; those belong to S14
    (follow-up entry) + dev-backend. Fails red (200) until the guard exists.
    """
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        created_physician = admin.post(
            "/api/v1/physicians",
            json={"username": "reconciledoc", "password": "secret"},
            headers=_mutation_headers(admin, key="reconcile-create-physician"),
        )
        assert created_physician.status_code == 201

        _login(physician, "reconciledoc", "secret", "physician")
        created_patient = physician.post(
            "/api/v1/patients",
            json={
                "first_name": "Anna",
                "last_name": "Muller",
                "sex": "F",
                "age": 30,
                "patient_id": "0799555557",
                "clinical_status": "first_time",
            },
            headers=_mutation_headers(physician, key="reconcile-create-patient"),
        )
        assert created_patient.status_code == 201
        encounter = created_patient.json()["encounter"]

        rejected = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={"draft_data": {"history_reconciliation": "reconciled"}},
            headers=_mutation_headers(physician, revision=1),
        )
        assert rejected.status_code == 422

        fetched = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert fetched.status_code == 200
        unchanged = _encounter(fetched.json())
        assert unchanged["revision"] == 1
        assert unchanged["draft_data"] == {}


def test_history_content_route_exposes_released_only(monkeypatch):
    """S12 slice B (RED): GET /content/history serves released versions only.

    Mirrors the S08 assessments content contract (assessments/content.py):
    anonymous -> 401; authenticated against the default content dir (whose
    history-effects-v0.1-draft.json is awaiting_review, never released) -> 404;
    authenticated with X_INSIGHT_HISTORY_CONTENT_DIR pointing at the synthetic
    released fixture -> 200 with the released version. No such route exists
    yet, so the released-fixture leg fails red (404) until dev-backend adds it.
    Uses the synthetic fixture env only; never touches the released draft.
    """
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/v1/content/history").status_code == 401

    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        created_physician = admin.post(
            "/api/v1/physicians",
            json={"username": "historycontentdoc", "password": "secret"},
            headers=_mutation_headers(admin, key="historycontent-create-physician"),
        )
        assert created_physician.status_code == 201
        _login(physician, "historycontentdoc", "secret", "physician")

        monkeypatch.delenv("X_INSIGHT_HISTORY_CONTENT_DIR", raising=False)
        draft_default = physician.get("/api/v1/content/history")
        assert draft_default.status_code == 404

        monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(SYNTHETIC_HISTORY_DIR))
        released = physician.get("/api/v1/content/history")
        assert released.status_code == 200
        assert released.json()["definition_version"] == "synthetic-history-v1"


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
