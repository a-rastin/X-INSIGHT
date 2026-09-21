"""S13 failing-first: attributed page notes, append-only, separate history.

T1 scope: real PostgreSQL via TestClient; persistence observed only
through public HTTP. SYNTHETIC VALUES ONLY. Follows test_drafts.py:
TRUNCATE existing tables, admin creates physicians, physician creates
patient plus registration draft.

Assumed minimal route/shape for dev-backend (NOT implemented -- RED):
- POST /api/v1/encounters/{id}/notes {"page","text"} (+ optional
  Idempotency-Key) -> 201 {"schema_version":1,"note":{"id",
  "encounter_id","page","text","author_id","author_display",
  "created_at"}}. Client author_id/author_display/created_at ignored;
  provenance is server-derived. Same Idempotency-Key retry returns the
  original note, creating exactly one note.
- GET /api/v1/encounters/{id}/notes -> 200 {"schema_version":1,
  "items":[<note>,...]}.
- No edit route: PUT/PATCH/DELETE .../notes/{note_id} -> 404/405 for the
  author. Non-author POST/PUT/PATCH/DELETE -> 403; anon -> 401.
- Notes listed separately: note text never appears in draft_data/history.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_notes():
    # No notes table exists yet; truncate only existing relations so setup
    # itself stays green and the missing route is the RED signal.
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


def note_headers(client, key=None):
    headers = {"X-CSRF-Token": client.cookies.get("xinsight_csrf")}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def create_physician(admin, username, key):
    created = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": "secret"},
        headers=note_headers(admin, key),
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
        "/api/v1/patients", json=body, headers=note_headers(physician, key)
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["patient"], payload["encounter"]


def notes_url(encounter_id):
    return f"/api/v1/encounters/{encounter_id}/notes"


def note_item_url(encounter_id, note_id):
    return f"/api/v1/encounters/{encounter_id}/notes/{note_id}"


def resumed_client(client):
    session_cookie = client.cookies.get("xinsight_session")
    csrf_cookie = client.cookies.get("xinsight_csrf")
    assert session_cookie and csrf_cookie
    return TestClient(
        app,
        cookies={
            "xinsight_session": session_cookie,
            "xinsight_csrf": csrf_cookie,
        },
    )


def test_author_adds_note_visible_after_resume_idempotent_retry():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "notedocauthor", "notes-create-author")
        author = login(physician, "notedocauthor", "secret", "physician")["user"]
        _, encounter = create_patient(physician, "0799000001", "notes-patient-1")
        encounter_id = encounter["id"]
        url = notes_url(encounter_id)

        created = physician.post(
            url,
            json={"page": "demographics", "text": "synthetic-note-demographics"},
            headers=note_headers(physician, "notes-once-1"),
        )
        assert created.status_code == 201
        note = created.json()["note"]
        assert note["encounter_id"] == encounter_id
        assert note["page"] == "demographics"
        assert note["text"] == "synthetic-note-demographics"
        assert note["author_id"] == author["id"]
        assert note["author_display"] == author["username"]
        assert note["created_at"].endswith("Z")
        assert note["id"]

        listed = physician.get(url)
        assert listed.status_code == 200
        assert listed.json()["items"] == [note]

        retried = physician.post(
            url,
            json={"page": "demographics", "text": "synthetic-note-demographics"},
            headers=note_headers(physician, "notes-once-1"),
        )
        assert retried.status_code == 201
        assert retried.json()["note"]["id"] == note["id"]
        again = physician.get(url)
        assert again.status_code == 200
        assert len(again.json()["items"]) == 1

        with resumed_client(physician) as resumed:
            second = resumed.post(
                url,
                json={"page": "history", "text": "synthetic-note-no-key"},
                headers=note_headers(resumed, "notes-once-2"),
            )
            assert second.status_code == 201
            assert second.json()["note"]["id"] != note["id"]

            visible = resumed.get(url)
            assert visible.status_code == 200
            items = visible.json()["items"]
            assert len(items) == 2
            texts = {item["text"] for item in items}
            assert texts == {"synthetic-note-demographics", "synthetic-note-no-key"}

            draft = resumed.get(f"/api/v1/encounters/{encounter_id}")
            assert draft.status_code == 200


def test_only_author_may_write_notes():
    with (
        TestClient(app) as admin,
        TestClient(app) as author_client,
        TestClient(app) as other_client,
    ):
        login(admin)
        create_physician(admin, "notedocauthor", "notes-create-author-b")
        create_physician(admin, "notedocother", "notes-create-other")
        login(author_client, "notedocauthor", "secret", "physician")
        login(other_client, "notedocother", "secret", "physician")
        _, encounter = create_patient(author_client, "0799000002", "notes-patient-2")
        encounter_id = encounter["id"]
        url = notes_url(encounter_id)

        created = author_client.post(
            url,
            json={"page": "demographics", "text": "synthetic-note-authored"},
            headers=note_headers(author_client, "notes-author-write"),
        )
        assert created.status_code == 201
        item_url = note_item_url(encounter_id, created.json()["note"]["id"])

        other_post = other_client.post(
            url,
            json={"page": "demographics", "text": "synthetic-note-intruder"},
            headers=note_headers(other_client, "notes-other-write"),
        )
        assert other_post.status_code == 403

        admin_post = admin.post(
            url,
            json={"page": "demographics", "text": "synthetic-note-admin"},
            headers=note_headers(admin, "notes-admin-write"),
        )
        assert admin_post.status_code == 403

        put_edit = author_client.put(
            item_url,
            json={"page": "demographics", "text": "synthetic-note-edited"},
            headers=note_headers(author_client),
        )
        assert put_edit.status_code in (404, 405)
        patch_edit = author_client.patch(
            item_url,
            json={"text": "synthetic-note-edited"},
            headers=note_headers(author_client),
        )
        assert patch_edit.status_code in (404, 405)
        delete_edit = author_client.delete(
            item_url, headers=note_headers(author_client)
        )
        assert delete_edit.status_code in (404, 405)

        for method in ("put", "patch"):
            other_edit = getattr(other_client, method)(
                item_url,
                json={"text": "synthetic-note-edited"},
                headers=note_headers(other_client),
            )
            assert other_edit.status_code in (403, 404, 405)
            admin_edit = getattr(admin, method)(
                item_url,
                json={"text": "synthetic-note-edited"},
                headers=note_headers(admin),
            )
            assert admin_edit.status_code in (403, 404, 405)
        other_delete = other_client.delete(item_url, headers=note_headers(other_client))
        assert other_delete.status_code in (403, 404, 405)
        admin_delete = admin.delete(item_url, headers=note_headers(admin))
        assert admin_delete.status_code in (403, 404, 405)

        survived = author_client.get(url)
        assert survived.status_code == 200
        texts = [item["text"] for item in survived.json()["items"]]
        assert texts == ["synthetic-note-authored"]

    with TestClient(app) as anon:
        assert (
            anon.post(
                url,
                json={"page": "demographics", "text": "synthetic-note-anon"},
            ).status_code
            == 401
        )
        assert anon.get(url).status_code == 401


def test_note_provenance_is_server_derived():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "notedocauthor", "notes-create-author-c")
        author = login(physician, "notedocauthor", "secret", "physician")["user"]
        _, encounter = create_patient(physician, "0799000003", "notes-patient-3")
        url = notes_url(encounter["id"])

        forged = physician.post(
            url,
            json={
                "page": "demographics",
                "text": "synthetic-note-provenance",
                "author_id": "00000000-0000-0000-0000-000000000000",
                "author_display": "forged-display",
                "created_at": "2000-01-01T00:00:00Z",
            },
            headers=note_headers(physician, "notes-provenance"),
        )
        assert forged.status_code == 201
        note = forged.json()["note"]
        assert note["author_id"] == author["id"]
        assert note["author_id"] != "00000000-0000-0000-0000-000000000000"
        assert note["author_display"] == author["username"]
        assert note["author_display"] != "forged-display"
        assert note["created_at"].endswith("Z")
        assert note["created_at"] != "2000-01-01T00:00:00Z"
        assert note["page"] == "demographics"
        assert note["text"] == "synthetic-note-provenance"

        listed = physician.get(url)
        assert listed.status_code == 200
        assert listed.json()["items"] == [note]


def test_notes_are_listed_separately_from_history():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "notedocauthor", "notes-create-author-d")
        login(physician, "notedocauthor", "secret", "physician")
        _, encounter = create_patient(physician, "0799000004", "notes-patient-4")
        encounter_id = encounter["id"]

        created = physician.post(
            notes_url(encounter_id),
            json={"page": "demographics", "text": "synthetic-note-never-history"},
            headers=note_headers(physician, "notes-separation"),
        )
        assert created.status_code == 201

        listed = physician.get(notes_url(encounter_id))
        assert listed.status_code == 200
        texts = [item["text"] for item in listed.json()["items"]]
        assert texts == ["synthetic-note-never-history"]

        draft = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert draft.status_code == 200
        draft_data = draft.json()["encounter"]["draft_data"]
        assert "synthetic-note-never-history" not in json.dumps(draft_data)
        history = draft_data.get("history")
        assert history is None or "synthetic-note-never-history" not in json.dumps(
            history
        )


def test_note_shape_requires_page_and_text():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "notedocauthor", "notes-create-author-e")
        login(physician, "notedocauthor", "secret", "physician")
        _, encounter = create_patient(physician, "0799000005", "notes-patient-5")
        url = notes_url(encounter["id"])

        empty = physician.post(
            url, json={}, headers=note_headers(physician, "notes-shape-empty")
        )
        assert empty.status_code == 422
        no_text = physician.post(
            url,
            json={"page": "demographics"},
            headers=note_headers(physician, "notes-shape-no-text"),
        )
        assert no_text.status_code == 422
        no_page = physician.post(
            url,
            json={"text": "synthetic-note-no-page"},
            headers=note_headers(physician, "notes-shape-no-page"),
        )
        assert no_page.status_code == 422
        blank = physician.post(
            url,
            json={"page": "demographics", "text": ""},
            headers=note_headers(physician, "notes-shape-blank"),
        )
        assert blank.status_code == 422

        listed = physician.get(url)
        assert listed.status_code == 200
        assert listed.json()["items"] == []
