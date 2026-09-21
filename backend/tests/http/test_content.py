"""Slice 4 (RED): authenticated released-only content routes (T1, real PG).

No content router exists yet: GET /api/v1/content/assessments/* is 404.
Agreed contract under test:
- GET /api/v1/content/assessments/{type}, type in {diagnosis, panss, cssrs}.
- Active session required: anonymous gets 401 (generic envelope).
- Only RELEASED packages served: envelope["review_status"] == "released"
  AND envelope["definition"] passes the v1 loader. Real repo files are all
  draft (review_status "draft", key "definition_proposal") -> 404.
- Unknown type -> 404.
- 200 body: {"schema_version": 1, "assessment_type": <type>,
  "definition_version": str, "definition": {...}} with
  Cache-Control private, no-store.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_content():
    with db.transaction() as conn:
        conn.execute(text("TRUNCATE sessions, users, audit_events"))
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


def test_anonymous_content_denied():
    with TestClient(app) as anon:
        response = anon.get("/api/v1/content/assessments/panss")
    assert response.status_code == 401


def test_unknown_assessment_type_not_found():
    with TestClient(app) as client:
        login(client)
        response = client.get("/api/v1/content/assessments/nonexistent")
    assert response.status_code == 404


def test_draft_definitions_not_exposed():
    with TestClient(app) as client:
        login(client)
        for assessment_type in ("diagnosis", "panss", "cssrs"):
            response = client.get(f"/api/v1/content/assessments/{assessment_type}")
            assert response.status_code == 404


def test_released_definition_served_from_content_dir(tmp_path, monkeypatch):
    from x_insight.assessments import content as content_module

    synthetic_definition = {
        "schema_version": 1,
        "assessment_type": "panss",
        "definition_version": "synthetic-released-v1",
        "items": [{"id": "q1", "kind": "int", "min": 1, "max": 7}],
        "required_item_ids": ["q1"],
        "result_rules": [{"id": "total", "op": "sum", "items": ["q1"]}],
    }
    (tmp_path / "panss.json").write_text(
        json.dumps({"review_status": "released", "definition": synthetic_definition})
    )
    (tmp_path / "diagnosis.json").write_text(
        json.dumps({"review_status": "draft", "definition_proposal": {}})
    )
    # Assumes the route reads CONTENT_DIR at request time; if the
    # implementation instead resolves the real dir only, this test defines
    # the required seam (do not weaken it).
    monkeypatch.setattr(content_module, "CONTENT_DIR", tmp_path)
    with TestClient(app) as client:
        login(client)
        served = client.get("/api/v1/content/assessments/panss")
        assert served.status_code == 200
        body = served.json()
        assert body["definition_version"] == "synthetic-released-v1"
        assert body["assessment_type"] == "panss"
        assert "definition" in body
        item_ids = [item["id"] for item in body["definition"]["items"]]
        assert "q1" in item_ids
        cache_control = served.headers.get("cache-control", "")
        assert "private" in cache_control
        assert "no-store" in cache_control
        draft = client.get("/api/v1/content/assessments/diagnosis")
        assert draft.status_code == 404
