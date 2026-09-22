"""S20 (RED, T1): medications + DDI encounter-history integration.

Contract pinned for dev-backend (implements AFTER this red run):
- PATCH medications: list of dicts with EXACTLY ONE key in
  {catalog_drug_id, unknown_label}, value non-empty str (stripped). Any
  other key (incl. dose/unit/route/frequency/active/stopped/status),
  both/neither discriminator, empty value, non-dict entry, non-list ->
  422 INVALID_CONTENT, revision + draft_data unchanged.
- PATCH ddi_report: optional dict persisted verbatim; when present it must
  carry dataset_version + medication_fingerprint (non-empty str), pairs (if
  present) a list. Else 422, revision unchanged. No server freshness check.
- Follow-up copies medications verbatim, never copies ddi_report, opens
  history_reconciliation {pending, baseline id}, never mutates baseline.
- GET /ddi/current (session-required, anon 401): latest release
  {dataset_version, catalog_version, dataset_hash}, 404 when none,
  Cache-Control private, no-store. POST /ddi/check works with no provider
  settings configured.

Synthetic-only (never clinical): synthetic-med-a/b, synthetic-unknown-x,
pinned pair synthetic-med-a:synthetic-med-b with TWO conflicting rows
(monitor_closely + serious), coverage limited. HTTP-only assertions; SQL
seeds the release / marks baselines signed during setup.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all

SYN_A = "synthetic-med-a"
SYN_B = "synthetic-med-b"
UNK_X = "synthetic-unknown-x"
PAIR_AB = "synthetic-med-a:synthetic-med-b"
CATALOG_VERSION = "synthetic-catalog-s20-v1"
EVIDENCE_ONE = "SYNTHETIC_EVIDENCE_ONE for synthetic-med-a + synthetic-med-b"
EVIDENCE_TWO = "SYNTHETIC_EVIDENCE_TWO conflicting severity for the AB pair"

SYNTHETIC_HISTORY_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "content" / "history"
)


@pytest.fixture(autouse=True)
def clean_medications(monkeypatch):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(SYNTHETIC_HISTORY_DIR))
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, audit_events, ddi_dataset_releases"
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


def _new_version() -> str:
    return f"s20-meds-{uuid.uuid4().hex[:8]}"


def _row(severity: str, raw: str, start: int) -> dict:
    return {
        "pair_key": PAIR_AB,
        "source_severity": severity,
        "management": None,
        "direction": None,
        "source_path": "SYNTHETIC-ddi.txt",
        "span": {"start_line": start, "end_line": start + 1},
        "raw_text": raw,
    }


def _jb(value) -> str:
    return json.dumps(value)


def _insert_release(version: str) -> None:
    evidence = [
        _row("monitor_closely", EVIDENCE_ONE, 1),
        _row("serious", EVIDENCE_TWO, 3),
    ]
    cols = (
        "version, dataset_hash, source_inventory, terminology_provenance, "
        "review_record, corrections, coverage, evidence"
    )
    with db.transaction() as conn:
        conn.execute(
            text(
                f"INSERT INTO ddi_dataset_releases ({cols}) VALUES (:version, "
                ":dataset_hash, CAST(:source_inventory AS JSONB), "
                "CAST(:terminology_provenance AS JSONB), "
                "CAST(:review_record AS JSONB), CAST(:corrections AS JSONB), "
                "CAST(:coverage AS JSONB), CAST(:evidence AS JSONB))"
            ),
            {
                "version": version,
                "dataset_hash": f"synthetic-hash-{version}",
                "source_inventory": _jb([]),
                "terminology_provenance": _jb(
                    {"terminology_version": CATALOG_VERSION, "synthetic_fixture": True}
                ),
                "review_record": _jb(
                    {"synthetic_fixture": True, "reviewer": "dr-synthetic"}
                ),
                "corrections": _jb([]),
                "coverage": _jb({"scope": "limited", "exclusions": []}),
                "evidence": _jb(evidence),
            },
        )


def _make_physician(admin, username: str) -> None:
    created = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": "secret"},
        headers=_mutation_headers(admin, key=f"s20-{username}-{uuid.uuid4().hex[:6]}"),
    )
    assert created.status_code == 201


def _create_patient(physician, patient_id: str, key: str):
    response = physician.post(
        "/api/v1/patients",
        json={
            "first_name": "Anna",
            "last_name": "Muller",
            "sex": "F",
            "age": 30,
            "patient_id": patient_id,
            "clinical_status": "first_time",
        },
        headers=_mutation_headers(physician, key=key),
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["patient"], payload["encounter"]


def _sign_baseline(encounter_id: str) -> None:
    with db.transaction() as conn:
        conn.execute(
            text("UPDATE encounters SET state = 'signed' WHERE id = :id"),
            {"id": str(encounter_id)},
        )


def _encounter(payload):
    return payload["encounter"]


def _setup(admin, physician, tag: str):
    username = f"medsdoc{tag}"
    _login(admin)
    _make_physician(admin, username)
    _login(physician, username, "secret", "physician")
    return _create_patient(physician, f"07990000{tag}", f"s20-{tag}-patient")


FORGED_FIELDS = ["dose", "unit", "route", "frequency", "active", "stopped", "status"]


def test_medications_round_trip_catalog_and_unknown() -> None:
    medications = [{"catalog_drug_id": SYN_A}, {"unknown_label": UNK_X}]
    with TestClient(app) as admin, TestClient(app) as physician:
        _, encounter = _setup(admin, physician, "01")

        saved = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={"draft_data": {"medications": medications}},
            headers=_mutation_headers(physician, revision=encounter["revision"]),
        )
        assert saved.status_code == 200
        assert _encounter(saved.json())["revision"] == encounter["revision"] + 1

        fetched = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert fetched.status_code == 200
        persisted = _encounter(fetched.json())
        assert persisted["revision"] == encounter["revision"] + 1
        assert persisted["draft_data"]["medications"] == medications


@pytest.mark.parametrize("field", FORGED_FIELDS)
def test_forged_regimen_fields_rejected(field: str) -> None:
    with TestClient(app) as admin, TestClient(app) as physician:
        _, encounter = _setup(admin, physician, "02")

        rejected = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={
                "draft_data": {
                    "medications": [
                        {"catalog_drug_id": SYN_A, field: "synthetic-forged"}
                    ]
                }
            },
            headers=_mutation_headers(physician, revision=1),
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "INVALID_CONTENT"

        fetched = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert fetched.status_code == 200
        unchanged = _encounter(fetched.json())
        assert unchanged["revision"] == 1
        assert unchanged["draft_data"] == {}


def test_discriminator_guards() -> None:
    invalid_payloads = [
        [{"catalog_drug_id": SYN_A, "unknown_label": UNK_X}],
        [{}],
        [{"catalog_drug_id": "   "}],
        [{"unknown_label": ""}],
        ["synthetic-med-a"],
        {"catalog_drug_id": SYN_A},
    ]
    with TestClient(app) as admin, TestClient(app) as physician:
        _, encounter = _setup(admin, physician, "03")

        for meds in invalid_payloads:
            rejected = physician.patch(
                f"/api/v1/encounters/{encounter['id']}",
                json={"draft_data": {"medications": meds}},
                headers=_mutation_headers(physician, revision=1),
            )
            assert rejected.status_code == 422, meds
            assert rejected.json()["code"] == "INVALID_CONTENT"

        fetched = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert fetched.status_code == 200
        unchanged = _encounter(fetched.json())
        assert unchanged["revision"] == 1
        assert unchanged["draft_data"] == {}


def test_ddi_report_reference_persists_and_invalid_rejected() -> None:
    version = _new_version()
    _insert_release(version)
    medications = [{"catalog_drug_id": SYN_A}, {"catalog_drug_id": SYN_B}]
    report = {"dataset_version": version, "medication_fingerprint": "fp-synth-1"}
    with TestClient(app) as admin, TestClient(app) as physician:
        _, encounter = _setup(admin, physician, "04")

        saved = physician.patch(
            f"/api/v1/encounters/{encounter['id']}",
            json={"draft_data": {"medications": medications, "ddi_report": report}},
            headers=_mutation_headers(physician, revision=1),
        )
        assert saved.status_code == 200
        assert _encounter(saved.json())["revision"] == 2

        fetched = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert fetched.status_code == 200
        persisted = _encounter(fetched.json())
        assert persisted["draft_data"]["medications"] == medications
        assert persisted["draft_data"]["ddi_report"] == report

        for bad in ({"dataset_version": 123}, {"dataset_version": version}):
            rejected = physician.patch(
                f"/api/v1/encounters/{encounter['id']}",
                json={"draft_data": {"ddi_report": bad}},
                headers=_mutation_headers(physician, revision=2),
            )
            assert rejected.status_code == 422, bad
            assert rejected.json()["code"] == "INVALID_CONTENT"

        refetched = physician.get(f"/api/v1/encounters/{encounter['id']}")
        assert refetched.status_code == 200
        unchanged = _encounter(refetched.json())
        assert unchanged["revision"] == 2
        assert unchanged["draft_data"]["ddi_report"] == report


def test_followup_copies_meds_not_report_requires_reconciliation() -> None:
    version = _new_version()
    _insert_release(version)
    medications = [{"catalog_drug_id": SYN_A}, {"unknown_label": UNK_X}]
    report = {"dataset_version": version, "medication_fingerprint": "fp-synth-1"}
    with TestClient(app) as admin, TestClient(app) as physician:
        patient, baseline = _setup(admin, physician, "05")

        seeded = physician.patch(
            f"/api/v1/encounters/{baseline['id']}",
            json={"draft_data": {"medications": medications, "ddi_report": report}},
            headers=_mutation_headers(physician, revision=baseline["revision"]),
        )
        assert seeded.status_code == 200
        _sign_baseline(baseline["id"])

        created = physician.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": baseline["id"]},
            headers=_mutation_headers(physician, key="s20-e-followup"),
        )
        assert created.status_code == 201
        followup = _encounter(created.json())
        assert followup["draft_data"]["medications"] == medications
        assert "ddi_report" not in followup["draft_data"]
        assert followup["draft_data"]["history_reconciliation"] == {
            "status": "pending",
            "baseline_encounter_id": baseline["id"],
        }

        baseline_fetched = physician.get(f"/api/v1/encounters/{baseline['id']}")
        assert baseline_fetched.status_code == 200
        baseline_draft = _encounter(baseline_fetched.json())["draft_data"]
        assert baseline_draft["medications"] == medications
        assert baseline_draft["ddi_report"] == report

        confirmed = physician.patch(
            f"/api/v1/encounters/{followup['id']}",
            json={"draft_data": {"history_reconciliation": {"status": "confirmed"}}},
            headers=_mutation_headers(physician, revision=1),
        )
        assert confirmed.status_code == 200


def test_ddi_check_works_without_provider_config() -> None:
    version = _new_version()
    _insert_release(version)
    with db.transaction() as conn:
        conn.execute(text("TRUNCATE provider_configs, provider_config_pointer"))
    with TestClient(app) as admin, TestClient(app) as physician:
        _setup(admin, physician, "06")

        unconfigured = admin.get("/api/v1/api-settings")
        assert unconfigured.status_code == 404

        response = physician.post(
            "/api/v1/ddi/check",
            json={
                "dataset_version": version,
                "medications": [
                    {"catalog_drug_id": SYN_A},
                    {"catalog_drug_id": SYN_B},
                ],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["dataset_version"] == version
        raw_texts = [item.get("raw_text") for item in body["pairs"][0]["evidence"]]
        assert EVIDENCE_ONE in raw_texts
        assert EVIDENCE_TWO in raw_texts


def test_discovery_current() -> None:
    version = _new_version()
    _insert_release(version)
    with TestClient(app) as admin, TestClient(app) as physician:
        _setup(admin, physician, "07")

        current = physician.get("/api/v1/ddi/current")
        assert current.status_code == 200
        body = current.json()
        assert body["dataset_version"] == version
        assert body["catalog_version"] == CATALOG_VERSION
        assert body["dataset_hash"] == f"synthetic-hash-{version}"
        assert current.headers["Cache-Control"] == "private, no-store"

    with TestClient(app) as anon:
        denied = anon.get("/api/v1/ddi/current")
        assert denied.status_code == 401
        assert denied.json()["code"] == "UNAUTHENTICATED"

    with TestClient(app) as admin:
        _login(admin)
        with db.transaction() as conn:
            conn.execute(text("TRUNCATE ddi_dataset_releases"))
        missing = admin.get("/api/v1/ddi/current")
        assert missing.status_code == 404
        assert missing.json()["code"] == "NOT_FOUND"
