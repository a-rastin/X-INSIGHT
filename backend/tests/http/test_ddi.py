"""S19 slice 4 (RED): DDI HTTP surface T1, real PostgreSQL, synthetic only.

Contract under test:
- POST /api/v1/ddi/check requires session (anon 401); physician+admin 200
  with pinned synthetic release, response pins dataset_version /
  catalog_version / medication_fingerprint, Cache-Control private, no-store.
- Unknown dataset_version -> 404 NOT_FOUND envelope (never 200 empty).
- Excluded regimen fields -> 422 INVALID_CONTENT; both/neither
  discriminator -> 422.
- GET /api/v1/drugs?query= requires session (anon 401); returns matching
  catalog entries with version IDs; query filters case-insensitively;
  empty query is bounded.

Synthetic fixture (conspicuously synthetic, tests-only; never clinical):
concept ids synthetic-drug-a/b with one evidence row for the AB pair.
Expected pair key is the pinned literal below, never computed via code.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all

SYN_A = "synthetic-drug-a"
SYN_B = "synthetic-drug-b"
PAIR_AB = "synthetic-drug-a:synthetic-drug-b"
CATALOG_VERSION = "synthetic-catalog-s19-s4-v1"
EVIDENCE_RAW = "SYNTHETIC evidence for synthetic-drug-a + synthetic-drug-b - test only"


@pytest.fixture(autouse=True)
def clean_ddi():
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


def _login(client: TestClient, username="admin", password="admin", role="admin"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 200


def _mutation_headers(client: TestClient, *, key: str):
    return {
        "X-CSRF-Token": client.cookies.get("xinsight_csrf"),
        "Idempotency-Key": key,
    }


def _insert_release(version: str) -> None:
    """Fixture SETUP only (not under test): one synthetic release, one AB row."""
    evidence = [
        {
            "pair_key": PAIR_AB,
            "source_severity": "monitor_closely",
            "management": None,
            "direction": None,
            "source_path": "SYNTHETIC-slice4.txt",
            "span": {"start_line": 1, "end_line": 2},
            "raw_text": EVIDENCE_RAW,
        }
    ]
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO ddi_dataset_releases "
                "(version, dataset_hash, source_inventory, "
                "terminology_provenance, review_record, corrections, "
                "coverage, evidence) "
                "VALUES (:version, :dataset_hash, "
                "CAST(:source_inventory AS JSONB), "
                "CAST(:terminology_provenance AS JSONB), "
                "CAST(:review_record AS JSONB), "
                "CAST(:corrections AS JSONB), "
                "CAST(:coverage AS JSONB), "
                "CAST(:evidence AS JSONB))"
            ),
            {
                "version": version,
                "dataset_hash": f"synthetic-hash-{version}",
                "source_inventory": json.dumps([]),
                "terminology_provenance": json.dumps(
                    {
                        "terminology_version": CATALOG_VERSION,
                        "synthetic_fixture": True,
                    }
                ),
                "review_record": json.dumps(
                    {"synthetic_fixture": True, "reviewer": "dr-synthetic"}
                ),
                "corrections": json.dumps([]),
                "coverage": json.dumps({"scope": "limited", "exclusions": []}),
                "evidence": json.dumps(evidence),
            },
        )


def _new_version() -> str:
    return f"s19-s4-http-{uuid.uuid4().hex[:8]}"


def _make_physician(admin: TestClient, username: str) -> None:
    created = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": "secret"},
        headers=_mutation_headers(admin, key=f"ddi-{username}-{uuid.uuid4().hex[:6]}"),
    )
    assert created.status_code == 201


def test_anon_check_requires_session() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ddi/check",
            json={
                "dataset_version": "synthetic-missing",
                "medications": [{"catalog_drug_id": SYN_A}],
            },
        )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_physician_and_admin_can_check_pins() -> None:
    version = _new_version()
    _insert_release(version)
    payload = {
        "dataset_version": version,
        "medications": [{"catalog_drug_id": SYN_A}, {"catalog_drug_id": SYN_B}],
    }
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "ddidoc")
        _login(physician, "ddidoc", "secret", "physician")

        admin_resp = admin.post("/api/v1/ddi/check", json=payload)
        assert admin_resp.status_code == 200
        admin_body = admin_resp.json()
        assert admin_body["dataset_version"] == version
        assert admin_body["catalog_version"] == CATALOG_VERSION
        assert isinstance(admin_body["medication_fingerprint"], str)
        assert admin_body["medication_fingerprint"]
        assert admin_resp.headers["Cache-Control"] == "private, no-store"

        phys_resp = physician.post("/api/v1/ddi/check", json=payload)
        assert phys_resp.status_code == 200
        phys_body = phys_resp.json()
        assert phys_body["dataset_version"] == version
        assert phys_body["catalog_version"] == CATALOG_VERSION
        assert (
            phys_body["medication_fingerprint"] == admin_body["medication_fingerprint"]
        )
        assert EVIDENCE_RAW in phys_body["pairs"][0]["evidence"][0]["raw_text"]


def test_unknown_dataset_version_404() -> None:
    with TestClient(app) as client:
        _login(client)
        response = client.post(
            "/api/v1/ddi/check",
            json={
                "dataset_version": f"s19-s4-missing-{uuid.uuid4().hex[:8]}",
                "medications": [{"catalog_drug_id": SYN_A}],
            },
        )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_excluded_fields_422() -> None:
    version = _new_version()
    _insert_release(version)
    with TestClient(app) as client:
        _login(client)
        response = client.post(
            "/api/v1/ddi/check",
            json={
                "dataset_version": version,
                "medications": [{"catalog_drug_id": SYN_A, "dose": "synthetic-dose"}],
            },
        )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_CONTENT"


def test_both_neither_discriminator_422() -> None:
    version = _new_version()
    _insert_release(version)
    with TestClient(app) as client:
        _login(client)
        both = client.post(
            "/api/v1/ddi/check",
            json={
                "dataset_version": version,
                "medications": [
                    {"catalog_drug_id": SYN_A, "unknown_label": "synthetic-x"}
                ],
            },
        )
        assert both.status_code == 422
        assert both.json()["code"] == "INVALID_CONTENT"

        neither = client.post(
            "/api/v1/ddi/check",
            json={"dataset_version": version, "medications": [{}]},
        )
        assert neither.status_code == 422
        assert neither.json()["code"] == "INVALID_CONTENT"


def test_anon_drugs_requires_session() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/drugs?query=synthetic-drug-a")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_drugs_search_filters_case_insensitively_and_empty_bounded() -> None:
    version = _new_version()
    _insert_release(version)
    with TestClient(app) as client:
        _login(client)

        exact = client.get("/api/v1/drugs", params={"query": SYN_A})
        assert exact.status_code == 200
        exact_body = exact.json()
        assert exact_body["catalog_version"] == CATALOG_VERSION
        assert exact_body["query"] == SYN_A
        assert any(item["concept_id"] == SYN_A for item in exact_body["results"])
        assert exact.headers["Cache-Control"] == "private, no-store"

        upper = client.get("/api/v1/drugs", params={"query": "SYNTHETIC-DRUG-A"})
        assert upper.status_code == 200
        assert {item["concept_id"] for item in upper.json()["results"]} == {
            item["concept_id"] for item in exact_body["results"]
        }

        missing = client.get("/api/v1/drugs", params={"query": "synthetic-no-such"})
        assert missing.status_code == 200
        assert missing.json()["results"] == []

        empty = client.get("/api/v1/drugs", params={"query": ""})
        assert empty.status_code == 200
        empty_body = empty.json()
        assert len(empty_body["results"]) <= 25
        assert {SYN_A, SYN_B} <= {item["concept_id"] for item in empty_body["results"]}
        assert all(
            item["concept_id"] and item["canonical_name"]
            for item in empty_body["results"]
        )
