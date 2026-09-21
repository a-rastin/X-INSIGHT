"""S07 slice 1: author saves/retrieves draft; shared read, author-only write.

Scope: save + retrieve + revision preconditions + state guards (T1, real PG).
Terminal/archived states use direct SQL setup (discard route is slice 4);
persistence is verified through public HTTP. Synthetic values only.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_drafts():
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
    """Unwrap {"encounter": {...}} envelope if present, else flat payload."""
    if isinstance(payload, dict) and isinstance(payload.get("encounter"), dict):
        return payload["encounter"]
    return payload


DRAFT = {"complaint": "synthetic-test-value"}


def test_author_saves_and_retrieves_draft_across_restart():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "draft-create-doctor")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0711111111", "draft-patient-1")
        encounter_id = encounter["id"]
        assert encounter["revision"] == 1

        patched = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=draft_headers(physician, "1"),
        )
        assert patched.status_code == 200
        saved = encounter_body(patched.json())
        assert saved["revision"] == 2
        assert saved["draft_data"] == {"complaint": "synthetic-test-value"}
        etag = patched.headers.get("etag")
        assert etag is not None
        assert "2" in etag

        # Restart recovery: brand-new client, same session cookies.
        session_cookie = physician.cookies.get("xinsight_session")
        csrf_cookie = physician.cookies.get("xinsight_csrf")
        assert session_cookie and csrf_cookie
        with TestClient(
            app,
            cookies={
                "xinsight_session": session_cookie,
                "xinsight_csrf": csrf_cookie,
            },
        ) as restarted:
            fetched = restarted.get(f"/api/v1/encounters/{encounter_id}")
            assert fetched.status_code == 200
            seen = encounter_body(fetched.json())
            assert seen["revision"] == 2
            assert seen["draft_data"] == {"complaint": "synthetic-test-value"}


def test_shared_read_but_author_only_write():
    with (
        TestClient(app) as admin,
        TestClient(app) as author,
        TestClient(app) as other,
    ):
        login(admin)
        create_physician(admin, "docA", "draft-create-docA")
        create_physician(admin, "docB", "draft-create-docB")
        login(author, "docA", "secret", "physician")
        login(other, "docB", "secret", "physician")
        _, encounter = create_patient(author, "0722222222", "draft-patient-2")
        encounter_id = encounter["id"]

        patched = author.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=draft_headers(author, "1"),
        )
        assert patched.status_code == 200

        other_got = other.get(f"/api/v1/encounters/{encounter_id}")
        assert other_got.status_code == 200
        assert encounter_body(other_got.json())["draft_data"] == {
            "complaint": "synthetic-test-value"
        }
        admin_got = admin.get(f"/api/v1/encounters/{encounter_id}")
        assert admin_got.status_code == 200
        assert encounter_body(admin_got.json())["draft_data"] == {
            "complaint": "synthetic-test-value"
        }

        other_patch = other.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=draft_headers(other, "2"),
        )
        assert other_patch.status_code == 403
        admin_patch = admin.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=draft_headers(admin, "2"),
        )
        assert admin_patch.status_code == 403


def test_unauthenticated_draft_access_denied():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "draft-create-doc-unauth")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0733333333", "draft-patient-3")
        encounter_id = encounter["id"]
    with TestClient(app) as anon:
        assert anon.get(f"/api/v1/encounters/{encounter_id}").status_code == 401
        denied = anon.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers={"If-Match": "1"},
        )
        assert denied.status_code == 401


def test_revision_precondition_required():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "draft-create-doc-rev")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0744444444", "draft-patient-4")
        encounter_id = encounter["id"]

        missing = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=draft_headers(physician, None),
        )
        assert missing.status_code == 412
        assert missing.json()["code"] == "STALE_REVISION"

        wrong = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=draft_headers(physician, "99"),
        )
        assert wrong.status_code == 412
        assert wrong.json()["code"] == "STALE_REVISION"


def test_terminal_invalid_and_archived_draft_rejected():
    # NOTE: discard route lands in slice 4, so terminal states are set via
    # direct SQL setup here (not a persistence assertion).
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "draft-create-doc-term")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0755555555", "draft-patient-5")
        encounter_id = encounter["id"]

        with db.transaction() as conn:
            conn.execute(
                text(
                    "UPDATE encounters SET state = 'discarded' "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": encounter_id},
            )
        discarded = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=draft_headers(physician, "1"),
        )
        assert discarded.status_code == 409

        with db.transaction() as conn:
            conn.execute(
                text(
                    "UPDATE encounters SET state = 'signed' "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": encounter_id},
            )
        signed = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=draft_headers(physician, "1"),
        )
        assert signed.status_code == 409

        _, fresh = create_patient(physician, "0766666666", "draft-patient-6")
        fresh_id = fresh["id"]
        non_object = physician.patch(
            f"/api/v1/encounters/{fresh_id}",
            json={"draft_data": "synthetic-test-value"},
            headers=draft_headers(physician, "1"),
        )
        assert non_object.status_code == 422

        with db.transaction() as conn:
            conn.execute(
                text(
                    "UPDATE patients SET archived = true "
                    "WHERE patient_id_text = '0766666666'"
                )
            )
        archived = physician.patch(
            f"/api/v1/encounters/{fresh_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=draft_headers(physician, "1"),
        )
        assert archived.status_code == 409


def test_malformed_patch_rejected_without_revision_bump():
    """S07 slice 3: failed (malformed) save returns 422, revision stays 1."""
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "draft-create-doc-malformed")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(
            physician, "0777777777", "draft-patient-malformed"
        )
        encounter_id = encounter["id"]

        non_object = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": "synthetic-test-value"},
            headers=draft_headers(physician, "1"),
        )
        assert non_object.status_code == 422

        unknown_field = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"bogus": "synthetic-test-value"},
            headers=draft_headers(physician, "1"),
        )
        assert unknown_field.status_code == 422

        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        seen = encounter_body(fetched.json())
        assert seen["revision"] == 1
        assert seen["draft_data"] == {}


# ---------------------------------------------------------------------------
# S07 slice 4 (RED): author-confirmed discard (POST /encounters/{id}/discard).
#
# No discard route exists yet: every test below currently fails with 404.
# Agreed contract under test:
# - POST /api/v1/encounters/{id}/discard with If-Match <current revision>
#   and JSON {"confirm": true} discards the draft (200, state discarded,
#   revision bumped). GET still returns the tombstone (state discarded,
#   draft_data preserved); PATCH and a second discard then return 409.
#   The patient row is retained (still listed via GET /patients?q=...).
# - Discard requires explicit confirmation: {"confirm": false} or a missing
#   confirm field is rejected with 422 and leaves revision untouched.
# - Revision precondition: missing/stale If-Match is rejected with
#   412 STALE_REVISION (same convention as PATCH).
# - Author-only mutation: other physicians and admins get 403, anonymous 401.
# - Draft discard takes If-Match only (no Idempotency-Key): the plan lists
#   Idempotency-Key for create/run/sign/note/addendum/recovery, not discard,
#   so these tests deliberately send no Idempotency-Key header and still
#   expect success. S04-style account commands are unaffected.
# - No background jobs tables exist yet, so there is nothing to cancel;
#   jobs cancellation is a documented no-op for this slice.
# - Audit: no admin audit HTTP exists until S52, so the encounter.discard
#   audit assertion below reads audit_events directly. This is the interim
#   side-channel already accepted in S03 (cf. test_identity._audit_rows);
#   tombstone + patient retention are verified through public HTTP.
# ---------------------------------------------------------------------------


def discard_headers(client, revision=None):
    """CSRF + optional If-Match headers; never an Idempotency-Key (by design)."""
    headers = {"X-CSRF-Token": client.cookies.get("xinsight_csrf")}
    if revision is not None:
        headers["If-Match"] = str(revision)
    return headers


def discard_audit_rows(encounter_id):
    with db.transaction() as conn:
        return (
            conn.execute(
                text(
                    "SELECT operation, actor_id, result_reference FROM audit_events "
                    "WHERE operation = 'encounter.discard' "
                    "AND result_reference = :ref"
                ),
                {"ref": str(encounter_id)},
            )
            .mappings()
            .all()
        )


def test_author_discards_draft_with_confirmation():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "discard-create-doctor")
        login(physician, "doctor", "secret", "physician")
        patient_id_text = "0788111111"
        _, encounter = create_patient(physician, patient_id_text, "discard-patient-1")
        encounter_id = encounter["id"]

        saved = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=draft_headers(physician, "1"),
        )
        assert saved.status_code == 200
        revision_before = encounter_body(saved.json())["revision"]

        # No Idempotency-Key header is sent here, by design (see note above).
        discarded = physician.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={"confirm": True},
            headers=discard_headers(physician, str(revision_before)),
        )
        assert discarded.status_code == 200
        seen = encounter_body(discarded.json())
        assert seen["state"] == "discarded"
        assert seen["revision"] == revision_before + 1
        assert seen["draft_data"] == {"complaint": "synthetic-test-value"}

        # Tombstone stays readable; edits are now rejected.
        tombstone = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert tombstone.status_code == 200
        kept = encounter_body(tombstone.json())
        assert kept["state"] == "discarded"
        assert kept["revision"] == revision_before + 1
        assert kept["draft_data"] == {"complaint": "synthetic-test-value"}

        repatch = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=draft_headers(physician, str(revision_before + 1)),
        )
        assert repatch.status_code == 409

        # The patient is retained, not deleted with the draft.
        listed = physician.get("/api/v1/patients", params={"q": patient_id_text})
        assert listed.status_code == 200
        assert any(
            item["patient_id"] == patient_id_text for item in listed.json()["items"]
        )

        # Interim side-channel (S03 precedent): audit tombstone exists.
        assert len(discard_audit_rows(encounter_id)) == 1


def test_discard_requires_explicit_confirmation():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "discard-create-doc-confirm")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0788222222", "discard-patient-2")
        encounter_id = encounter["id"]

        refused = physician.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={"confirm": False},
            headers=discard_headers(physician, "1"),
        )
        assert refused.status_code == 422

        missing = physician.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={},
            headers=discard_headers(physician, "1"),
        )
        assert missing.status_code == 422

        # Rejected discards leave the draft untouched.
        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        seen = encounter_body(fetched.json())
        assert seen["state"] == "draft"
        assert seen["revision"] == 1


def test_discard_rejects_stale_revision():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "discard-create-doc-stale")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0788333333", "discard-patient-3")
        encounter_id = encounter["id"]

        stale = physician.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={"confirm": True},
            headers=discard_headers(physician, "99"),
        )
        assert stale.status_code == 412
        assert stale.json()["code"] == "STALE_REVISION"

        absent = physician.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={"confirm": True},
            headers=discard_headers(physician, None),
        )
        assert absent.status_code == 412
        assert absent.json()["code"] == "STALE_REVISION"


def test_discard_forbidden_for_non_author_and_anonymous():
    with (
        TestClient(app) as admin,
        TestClient(app) as author,
        TestClient(app) as other,
    ):
        login(admin)
        create_physician(admin, "docDiscardA", "discard-create-docA")
        create_physician(admin, "docDiscardB", "discard-create-docB")
        login(author, "docDiscardA", "secret", "physician")
        login(other, "docDiscardB", "secret", "physician")
        _, encounter = create_patient(author, "0788444444", "discard-patient-4")
        encounter_id = encounter["id"]

        other_discard = other.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={"confirm": True},
            headers=discard_headers(other, "1"),
        )
        assert other_discard.status_code == 403

        admin_discard = admin.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={"confirm": True},
            headers=discard_headers(admin, "1"),
        )
        assert admin_discard.status_code == 403

        # The draft survives forbidden discard attempts.
        fetched = author.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        assert encounter_body(fetched.json())["state"] == "draft"

    with TestClient(app) as anon:
        denied = anon.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={"confirm": True},
            headers={"If-Match": "1"},
        )
        assert denied.status_code == 401


def test_double_discard_conflicts():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "doctor", "discard-create-doc-double")
        login(physician, "doctor", "secret", "physician")
        _, encounter = create_patient(physician, "0788555555", "discard-patient-5")
        encounter_id = encounter["id"]

        first = physician.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={"confirm": True},
            headers=discard_headers(physician, "1"),
        )
        assert first.status_code == 200
        revision_after = encounter_body(first.json())["revision"]

        second = physician.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={"confirm": True},
            headers=discard_headers(physician, str(revision_after)),
        )
        assert second.status_code == 409

        tombstone = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert tombstone.status_code == 200
        assert encounter_body(tombstone.json())["state"] == "discarded"
