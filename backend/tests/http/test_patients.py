"""S06 slice 1: physician patient registration + registration draft (T1, real PG)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_patients():
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


def headers(client, key):
    return {
        "X-CSRF-Token": client.cookies.get("xinsight_csrf"),
        "Idempotency-Key": key,
    }


def test_physician_registers_patient_with_registration_draft():
    """Response shape: {"schema_version":1,"patient":{...,"patient_id":"0012345678",
    "revision":1,...,"created_at":...Z},"encounter":{"id":...,"patient_id":...,
    "kind":"registration","state":"draft","revision":1,...}}; patient UUID + text ID."""
    body = {
        "first_name": "Anna",
        "last_name": "Muller",
        "sex": "F",
        "age": 30,
        "patient_id": "0012345678",
        "clinical_status": "first_time",
        "phone": "0123456789",
    }
    with (
        TestClient(app) as admin,
        TestClient(app) as physician,
        TestClient(app) as anon,
    ):
        assert anon.post("/api/v1/patients", json=body).status_code == 401
        login(admin)
        created = admin.post(
            "/api/v1/physicians",
            json={"username": "doctor", "password": "secret"},
            headers=headers(admin, "create-doctor"),
        )
        assert created.status_code == 201
        login(physician, "doctor", "secret", "physician")
        created_patient = physician.post(
            "/api/v1/patients", json=body, headers=headers(physician, "register-once")
        )
        assert created_patient.status_code == 201
        payload = created_patient.json()
        assert payload["schema_version"] == 1
        patient = payload["patient"]
        encounter = payload["encounter"]
        assert patient["patient_id"] == "0012345678"
        assert patient["revision"] == 1
        assert patient["created_at"].endswith("Z")
        assert patient["id"] and patient["patient_id"] != patient["id"]
        assert patient["first_name"] == "Anna"
        assert encounter["kind"] == "registration"
        assert encounter["state"] == "draft"
        assert encounter["revision"] == 1
        assert encounter["patient_id"] == patient["id"]
        assert (
            admin.post(
                "/api/v1/patients", json=body, headers=headers(admin, "admin-create")
            ).status_code
            == 403
        )


def test_patient_field_validation_rejects_bad_demographics():
    """Slice 2: 422 + field_errors for bad demographics; NFC name succeeds."""
    base = {
        "first_name": "Anna",
        "last_name": "Muller",
        "sex": "F",
        "age": 30,
        "patient_id": "0012345678",
        "clinical_status": "first_time",
        "phone": "0123456789",
    }
    fullwidth_id = "００12345678"
    cases: list[tuple[str, dict]] = [
        ("age 17", {**base, "age": 17}),
        ("age 100", {**base, "age": 100}),
        ("decimal age", {**base, "age": 30.5}),
        ("fullwidth id", {**base, "patient_id": fullwidth_id}),
        ("short id", {**base, "patient_id": "123"}),
        ("letter id", {**base, "patient_id": "123456789A"}),
        ("spaced id", {**base, "patient_id": " 0012345678 "}),
        ("hyphen name", {**base, "first_name": "Anne-Marie"}),
        ("apostrophe name", {**base, "first_name": "O'Brien"}),
        ("digit name", {**base, "first_name": "John3"}),
        ("space name", {**base, "first_name": "Mary Jane"}),
        ("empty name", {**base, "first_name": ""}),
    ]
    missing_sex = dict(base)
    del missing_sex["sex"]
    cases.append(("missing sex", missing_sex))
    missing_status = dict(base)
    del missing_status["clinical_status"]
    cases.append(("missing status", missing_status))
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        created = admin.post(
            "/api/v1/physicians",
            json={"username": "doctor", "password": "secret"},
            headers=headers(admin, "create-doctor"),
        )
        assert created.status_code == 201
        login(physician, "doctor", "secret", "physician")
        for i, (label, body) in enumerate(cases):
            response = physician.post(
                "/api/v1/patients", json=body, headers=headers(physician, f"val-{i}")
            )
            assert response.status_code == 422, label
            assert response.json()["field_errors"], label
        valid = {
            **base,
            "first_name": "Jose\u0301",
            "last_name": "Müller",
            "patient_id": "0098765432",
        }
        response = physician.post(
            "/api/v1/patients", json=valid, headers=headers(physician, "val-ok")
        )
        assert response.status_code == 201
        patient = response.json()["patient"]
        assert patient["first_name"] == "José"
        assert patient["last_name"] == "Müller"


def test_concurrent_duplicate_archived_and_idempotent_create():
    """Slice 3: exactly-one concurrent create; archived IDs still conflict;
    idempotent replay returns identical IDs; key reuse with new body 409s."""
    import concurrent.futures
    import threading

    body = {
        "first_name": "Anna",
        "last_name": "Muller",
        "sex": "F",
        "age": 30,
        "patient_id": "0055555555",
        "clinical_status": "first_time",
        "phone": "0123456789",
    }
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        created = admin.post(
            "/api/v1/physicians",
            json={"username": "doctor", "password": "secret"},
            headers=headers(admin, "create-doctor"),
        )
        assert created.status_code == 201
        login(physician, "doctor", "secret", "physician")
        session_cookie = physician.cookies.get("xinsight_session")
        csrf_token = physician.cookies.get("xinsight_csrf")
        assert session_cookie and csrf_token
        barrier = threading.Barrier(10)

        def attempt(i: int):
            barrier.wait(timeout=30)
            with TestClient(
                app,
                cookies={
                    "xinsight_session": session_cookie,
                    "xinsight_csrf": csrf_token,
                },
            ) as client:
                return client.post(
                    "/api/v1/patients",
                    json=body,
                    headers={
                        "X-CSRF-Token": csrf_token,
                        "Idempotency-Key": f"conc-{i}",
                    },
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(attempt, range(10)))
        statuses = sorted(r.status_code for r in responses)
        assert statuses.count(201) == 1, statuses
        assert statuses.count(409) == 9, statuses
        for response in responses:
            if response.status_code == 409:
                payload = response.json()
                assert payload["code"] == "CONFLICT"
                assert "already exists" in payload["message"]

        with db.transaction() as conn:
            conn.execute(
                text(
                    "UPDATE patients SET archived = true "
                    "WHERE patient_id_text = '0055555555'"
                )
            )
        archived_dup = physician.post(
            "/api/v1/patients", json=body, headers=headers(physician, "archived-retry")
        )
        assert archived_dup.status_code == 409
        assert archived_dup.json()["code"] == "CONFLICT"

        fresh = {**body, "patient_id": "0066666666"}
        first = physician.post(
            "/api/v1/patients", json=fresh, headers=headers(physician, "replay-key")
        )
        assert first.status_code == 201
        first_payload = first.json()
        replay = physician.post(
            "/api/v1/patients", json=fresh, headers=headers(physician, "replay-key")
        )
        assert replay.status_code == 201
        replay_payload = replay.json()
        assert replay_payload == first_payload
        assert replay_payload["patient"]["id"] == first_payload["patient"]["id"]
        assert replay_payload["encounter"]["id"] == first_payload["encounter"]["id"]
        changed = physician.post(
            "/api/v1/patients",
            json={**fresh, "first_name": "Maria"},
            headers=headers(physician, "replay-key"),
        )
        assert changed.status_code == 409
        assert changed.json()["code"] == "CONFLICT"


def test_directory_search_filter_pagination_shared():
    """Slice 4 (T1): shared directory search with filters + cursor pagination.

    Archived default: hidden unless ?archived=true (?archived=true returns
    only archived rows).
    """
    bodies = [
        {
            "first_name": "Anna",
            "last_name": "Muller",
            "sex": "F",
            "age": 30,
            "patient_id": "0012345678",
            "clinical_status": "first_time",
        },
        {
            "first_name": "Anna",
            "last_name": "Schmidt",
            "sex": "F",
            "age": 40,
            "patient_id": "0012345679",
            "clinical_status": "established",
        },
        {
            "first_name": "Bernd",
            "last_name": "Muller",
            "sex": "M",
            "age": 50,
            "patient_id": "0012345680",
            "clinical_status": "first_time",
        },
    ]
    with (
        TestClient(app) as admin,
        TestClient(app) as doc_a,
        TestClient(app) as doc_b,
        TestClient(app) as anon,
    ):
        login(admin)
        for i, name in enumerate(("docA", "docB")):
            created = admin.post(
                "/api/v1/physicians",
                json={"username": name, "password": "secret"},
                headers=headers(admin, f"dir-create-{i}"),
            )
            assert created.status_code == 201
        login(doc_a, "docA", "secret", "physician")
        login(doc_b, "docB", "secret", "physician")
        for i, body in enumerate(bodies):
            response = doc_a.post(
                "/api/v1/patients", json=body, headers=headers(doc_a, f"dir-{i}")
            )
            assert response.status_code == 201

        listed = doc_b.get("/api/v1/patients")
        assert listed.status_code == 200
        assert listed.json()["schema_version"] == 1
        assert len(listed.json()["items"]) == 3

        by_name = doc_b.get("/api/v1/patients", params={"q": "Anna"})
        assert by_name.status_code == 200
        assert len(by_name.json()["items"]) == 2

        by_id = doc_b.get("/api/v1/patients", params={"q": "0012345678"})
        assert by_id.status_code == 200
        assert len(by_id.json()["items"]) == 1
        assert by_id.json()["items"][0]["patient_id"] == "0012345678"

        by_status = doc_b.get(
            "/api/v1/patients", params={"clinical_status": "established"}
        )
        assert by_status.status_code == 200
        assert len(by_status.json()["items"]) == 1
        assert by_status.json()["items"][0]["patient_id"] == "0012345679"

        bad_status = doc_b.get("/api/v1/patients", params={"clinical_status": "bogus"})
        assert bad_status.status_code == 422

        first = doc_b.get("/api/v1/patients", params={"limit": 2})
        assert first.status_code == 200
        assert len(first.json()["items"]) == 2
        cursor = first.json()["next_cursor"]
        assert cursor
        second = doc_b.get("/api/v1/patients", params={"limit": 2, "cursor": cursor})
        assert second.status_code == 200
        assert len(second.json()["items"]) == 1
        first_ids = {item["id"] for item in first.json()["items"]}
        second_ids = {item["id"] for item in second.json()["items"]}
        assert not first_ids & second_ids
        assert len(first_ids | second_ids) == 3

        assert anon.get("/api/v1/patients").status_code == 401

        as_admin = admin.get("/api/v1/patients")
        assert as_admin.status_code == 200
        assert len(as_admin.json()["items"]) == 3

        with db.transaction() as conn:
            conn.execute(
                text(
                    "UPDATE patients SET archived = true "
                    "WHERE patient_id_text = '0012345680'"
                )
            )
        assert len(doc_b.get("/api/v1/patients").json()["items"]) == 2
        only_archived = doc_b.get("/api/v1/patients", params={"archived": True})
        assert only_archived.status_code == 200
        assert len(only_archived.json()["items"]) == 1
        assert only_archived.json()["items"][0]["patient_id"] == "0012345680"
