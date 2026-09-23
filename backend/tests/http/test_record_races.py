"""S51 slice 1 (RED): admin archive/unarchive + archived-patient guards (T1).

Scope: plan.md 2.1/2.3/4.3; tasks.md S51.1; FR-22/FR-23, NFR-04. No
archive routes exist yet: every archive/unarchive assertion below
currently fails with 404 (missing route).

Agreed contract under test:
- POST /api/v1/patients/{id}/archive with If-Match <current revision>
  plus CSRF + Idempotency-Key archives (200, archived true, revision
  bumped, ETag, attributed audit row). Admin-only: physician 403,
  anonymous 401; stale If-Match 412.
- POST /api/v1/patients/{id}/unarchive (same headers, admin-only)
  restores archived false with a revision bump; the original author can
  then PATCH the draft again (200 with fresh revision).
- While archived: POST /patients/{id}/encounters 409, PATCH
  /encounters/{id} 409, POST /encounters/{id}/sign 409, PATCH
  /encounters/{id}/secondary-plan 409.
- While archived: GET /patients hides by default, ?archived=true shows;
  GET /encounters/{id} stays readable by author, other physician, and
  admin; the draft history (GET list) is retained.
- No permanent delete route exists: DELETE on /patients/{id} (and on
  /patients) is 404/405.

All assertions go through public HTTP against real PostgreSQL; no mocks,
no synthetic-clinical shortcuts. Audit is read via direct SQL (S03
precedent) since no admin audit HTTP exists yet.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_record_races():
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


def mutation_headers(client, key=None, revision=None):
    headers = {"X-CSRF-Token": client.cookies.get("xinsight_csrf")}
    if key is not None:
        headers["Idempotency-Key"] = key
    if revision is not None:
        headers["If-Match"] = str(revision)
    return headers


def create_physician(admin, username, key):
    created = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": "secret"},
        headers=mutation_headers(admin, key),
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
        "/api/v1/patients", json=body, headers=mutation_headers(physician, key)
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["patient"], payload["encounter"]


def archive_audit_rows(patient_id):
    with db.transaction() as conn:
        return (
            conn.execute(
                text(
                    "SELECT operation, actor_id, result_reference FROM audit_events "
                    "WHERE result_reference = :ref AND operation ILIKE '%archiv%'"
                ),
                {"ref": str(patient_id)},
            )
            .mappings()
            .all()
        )


def encounter_body(payload):
    if isinstance(payload, dict) and isinstance(payload.get("encounter"), dict):
        return payload["encounter"]
    return payload


def test_admin_archives_patient_with_revision_and_audit():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "archdoc", "archive-create-archdoc")
        login(physician, "archdoc", "secret", "physician")
        patient, _encounter = create_patient(physician, "0811111111", "archive-p1")
        assert patient["archived"] is False
        assert patient["revision"] == 1

        archived = admin.post(
            f"/api/v1/patients/{patient['id']}/archive",
            headers=mutation_headers(admin, "archive-key-1", revision="1"),
        )
        assert archived.status_code == 200
        seen = archived.json()["patient"]
        assert seen["id"] == patient["id"]
        assert seen["archived"] is True
        assert seen["revision"] == patient["revision"] + 1
        assert "2" in (archived.headers.get("etag") or "")

        assert len(archive_audit_rows(patient["id"])) >= 1


def test_archive_forbidden_for_physician_anon_and_stale_revision():
    with (
        TestClient(app) as admin,
        TestClient(app) as physician,
        TestClient(app) as anon,
    ):
        login(admin)
        create_physician(admin, "archdocB", "archive-create-archdocB")
        login(physician, "archdocB", "secret", "physician")
        patient, _encounter = create_patient(physician, "0812222222", "archive-p2")

        physician_archive = physician.post(
            f"/api/v1/patients/{patient['id']}/archive",
            headers=mutation_headers(physician, "archive-key-doc", revision="1"),
        )
        assert physician_archive.status_code == 403

        anon_archive = anon.post(
            f"/api/v1/patients/{patient['id']}/archive",
            headers={"If-Match": "1", "Idempotency-Key": "archive-key-anon"},
        )
        assert anon_archive.status_code == 401

        stale = admin.post(
            f"/api/v1/patients/{patient['id']}/archive",
            headers=mutation_headers(admin, "archive-key-stale", revision="99"),
        )
        assert stale.status_code == 412

        # Failed attempts leave the patient unarchived at revision 1.
        listed = physician.get("/api/v1/patients", params={"q": "0812222222"})
        assert listed.status_code == 200
        assert listed.json()["items"][0]["archived"] is False
        assert listed.json()["items"][0]["revision"] == 1


def test_archived_patient_blocks_new_encounters_edits_sign_and_plan():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "archdocC", "archive-create-archdocC")
        login(physician, "archdocC", "secret", "physician")
        patient, encounter = create_patient(physician, "0813333333", "archive-p3")
        encounter_id = encounter["id"]

        archived = admin.post(
            f"/api/v1/patients/{patient['id']}/archive",
            headers=mutation_headers(admin, "archive-key-3", revision="1"),
        )
        assert archived.status_code == 200

        followup = physician.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": encounter_id},
            headers=mutation_headers(physician, "archive-block-followup"),
        )
        assert followup.status_code == 409

        patched = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=mutation_headers(physician, revision="1"),
        )
        assert patched.status_code == 409

        signed = physician.post(
            f"/api/v1/encounters/{encounter_id}/sign",
            json={
                "encounter_revision": 1,
                "run_id": str(uuid.uuid4()),
                "secondary_plan_revision": 0,
                "review_acknowledgments": [],
                "baseline_acknowledgment": True,
            },
            headers=mutation_headers(
                physician, "archive-block-sign", revision="1"
            ),
        )
        assert signed.status_code == 409

        planned = physician.patch(
            f"/api/v1/encounters/{encounter_id}/secondary-plan",
            json={"text": "SYNTHETIC-ARCHIVE-PLAN-test-only"},
            headers=mutation_headers(
                physician, "archive-block-plan", revision="0"
            ),
        )
        assert planned.status_code == 409


def test_archived_patient_preserves_reads_and_draft_history():
    with (
        TestClient(app) as admin,
        TestClient(app) as author,
        TestClient(app) as other,
    ):
        login(admin)
        create_physician(admin, "archdocD", "archive-create-archdocD")
        create_physician(admin, "archdocE", "archive-create-archdocE")
        login(author, "archdocD", "secret", "physician")
        login(other, "archdocE", "secret", "physician")
        patient, encounter = create_patient(author, "0814444444", "archive-p4")
        encounter_id = encounter["id"]

        saved = author.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=mutation_headers(author, revision="1"),
        )
        assert saved.status_code == 200

        archived = admin.post(
            f"/api/v1/patients/{patient['id']}/archive",
            headers=mutation_headers(admin, "archive-key-4", revision="1"),
        )
        assert archived.status_code == 200

        # Default directory hides archived; explicit filter shows them.
        assert author.get("/api/v1/patients").json()["items"] == []
        only_archived = author.get("/api/v1/patients", params={"archived": True})
        assert only_archived.status_code == 200
        assert len(only_archived.json()["items"]) == 1
        assert only_archived.json()["items"][0]["patient_id"] == "0814444444"

        # Draft stays readable by author, other physician, and admin.
        for reader in (author, other, admin):
            fetched = reader.get(f"/api/v1/encounters/{encounter_id}")
            assert fetched.status_code == 200
            seen = encounter_body(fetched.json())
            assert seen["draft_data"] == {"complaint": "synthetic-test-value"}

        # Draft history is retained in the per-patient list.
        listed = author.get(f"/api/v1/patients/{patient['id']}/encounters")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [encounter_id]


def test_unarchive_restores_author_edit_and_no_delete_route_exists():
    with (
        TestClient(app) as admin,
        TestClient(app) as physician,
        TestClient(app) as anon,
    ):
        login(admin)
        create_physician(admin, "archdocF", "archive-create-archdocF")
        login(physician, "archdocF", "secret", "physician")
        patient, encounter = create_patient(physician, "0815555555", "archive-p5")
        encounter_id = encounter["id"]

        archived = admin.post(
            f"/api/v1/patients/{patient['id']}/archive",
            headers=mutation_headers(admin, "archive-key-5", revision="1"),
        )
        assert archived.status_code == 200
        assert archived.json()["patient"]["revision"] == 2

        # Physician unarchive is forbidden; the patient stays archived.
        physician_unarchive = physician.post(
            f"/api/v1/patients/{patient['id']}/unarchive",
            headers=mutation_headers(
                physician, "unarchive-key-doc", revision="2"
            ),
        )
        assert physician_unarchive.status_code == 403

        restored = admin.post(
            f"/api/v1/patients/{patient['id']}/unarchive",
            headers=mutation_headers(admin, "unarchive-key-1", revision="2"),
        )
        assert restored.status_code == 200
        seen = restored.json()["patient"]
        assert seen["archived"] is False
        assert seen["revision"] == 3

        # Author edit access is restored at the fresh revision.
        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        revision = encounter_body(fetched.json())["revision"]
        patched = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=mutation_headers(physician, revision=str(revision)),
        )
        assert patched.status_code == 200
        assert encounter_body(patched.json())["revision"] == revision + 1

        # No permanent delete route exists.
        assert (
            admin.delete(f"/api/v1/patients/{patient['id']}").status_code in (404, 405)
        )
        assert admin.delete("/api/v1/patients").status_code in (404, 405)
        assert (
            anon.delete(f"/api/v1/patients/{patient['id']}").status_code
            in (401, 404, 405)
        )


# ---------------------------------------------------------------------------
# S51 slice 2 (RED): deactivation with real draft-set + queued-work revocation.
#
# Scope: plan.md 2.1; FR-04, NFR-04. Seam T1 only (public HTTP against real
# PostgreSQL; audit/run-status reads via direct SQL per S03 precedent).
# Slice-1 tests above are unchanged.
#
# Agreed contract under test (backend stub still returns an empty draft set
# and revokes sessions only, so the draft-set / cancellation / tombstone
# assertions below currently fail):
# - GET /api/v1/physicians/{id}/deactivation-review returns the real draft
#   set (encounter ids/kind/state/revision) plus a draft_set_revision hash;
#   creating a new draft changes the hash, so deactivate with the stale
#   revision is rejected with 412.
# - Deactivate {draft_action retain} revokes the author's sessions (login
#   401, PATCH own draft 401/403), keeps the draft readable by admin, and
#   marks the author's queued run/jobs cancelled (no longer eligible).
# - Deactivate {draft_action discard, confirm_discard true, fresh revision}
#   tombstones the author's drafts (state discarded, draft_data preserved,
#   GET readable, PATCH 409, audit retained); missing confirm is 422 and a
#   wrong revision is 412.
# - Reactivate restores author edits of retained drafts (PATCH 200), never
#   resurrects discarded drafts (PATCH 409, state discarded), and never
#   changes attribution (author_id identical).
# ---------------------------------------------------------------------------

import json


def _s51_reset_full():
    """Clear reasoning/bundle tables the slice-1 fixture does not truncate."""
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE runs, run_questions, reasoning_jobs, "
                "reasoning_attempts, run_question_artifacts, run_proposals, "
                "model_bundle_pointers, model_bundle_events, "
                "mcp_question_grants, provider_configs, "
                "provider_config_pointer, queue_fairness, "
                "ddi_dataset_releases"
            )
        )


def _s51_physician_id(admin, username):
    listing = admin.get("/api/v1/physicians")
    assert listing.status_code == 200
    for item in listing.json()["items"]:
        if item["username"] == username:
            return item["id"]
    raise AssertionError(f"physician {username} not found")


def _s51_account_etag(admin, physician_id):
    found = admin.get(f"/api/v1/physicians/{physician_id}")
    assert found.status_code == 200
    return found.headers["etag"]


def _s51_insert_registration_bundle():
    pins = {"questions": [{"question_key": "s51-q1", "version": "v1"}]}
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO model_bundle_pointers "
                "(workflow, revision, bundle_hash, pins) "
                "VALUES ('registration', 1, 'synthetic-bundle-hash-s51', "
                "CAST(:pins AS jsonb)) ON CONFLICT (workflow) DO UPDATE "
                "SET revision = 1, "
                "bundle_hash = 'synthetic-bundle-hash-s51', "
                "pins = CAST(:pins AS jsonb)"
            ),
            {"pins": json.dumps(pins)},
        )


def _s51_start_run(author, encounter_id, key):
    fetched = author.get(f"/api/v1/encounters/{encounter_id}")
    assert fetched.status_code == 200
    revision = encounter_body(fetched.json())["revision"]
    started = author.post(
        f"/api/v1/encounters/{encounter_id}/runs",
        json={"encounter_revision": revision},
        headers=mutation_headers(author, key, revision=str(revision)),
    )
    assert started.status_code == 202
    return started.json()["run_id"]


def _s51_run_status(run_id):
    with db.transaction() as conn:
        return conn.execute(
            text("SELECT status FROM runs WHERE id = :id"),
            {"id": str(run_id)},
        ).scalar()


def _s51_job_statuses(run_id):
    with db.transaction() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT status FROM reasoning_jobs WHERE run_id = :id"
                ),
                {"id": str(run_id)},
            )
            .mappings()
            .all()
        )
    return [str(row["status"]) for row in rows]


def _s51_deactivate_audit_rows(physician_id):
    with db.transaction() as conn:
        return (
            conn.execute(
                text(
                    "SELECT operation, details FROM audit_events "
                    "WHERE operation = 'physician.deactivate' "
                    "AND result_reference = :ref"
                ),
                {"ref": str(physician_id)},
            )
            .mappings()
            .all()
        )


def _s51_draft_entry_for(drafts, encounter_id):
    matches = [
        item
        for item in drafts
        if isinstance(item, dict)
        and encounter_id in {str(value) for value in item.values()}
    ]
    assert matches, f"encounter {encounter_id} missing from draft set"
    return matches[0]


def test_deactivation_review_reflects_real_draft_set_and_stale_revision_rejected():
    _s51_reset_full()
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "sreviewdoc", "s51-review-create")
        physician_id = _s51_physician_id(admin, "sreviewdoc")
        login(physician, "sreviewdoc", "secret", "physician")
        _patient, encounter = create_patient(
            physician, "0851111111", "s51-review-p1"
        )
        encounter_id = encounter["id"]

        review_response = admin.get(
            f"/api/v1/physicians/{physician_id}/deactivation-review"
        )
        assert review_response.status_code == 200
        review = review_response.json()
        assert review["physician_id"] == physician_id
        assert isinstance(review["drafts"], list)
        assert len(review["drafts"]) >= 1
        entry = _s51_draft_entry_for(review["drafts"], encounter_id)
        assert entry["kind"] == encounter["kind"]
        assert entry["state"] == "draft"
        assert int(entry["revision"]) == int(encounter["revision"])
        assert isinstance(review["draft_set_revision"], str)
        assert review["draft_set_revision"]
        stale_revision = review["draft_set_revision"]

        # A new draft changes the reviewed set and invalidates the old hash.
        _patient2, encounter2 = create_patient(
            physician, "0851222222", "s51-review-p2"
        )
        reread = admin.get(
            f"/api/v1/physicians/{physician_id}/deactivation-review"
        ).json()
        assert len(reread["drafts"]) >= 2
        _s51_draft_entry_for(reread["drafts"], encounter2["id"])
        assert reread["draft_set_revision"] != stale_revision

        etag = _s51_account_etag(admin, physician_id)
        stale = admin.post(
            f"/api/v1/physicians/{physician_id}/deactivate",
            json={
                "draft_action": "retain",
                "draft_set_revision": stale_revision,
            },
            headers=mutation_headers(admin, "s51-review-stale", revision=etag),
        )
        assert stale.status_code == 412


def test_deactivation_retain_revokes_sessions_and_cancels_queued_work():
    _s51_reset_full()
    _s51_insert_registration_bundle()
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "sretaindoc", "s51-retain-create")
        physician_id = _s51_physician_id(admin, "sretaindoc")
        login(physician, "sretaindoc", "secret", "physician")
        _patient, encounter = create_patient(
            physician, "0852333333", "s51-retain-p1"
        )
        encounter_id = encounter["id"]

        run_id = _s51_start_run(physician, encounter_id, "s51-retain-run-1")
        assert physician.get(f"/api/v1/runs/{run_id}").status_code == 200

        review = admin.get(
            f"/api/v1/physicians/{physician_id}/deactivation-review"
        ).json()
        _s51_draft_entry_for(review["drafts"], encounter_id)
        etag = _s51_account_etag(admin, physician_id)
        deactivated = admin.post(
            f"/api/v1/physicians/{physician_id}/deactivate",
            json={
                "draft_action": "retain",
                "draft_set_revision": review["draft_set_revision"],
            },
            headers=mutation_headers(admin, "s51-retain-deact", revision=etag),
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["active"] is False

        # Sessions are revoked: login is refused and the old session is dead.
        assert physician.get("/api/v1/me").status_code == 401
        with TestClient(app) as probe:
            assert (
                probe.post(
                    "/api/v1/auth/login",
                    json={
                        "username": "sretaindoc",
                        "password": "secret",
                        "role": "physician",
                    },
                ).status_code
                == 401
            )
        repatch = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=mutation_headers(physician, revision="1"),
        )
        assert repatch.status_code in (401, 403)

        # The retained draft stays readable by the administrator.
        readable = admin.get(f"/api/v1/encounters/{encounter_id}")
        assert readable.status_code == 200
        assert encounter_body(readable.json())["state"] == "draft"

        # Queued work for the deactivated author is cancelled, never eligible.
        assert _s51_run_status(run_id) == "cancelled"
        job_statuses = _s51_job_statuses(run_id)
        assert job_statuses, "expected queued-work rows for the run"
        assert all(
            status not in ("queued", "claimed") for status in job_statuses
        )


def test_deactivation_discard_tombstones_drafts_with_confirmation():
    _s51_reset_full()
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "sdiscarddoc", "s51-discard-create")
        physician_id = _s51_physician_id(admin, "sdiscarddoc")
        login(physician, "sdiscarddoc", "secret", "physician")
        _patient, encounter = create_patient(
            physician, "0853444444", "s51-discard-p1"
        )
        encounter_id = encounter["id"]
        saved = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=mutation_headers(physician, revision="1"),
        )
        assert saved.status_code == 200
        before = encounter_body(saved.json())
        author_before = before["author_id"]
        draft_before = before["draft_data"]
        revision_before = before["revision"]

        review = admin.get(
            f"/api/v1/physicians/{physician_id}/deactivation-review"
        ).json()
        _s51_draft_entry_for(review["drafts"], encounter_id)
        etag = _s51_account_etag(admin, physician_id)

        # Discard demands explicit confirmation.
        missing = admin.post(
            f"/api/v1/physicians/{physician_id}/deactivate",
            json={
                "draft_action": "discard",
                "draft_set_revision": review["draft_set_revision"],
            },
            headers=mutation_headers(admin, "s51-discard-missing", revision=etag),
        )
        assert missing.status_code == 422

        # A wrong draft-set revision is rejected before any mutation.
        wrong = admin.post(
            f"/api/v1/physicians/{physician_id}/deactivate",
            json={
                "draft_action": "discard",
                "confirm_discard": True,
                "draft_set_revision": "stale-revision",
            },
            headers=mutation_headers(admin, "s51-discard-wrong", revision=etag),
        )
        assert wrong.status_code == 412

        discarded = admin.post(
            f"/api/v1/physicians/{physician_id}/deactivate",
            json={
                "draft_action": "discard",
                "confirm_discard": True,
                "draft_set_revision": review["draft_set_revision"],
            },
            headers=mutation_headers(admin, "s51-discard-go", revision=etag),
        )
        assert discarded.status_code == 200
        assert discarded.json()["active"] is False

        # The tombstone stays readable with content preserved, not editable.
        tombstone = admin.get(f"/api/v1/encounters/{encounter_id}")
        assert tombstone.status_code == 200
        seen = encounter_body(tombstone.json())
        assert seen["state"] == "discarded"
        assert seen["revision"] == revision_before + 1
        assert seen["draft_data"] == draft_before
        assert seen["author_id"] == author_before

        # The deactivation audit row retains the confirmed disposition.
        audits = _s51_deactivate_audit_rows(physician_id)
        assert any(
            isinstance(row["details"], dict)
            and row["details"].get("draft_action") == "discard"
            for row in audits
        )

        # After reactivation the discarded draft is still terminal.
        reactivated = admin.post(
            f"/api/v1/physicians/{physician_id}/reactivate",
            json={},
            headers=mutation_headers(
                admin, "s51-discard-react", revision=discarded.headers["etag"]
            ),
        )
        assert reactivated.status_code == 200
        login(physician, "sdiscarddoc", "secret", "physician")
        again = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert again.status_code == 200
        assert encounter_body(again.json())["state"] == "discarded"
        repatch = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=mutation_headers(
                physician, revision=str(revision_before + 1)
            ),
        )
        assert repatch.status_code == 409


def test_reactivate_restores_retained_but_never_discarded_or_reattributed():
    _s51_reset_full()
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "sreactdoc", "s51-react-create")
        physician_id = _s51_physician_id(admin, "sreactdoc")
        login(physician, "sreactdoc", "secret", "physician")
        _patient, encounter = create_patient(
            physician, "0853555555", "s51-react-p1"
        )
        encounter_id = encounter["id"]
        saved = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=mutation_headers(physician, revision="1"),
        )
        assert saved.status_code == 200
        author_before = encounter_body(saved.json())["author_id"]

        # Retain cycle: reactivation restores author edits, same attribution.
        review = admin.get(
            f"/api/v1/physicians/{physician_id}/deactivation-review"
        ).json()
        deactivated = admin.post(
            f"/api/v1/physicians/{physician_id}/deactivate",
            json={
                "draft_action": "retain",
                "draft_set_revision": review["draft_set_revision"],
            },
            headers=mutation_headers(
                admin,
                "s51-react-retain",
                revision=_s51_account_etag(admin, physician_id),
            ),
        )
        assert deactivated.status_code == 200
        reactivated = admin.post(
            f"/api/v1/physicians/{physician_id}/reactivate",
            json={},
            headers=mutation_headers(
                admin, "s51-react-back", revision=deactivated.headers["etag"]
            ),
        )
        assert reactivated.status_code == 200
        assert reactivated.json()["active"] is True
        login(physician, "sreactdoc", "secret", "physician")
        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        live = encounter_body(fetched.json())
        assert live["state"] == "draft"
        assert live["author_id"] == author_before
        repatch = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=mutation_headers(physician, revision=str(live["revision"])),
        )
        assert repatch.status_code == 200
        assert encounter_body(repatch.json())["author_id"] == author_before
        retained_revision = encounter_body(repatch.json())["revision"]

        # Discard cycle: reactivation never resurrects nor reattributes.
        fresh = admin.get(
            f"/api/v1/physicians/{physician_id}/deactivation-review"
        ).json()
        _s51_draft_entry_for(fresh["drafts"], encounter_id)
        redacted = admin.post(
            f"/api/v1/physicians/{physician_id}/deactivate",
            json={
                "draft_action": "discard",
                "confirm_discard": True,
                "draft_set_revision": fresh["draft_set_revision"],
            },
            headers=mutation_headers(
                admin,
                "s51-react-discard",
                revision=_s51_account_etag(admin, physician_id),
            ),
        )
        assert redacted.status_code == 200
        restored = admin.post(
            f"/api/v1/physicians/{physician_id}/reactivate",
            json={},
            headers=mutation_headers(
                admin, "s51-react-back-two", revision=redacted.headers["etag"]
            ),
        )
        assert restored.status_code == 200
        login(physician, "sreactdoc", "secret", "physician")
        tombstone = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert tombstone.status_code == 200
        kept = encounter_body(tombstone.json())
        assert kept["state"] == "discarded"
        assert kept["revision"] == retained_revision + 1
        assert kept["author_id"] == author_before
        refused = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=mutation_headers(physician, revision=str(kept["revision"])),
        )
        assert refused.status_code == 409


# ---------------------------------------------------------------------------
# S51 slice 3 (RED): concurrent sign/save, sign/archive, sign/deactivate,
# two baseline-related follow-up signs. FR-22, NFR-04.
# Seams T1 (real concurrent HTTP: ThreadPoolExecutor + one TestClient per
# thread + threading.Barrier start, bounded timeouts) + T8 controlled delay
# where needed (no provider delay during the races: every race starts from
# an already-succeeded run built with the test_signing.py synthetic-bundle /
# signable-run pattern exactly — one-question synthetic bundle, controlled
# localhost provider, synthetic DDI release, real worker drain; SQL is
# setup-only, never a forged success flag).
#
# Slices 1-2 above are unchanged.
#
# Agreed serial contract under test (sign uses SELECT FOR UPDATE +
# advisory lock + If-Match/encounter_revision + plan revision +
# archived/author/state/run-stale/baseline checks; PATCH uses If-Match):
# 1. sign+save on the same revision: exactly one serial outcome — either
#    sign 201 then save 412, or save 200 then sign 412/409; never both 200
#    (no lost update), never an ineligible signature.
# 2. sign vs archive: signed-then-archive OR archived-then-sign-409; never
#    a signature committed after the archive committed (no
#    signed-on-archived-patient). Commit order is read from response
#    completion timestamps (response is returned after commit).
# 3. sign vs deactivate: same serial property; a deactivated author must
#    not gain a newly-signed eligible signature unless sign committed first
#    while the author was still active.
# 4. two follow-up signs on one signed baseline with a concurrently signed
#    newer baseline (B2): at most one follow-up sign succeeds; any sign
#    finishing after an earlier committed sign on the same patient must be
#    409 baseline-changed; never two ineligible signatures.
# ---------------------------------------------------------------------------

import concurrent.futures as _cf
import hashlib as _hashlib
import http.server as _http_server
import socketserver as _socketserver
import threading as _threading
import time as _time
from pathlib import Path as _Path

from x_insight.contracts import content_hash as _r3_content_hash
from x_insight.ddi.terminology import canonical_pair_key as _r3_pair_key

_R3_HISTORY_DIR = (
    _Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "content" / "history"
)
_R3_QUESTION = "s51race_single"
_R3_NET_VERSION = "v1"
_R3_REG_BUNDLE = "synthetic-bundle-hash-s51-race-reg"
_R3_FU_BUNDLE = "synthetic-bundle-hash-s51-race-fu"
_R3_HIST_VERSION = "synthetic-history-v1"
_R3_DDI_VERSION = "synthetic-ddi-s51-race"
_R3_MODEL = "synthetic-model-s51-race"
_R3_API_KEY = "synthetic-provider-key-s51-race-001"
_R3_XML = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>SyntheticCPT</NAME>'
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
    b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)
_R3_NET_HASH = _hashlib.sha256(_R3_XML).hexdigest()
_R3_MED_A = "synthetic-s51race-med-a"
_R3_MED_B = "synthetic-s51race-med-b"
_R3_PLAN_TEXT = "SYNTHETIC-S51RACE-SECONDARY-test-only"


def _r3_reset_full():
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE runs, run_questions, reasoning_jobs, "
                "reasoning_attempts, run_question_artifacts, run_proposals, "
                "model_bundle_pointers, model_bundle_events, "
                "mcp_question_grants, provider_configs, "
                "provider_config_pointer, queue_fairness, "
                "ddi_dataset_releases"
            )
        )


def _r3_insert_bundle(workflow, bundle_hash):
    import json as _json

    pins = {
        "questions": [
            {
                "question_key": _R3_QUESTION,
                "version": _R3_NET_VERSION,
                "network_hash": _R3_NET_HASH,
                "network_xml": _R3_XML.decode("utf-8"),
                "prompt": (
                    f"SYNTH-S51RACE-{_R3_QUESTION} estimate every CPT as "
                    "percentages summing to 100 using only listed patient "
                    "facts. Do not write a plan. Do not choose applicability."
                ),
                "template": {"template_version": "synthetic-v1"},
            }
        ]
    }
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO model_bundle_pointers "
                "(workflow, revision, bundle_hash, pins) "
                "VALUES (:workflow, 1, :hash, CAST(:pins AS jsonb)) "
                "ON CONFLICT (workflow) DO UPDATE SET revision = 1, "
                "bundle_hash = :hash, pins = CAST(:pins AS jsonb)"
            ),
            {"workflow": workflow, "hash": bundle_hash, "pins": _json.dumps(pins)},
        )
        conn.execute(
            text(
                "INSERT INTO model_bundle_events "
                "(workflow, revision, bundle_hash, pins, action) "
                "VALUES (:workflow, 1, :hash, CAST(:pins AS jsonb), "
                "'activate') ON CONFLICT (workflow, revision) DO NOTHING"
            ),
            {"workflow": workflow, "hash": bundle_hash, "pins": _json.dumps(pins)},
        )


def _r3_insert_provider(base_url):
    from x_insight.reasoning.provider_config import encrypt_api_key

    ciphertext = encrypt_api_key(_R3_API_KEY)
    with db.transaction() as conn:
        row = (
            conn.execute(
                text(
                    "INSERT INTO provider_configs "
                    "(revision, base_url, model, key_ciphertext, "
                    " key_present, test_status) "
                    "VALUES (1, :base_url, :model, :ciphertext, TRUE, "
                    " 'untested') RETURNING id"
                ),
                {
                    "base_url": base_url,
                    "model": _R3_MODEL,
                    "ciphertext": ciphertext,
                },
            )
            .mappings()
            .one()
        )
        conn.execute(
            text(
                "INSERT INTO provider_config_pointer "
                "(id, active_config_id, active_revision) "
                "VALUES (1, :id, 1) "
                "ON CONFLICT (id) DO UPDATE SET "
                "active_config_id = EXCLUDED.active_config_id, "
                "active_revision = EXCLUDED.active_revision"
            ),
            {"id": str(row["id"])},
        )


def _r3_insert_ddi():
    import json as _json

    pair_key = _r3_pair_key(_R3_MED_A, _R3_MED_B)
    evidence = [
        {
            "pair_key": pair_key,
            "source_severity": "monitor_closely",
            "management": "SYNTHETIC s51race management - test only",
            "direction": {"subject": _R3_MED_A, "object": _R3_MED_B},
            "source_path": "SYNTHETIC-s51race.txt",
            "span": {"start_line": 1, "end_line": 2},
            "raw_text": "SYNTHETIC s51race evidence for pair coverage - test only",
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
                "version": _R3_DDI_VERSION,
                "dataset_hash": f"synthetic-hash-{_R3_DDI_VERSION}",
                "source_inventory": _json.dumps([]),
                "terminology_provenance": _json.dumps(None),
                "review_record": _json.dumps(
                    {"synthetic_fixture": True, "reviewer": "dr-synthetic"}
                ),
                "corrections": _json.dumps([]),
                "coverage": _json.dumps({"scope": "limited", "exclusions": []}),
                "evidence": _json.dumps(evidence),
            },
        )


def _r3_cpt_payload():
    return {
        "question_key": _R3_QUESTION,
        "network_version": _R3_NET_VERSION,
        "network_hash": _R3_NET_HASH,
        "tables": [
            {
                "node_id": "A",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [80, 20]}],
            },
            {
                "node_id": "B",
                "parent_ids": ["A"],
                "states": ["no", "yes"],
                "rows": [
                    {"parent_states": ["no"], "percentages": [90, 10]},
                    {"parent_states": ["yes"], "percentages": [30, 70]},
                ],
            },
        ],
    }


def _r3_start_provider(bodies):
    import json as _json

    payload = _r3_cpt_payload()

    class _Handler(_http_server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
            out = _json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args):
            pass

    server = _socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = _threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    return server, thread


def _r3_drain(worker_prefix, max_steps=10):
    from x_insight.reasoning.worker import run_once as _real_run_once

    outcomes = []
    for step in range(max_steps):
        outcome = _real_run_once(
            database_url=None,
            provider_adapter=None,
            worker_id=f"{worker_prefix}-{step}",
        )
        outcomes.append(outcome)
        if not outcome.get("claimed"):
            break
    return outcomes


def _r3_clinical_draft(medications, ddi_version, fingerprint):
    return {
        "diagnosis": {"answers": {"synthetic_item": "synthetic_value"}},
        "history": {
            "definition_version": _R3_HIST_VERSION,
            "values": {
                "synthetic_flag_true": {"status": "known", "value": True},
            },
        },
        "effects": {
            "definition_version": _R3_HIST_VERSION,
            "values": {
                "tardive_dyskinesia": {
                    "status": "present",
                    "severity": "synthetic_tardive_severity_one",
                },
                "akathisia": {"status": "absent", "severity": None},
                "parkinsonism": {"status": "absent", "severity": None},
                "acute_dystonia": {"status": "not_assessed", "severity": None},
            },
        },
        "medications": medications,
        "ddi_report": {
            "dataset_version": _R3_DDI_VERSION,
            "medication_fingerprint": fingerprint,
        },
    }


def _r3_followup_draft(medications, ddi_version, fingerprint, recon_status, baseline_id):
    draft = _r3_clinical_draft(medications, ddi_version, fingerprint)
    draft["history_reconciliation"] = {
        "status": recon_status,
        "baseline_encounter_id": baseline_id,
    }
    return draft


def _r3_meds_fingerprint(meds):
    return _r3_content_hash(
        {"resolved": sorted(meds), "unresolved": []}
    )


def _r3_revision(client, encounter_id):
    fetched = client.get(f"/api/v1/encounters/{encounter_id}")
    assert fetched.status_code == 200
    return int(encounter_body(fetched.json())["revision"])


def _r3_build_succeeded(client, encounter_id, revision, prefix):
    started = client.post(
        f"/api/v1/encounters/{encounter_id}/runs",
        json={"encounter_revision": revision},
        headers=mutation_headers(client, key=f"{prefix}-run", revision=revision),
    )
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    _r3_drain(prefix, max_steps=10)
    body = client.get(f"/api/v1/runs/{run_id}").json()
    assert body["run"]["status"] == "succeeded", body["run"]
    assert body["proposal"]["status"] == "succeeded"
    assert body["stale"] is False
    return run_id


def _r3_save_plan(client, encounter_id, key):
    saved = client.patch(
        f"/api/v1/encounters/{encounter_id}/secondary-plan",
        json={"text": _R3_PLAN_TEXT},
        headers=mutation_headers(client, key=key, revision="0"),
    )
    assert saved.status_code == 200
    payload = saved.json()
    plan = payload.get("secondary_plan", payload)
    return int(plan["revision"])


def _r3_seed_registration(client, patient_pid, key_prefix):
    _patient, encounter = create_patient(client, patient_pid, f"{key_prefix}-p")
    encounter_id = encounter["id"]
    meds = [_R3_MED_A, _R3_MED_B]
    fingerprint = _r3_meds_fingerprint(meds)
    saved = client.patch(
        f"/api/v1/encounters/{encounter_id}",
        json={
            "draft_data": _r3_clinical_draft(
                [{"catalog_drug_id": m} for m in meds],
                _R3_DDI_VERSION,
                fingerprint,
            )
        },
        headers=mutation_headers(client, revision=encounter["revision"]),
    )
    assert saved.status_code == 200
    revision = _r3_revision(client, encounter_id)
    run_id = _r3_build_succeeded(client, encounter_id, revision, key_prefix)
    plan_revision = _r3_save_plan(client, encounter_id, f"{key_prefix}-plan-1")
    assert plan_revision == 1
    return encounter_id, run_id


def _r3_cookies(client):
    return (
        client.cookies.get("xinsight_session"),
        client.cookies.get("xinsight_csrf"),
    )


def _r3_run_barrier(workers, timeout=90):
    """Run worker thunks concurrently with a barrier start (T1).

    Each thunk receives (client, barrier) where client is a per-thread
    TestClient; it must barrier.wait(timeout=30) then fire exactly one
    request and return {"status", "done", ...}. Responses complete after
    commit, so completion timestamps order the commits.
    """
    barrier = _threading.Barrier(len(workers))

    def _wrap(fn):
        try:
            with TestClient(app) as client:
                return fn(client, barrier)
        except Exception as exc:  # noqa: BLE001 - surface thread errors
            return {
                "status": "error",
                "detail": f"{type(exc).__name__}: {exc}",
                "done": _time.monotonic(),
            }

    with _cf.ThreadPoolExecutor(max_workers=len(workers)) as pool:
        futures = [pool.submit(_wrap, fn) for fn in workers]
        return [fut.result(timeout=timeout) for fut in futures]


def _r3_mk_headers(csrf, key=None, revision=None):
    headers = {"X-CSRF-Token": csrf}
    if key is not None:
        headers["Idempotency-Key"] = key
    if revision is not None:
        headers["If-Match"] = str(revision)
    return headers


def _r3_sign_body(encounter_revision, run_id, plan_revision):
    return {
        "encounter_revision": encounter_revision,
        "run_id": run_id,
        "secondary_plan_revision": plan_revision,
        "review_acknowledgments": [],
        "baseline_acknowledgment": True,
    }


def _r3_snapshot_status(client, encounter_id):
    return client.get(f"/api/v1/encounters/{encounter_id}/signed-snapshot").status_code


def _r3_encounter_state(client, encounter_id):
    fetched = client.get(f"/api/v1/encounters/{encounter_id}")
    assert fetched.status_code == 200
    body = encounter_body(fetched.json())
    return body["state"], int(body["revision"])


def test_concurrent_sign_and_save_serializes_no_lost_update(monkeypatch):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(_R3_HISTORY_DIR))
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    _r3_reset_full()
    _r3_insert_ddi()
    _r3_insert_bundle("registration", _R3_REG_BUNDLE)
    bodies = []
    server, thread = _r3_start_provider(bodies)
    try:
        host, port = server.server_address
        _r3_insert_provider(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as author:
            login(admin)
            create_physician(admin, "r3savesign", "r3-ss-create")
            login(author, "r3savesign", "secret", "physician")
            encounter_id, run_id = _r3_seed_registration(
                author, "0861000001", "r3-ss"
            )
            revision = _r3_revision(author, encounter_id)
            sess, csrf = _r3_cookies(author)
            assert sess and csrf

            meds = [{"catalog_drug_id": _R3_MED_A}]
            fingerprint = _r3_meds_fingerprint([_R3_MED_A, _R3_MED_B])
            save_draft = _r3_clinical_draft(meds, _R3_DDI_VERSION, fingerprint)

            def do_save(client, barrier):
                client.cookies.set("xinsight_session", sess)
                client.cookies.set("xinsight_csrf", csrf)
                barrier.wait(timeout=30)
                response = client.patch(
                    f"/api/v1/encounters/{encounter_id}",
                    json={"draft_data": save_draft},
                    headers=_r3_mk_headers(csrf, revision=revision),
                )
                return {"status": response.status_code, "done": _time.monotonic()}

            def do_sign(client, barrier):
                client.cookies.set("xinsight_session", sess)
                client.cookies.set("xinsight_csrf", csrf)
                barrier.wait(timeout=30)
                response = client.post(
                    f"/api/v1/encounters/{encounter_id}/sign",
                    json=_r3_sign_body(revision, run_id, 1),
                    headers=_r3_mk_headers(csrf, key="r3-ss-sign", revision=revision),
                )
                return {"status": response.status_code, "done": _time.monotonic()}

            (save_out, sign_out) = _r3_run_barrier([do_save, do_sign])
            assert save_out["status"] != "error", save_out
            assert sign_out["status"] != "error", sign_out

            # Exactly one serial outcome; never both 200 (no lost update).
            both_ok = save_out["status"] == 200 and sign_out["status"] in (200, 201)
            assert not both_ok, (
                f"lost update: save={save_out['status']} sign={sign_out['status']}"
            )
            if sign_out["status"] in (200, 201):
                assert save_out["status"] == 412, (save_out, sign_out)
                state, _rev = _r3_encounter_state(author, encounter_id)
                assert state == "signed"
                assert _r3_snapshot_status(author, encounter_id) == 200
            else:
                assert save_out["status"] == 200, (save_out, sign_out)
                assert sign_out["status"] in (409, 412), sign_out
                state, now = _r3_encounter_state(author, encounter_id)
                assert state == "draft"
                assert now == revision + 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_concurrent_sign_vs_archive_never_signs_archived(monkeypatch):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(_R3_HISTORY_DIR))
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    _r3_reset_full()
    _r3_insert_ddi()
    _r3_insert_bundle("registration", _R3_REG_BUNDLE)
    bodies = []
    server, thread = _r3_start_provider(bodies)
    try:
        host, port = server.server_address
        _r3_insert_provider(f"http://{host}:{port}")
        # Fresh fixtures per attempt amplify a true race window; a correct
        # serial fence passes every attempt, a start-only check fails one.
        for attempt in range(3):
            with TestClient(app) as admin, TestClient(app) as author:
                username = f"r3arch{attempt}"
                login(admin)
                create_physician(admin, username, f"r3-arch-create-{attempt}")
                login(author, username, "secret", "physician")
                patient, encounter = create_patient(
                    author, f"086200000{attempt}", f"r3-arch-p-{attempt}"
                )
                encounter_id = encounter["id"]
                meds = [_R3_MED_A, _R3_MED_B]
                fingerprint = _r3_meds_fingerprint(meds)
                seeded = author.patch(
                    f"/api/v1/encounters/{encounter_id}",
                    json={
                        "draft_data": _r3_clinical_draft(
                            [{"catalog_drug_id": m} for m in meds],
                            _R3_DDI_VERSION,
                            fingerprint,
                        )
                    },
                    headers=mutation_headers(author, revision=encounter["revision"]),
                )
                assert seeded.status_code == 200
                revision = _r3_revision(author, encounter_id)
                run_id = _r3_build_succeeded(
                    author, encounter_id, revision, f"r3-arch-{attempt}"
                )
                assert _r3_save_plan(author, encounter_id, f"r3-arch-plan-{attempt}") == 1
                patient_revision = patient["revision"]
                author_sess, author_csrf = _r3_cookies(author)
                admin_sess, admin_csrf = _r3_cookies(admin)

                def do_archive(client, barrier, _a=(admin_sess, admin_csrf)):
                    client.cookies.set("xinsight_session", _a[0])
                    client.cookies.set("xinsight_csrf", _a[1])
                    barrier.wait(timeout=30)
                    response = client.post(
                        f"/api/v1/patients/{patient['id']}/archive",
                        headers=_r3_mk_headers(
                            _a[1],
                            key=f"r3-arch-key-{attempt}",
                            revision=patient_revision,
                        ),
                    )
                    return {
                        "status": response.status_code,
                        "done": _time.monotonic(),
                    }

                def do_sign(client, barrier, _s=(author_sess, author_csrf)):
                    client.cookies.set("xinsight_session", _s[0])
                    client.cookies.set("xinsight_csrf", _s[1])
                    barrier.wait(timeout=30)
                    response = client.post(
                        f"/api/v1/encounters/{encounter_id}/sign",
                        json=_r3_sign_body(revision, run_id, 1),
                        headers=_r3_mk_headers(
                            _s[1], key=f"r3-archsign-{attempt}", revision=revision
                        ),
                    )
                    return {
                        "status": response.status_code,
                        "done": _time.monotonic(),
                    }

                (archive_out, sign_out) = _r3_run_barrier([do_archive, do_sign])
                assert archive_out["status"] != "error", archive_out
                assert sign_out["status"] != "error", sign_out

                # RED: archive committed first yet sign still succeeded, i.e.
                # a signature on an archived patient (signed-on-archived).
                if (
                    archive_out["status"] == 200
                    and sign_out["status"] in (200, 201)
                    and archive_out["done"] <= sign_out["done"]
                ):
                    raise AssertionError(
                        "ineligible signature: archive committed first "
                        f"(attempt {attempt}) yet sign={sign_out['status']}"
                    )
                if sign_out["status"] in (200, 201):
                    state, _rev = _r3_encounter_state(author, encounter_id)
                    assert state == "signed"
                    assert _r3_snapshot_status(author, encounter_id) == 200
                else:
                    assert sign_out["status"] in (401, 403, 409, 412), sign_out
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_concurrent_sign_vs_deactivate_no_post_deactivation_signature(monkeypatch):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(_R3_HISTORY_DIR))
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    _r3_reset_full()
    _r3_insert_ddi()
    _r3_insert_bundle("registration", _R3_REG_BUNDLE)
    bodies = []
    server, thread = _r3_start_provider(bodies)
    try:
        host, port = server.server_address
        _r3_insert_provider(f"http://{host}:{port}")
        for attempt in range(3):
            with TestClient(app) as admin, TestClient(app) as author:
                username = f"r3deact{attempt}"
                login(admin)
                create_physician(admin, username, f"r3-deact-create-{attempt}")
                physician_id = _s51_physician_id(admin, username)
                login(author, username, "secret", "physician")
                _patient, encounter = create_patient(
                    author, f"086300000{attempt}", f"r3-deact-p-{attempt}"
                )
                encounter_id = encounter["id"]
                meds = [_R3_MED_A, _R3_MED_B]
                fingerprint = _r3_meds_fingerprint(meds)
                seeded = author.patch(
                    f"/api/v1/encounters/{encounter_id}",
                    json={
                        "draft_data": _r3_clinical_draft(
                            [{"catalog_drug_id": m} for m in meds],
                            _R3_DDI_VERSION,
                            fingerprint,
                        )
                    },
                    headers=mutation_headers(author, revision=encounter["revision"]),
                )
                assert seeded.status_code == 200
                revision = _r3_revision(author, encounter_id)
                run_id = _r3_build_succeeded(
                    author, encounter_id, revision, f"r3-deact-{attempt}"
                )
                assert (
                    _r3_save_plan(author, encounter_id, f"r3-deact-plan-{attempt}") == 1
                )
                review = admin.get(
                    f"/api/v1/physicians/{physician_id}/deactivation-review"
                ).json()
                draft_set_revision = review["draft_set_revision"]
                etag = _s51_account_etag(admin, physician_id)
                author_sess, author_csrf = _r3_cookies(author)
                admin_sess, admin_csrf = _r3_cookies(admin)

                def do_deactivate(client, barrier, _a=(admin_sess, admin_csrf)):
                    client.cookies.set("xinsight_session", _a[0])
                    client.cookies.set("xinsight_csrf", _a[1])
                    barrier.wait(timeout=30)
                    response = client.post(
                        f"/api/v1/physicians/{physician_id}/deactivate",
                        json={
                            "draft_action": "retain",
                            "draft_set_revision": draft_set_revision,
                        },
                        headers=_r3_mk_headers(
                            _a[1], key=f"r3-deact-key-{attempt}", revision=etag
                        ),
                    )
                    return {
                        "status": response.status_code,
                        "done": _time.monotonic(),
                    }

                def do_sign(client, barrier, _s=(author_sess, author_csrf)):
                    client.cookies.set("xinsight_session", _s[0])
                    client.cookies.set("xinsight_csrf", _s[1])
                    barrier.wait(timeout=30)
                    response = client.post(
                        f"/api/v1/encounters/{encounter_id}/sign",
                        json=_r3_sign_body(revision, run_id, 1),
                        headers=_r3_mk_headers(
                            _s[1], key=f"r3-deactsign-{attempt}", revision=revision
                        ),
                    )
                    return {
                        "status": response.status_code,
                        "done": _time.monotonic(),
                    }

                (deact_out, sign_out) = _r3_run_barrier([do_deactivate, do_sign])
                assert deact_out["status"] != "error", deact_out
                assert sign_out["status"] != "error", sign_out

                # RED: deactivation committed first (author inactive, sessions
                # revoked) yet sign still succeeded — the implementation
                # checks author-active only at start, not at commit time.
                if (
                    deact_out["status"] == 200
                    and sign_out["status"] in (200, 201)
                    and deact_out["done"] <= sign_out["done"]
                ):
                    raise AssertionError(
                        "ineligible signature: deactivation committed first "
                        f"(attempt {attempt}) yet sign={sign_out['status']}"
                    )
                if sign_out["status"] in (200, 201):
                    assert _r3_snapshot_status(admin, encounter_id) == 200
                else:
                    assert sign_out["status"] in (401, 403, 409, 412), sign_out
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_concurrent_followup_signs_with_newer_baseline_at_most_one(monkeypatch):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(_R3_HISTORY_DIR))
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    _r3_reset_full()
    _r3_insert_ddi()
    _r3_insert_bundle("registration", _R3_REG_BUNDLE)
    _r3_insert_bundle("followup", _R3_FU_BUNDLE)
    bodies = []
    server, thread = _r3_start_provider(bodies)
    try:
        host, port = server.server_address
        _r3_insert_provider(f"http://{host}:{port}")
        for attempt in range(3):
            with (
                TestClient(app) as admin,
                TestClient(app) as phys_a,
                TestClient(app) as phys_b,
            ):
                login(admin)
                user_a = f"r3fua{attempt}"
                user_b = f"r3fub{attempt}"
                create_physician(admin, user_a, f"r3-fu-create-a-{attempt}")
                create_physician(admin, user_b, f"r3-fu-create-b-{attempt}")
                login(phys_a, user_a, "secret", "physician")
                login(phys_b, user_b, "secret", "physician")
                patient, baseline = create_patient(
                    phys_a, f"086400000{attempt}", f"r3-fu-p-{attempt}"
                )
                baseline_id = baseline["id"]
                meds = [{"catalog_drug_id": m} for m in [_R3_MED_A, _R3_MED_B]]
                fingerprint = _r3_meds_fingerprint([_R3_MED_A, _R3_MED_B])
                seeded = phys_a.patch(
                    f"/api/v1/encounters/{baseline_id}",
                    json={
                        "draft_data": _r3_clinical_draft(
                            meds, _R3_DDI_VERSION, fingerprint
                        )
                    },
                    headers=mutation_headers(phys_a, revision=baseline["revision"]),
                )
                assert seeded.status_code == 200
                base_rev = _r3_revision(phys_a, baseline_id)
                base_run = _r3_build_succeeded(
                    phys_a, baseline_id, base_rev, f"r3-fu-base-{attempt}"
                )
                assert (
                    _r3_save_plan(phys_a, baseline_id, f"r3-fu-base-plan-{attempt}")
                    == 1
                )
                base_rev = _r3_revision(phys_a, baseline_id)
                signed_base = phys_a.post(
                    f"/api/v1/encounters/{baseline_id}/sign",
                    json=_r3_sign_body(base_rev, base_run, 1),
                    headers=mutation_headers(
                        phys_a, key=f"r3-fu-base-sign-{attempt}", revision=base_rev
                    ),
                )
                assert signed_base.status_code in (200, 201)

                followups = []
                for tag, owner in (("f1", phys_a), ("f2", phys_b), ("b2", phys_a)):
                    created = owner.post(
                        f"/api/v1/patients/{patient['id']}/encounters",
                        json={"baseline_encounter_id": baseline_id},
                        headers=mutation_headers(owner, f"r3-fu-mk-{tag}-{attempt}"),
                    )
                    assert created.status_code == 201
                    followup = encounter_body(created.json())
                    followup_id = followup["id"]
                    patched = owner.patch(
                        f"/api/v1/encounters/{followup_id}",
                        json={
                            "draft_data": _r3_followup_draft(
                                meds, _R3_DDI_VERSION, fingerprint, "confirmed", baseline_id
                            )
                        },
                        headers=mutation_headers(owner, revision=1),
                    )
                    assert patched.status_code == 200
                    followup_rev = _r3_revision(owner, followup_id)
                    followup_run = _r3_build_succeeded(
                        owner, followup_id, followup_rev, f"r3-fu-{tag}-{attempt}"
                    )
                    assert (
                        _r3_save_plan(
                            owner, followup_id, f"r3-fu-{tag}-plan-{attempt}"
                        )
                        == 1
                    )
                    followups.append((tag, followup_id, followup_run, followup_rev))

                sess_a, csrf_a = _r3_cookies(phys_a)
                sess_b, csrf_b = _r3_cookies(phys_b)

                def _signer(tag, sess, csrf, followup_id, followup_run, rev):
                    def _fire(client, barrier):
                        client.cookies.set("xinsight_session", sess)
                        client.cookies.set("xinsight_csrf", csrf)
                        barrier.wait(timeout=30)
                        response = client.post(
                            f"/api/v1/encounters/{followup_id}/sign",
                            json=_r3_sign_body(rev, followup_run, 1),
                            headers=_r3_mk_headers(
                                csrf,
                                key=f"r3-fu-sign-{tag}-{attempt}",
                                revision=rev,
                            ),
                        )
                        return {
                            "tag": tag,
                            "status": response.status_code,
                            "done": _time.monotonic(),
                        }

                    return _fire

                tag_a, fid_a, frun_a, rev_a = followups[0]
                tag_b, fid_b, frun_b, rev_b = followups[1]
                tag_c, fid_c, frun_c, rev_c = followups[2]
                outcomes = _r3_run_barrier(
                    [
                        _signer(tag_a, sess_a, csrf_a, fid_a, frun_a, rev_a),
                        _signer(tag_b, sess_b, csrf_b, fid_b, frun_b, rev_b),
                        # B2: a concurrently signed newer baseline on the
                        # same patient; whichever follow-up finishes after
                        # the first committed sign must reconcile afresh.
                        _signer(tag_c, sess_a, csrf_a, fid_c, frun_c, rev_c),
                    ]
                )
                for outcome in outcomes:
                    assert outcome.get("status") != "error", outcome
                successes = [
                    o
                    for o in outcomes
                    if o["status"] in (200, 201)
                ]
                # RED: two follow-ups each committed without seeing the
                # other's (or B2's) newer signed baseline — the winner's
                # commit should fence the losers to 409 baseline-changed.
                assert len(successes) <= 1, (
                    "two ineligible signatures without fresh reconciliation "
                    f"(attempt {attempt}): {outcomes}"
                )
                for outcome in outcomes:
                    if outcome["status"] in (200, 201):
                        assert _r3_snapshot_status(admin, {
                            tag_a: fid_a, tag_b: fid_b, tag_c: fid_c,
                        }[outcome["tag"]]) == 200
                    else:
                        assert outcome["status"] in (401, 403, 409, 412), outcome
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S51 slice 4 (RED, T1 only): staleness + reconciled concurrent follow-ups.
# FR-16/22, NFR-04. Deterministic sequential HTTP (no threads — slice 3
# owns concurrency). Reuses the _r3 signable-run helpers above (one-question
# synthetic bundle, controlled localhost provider, synthetic DDI release,
# real worker drain; SQL is setup-only, never a forged success flag).
#
# Agreed contract under test (runs._compute_stale + signing fingerprint
# rules; encounters PATCH phone-only vs draft_data analytical facts;
# history_reconciliation pending/confirmed; sign requires current run
# fingerprint + latest encounter revision + confirmed reconciliation):
# 1. Analytical draft_data edit bumps the encounter revision, flips an old
#    succeeded run to stale True, and sign with the old run_id is 409; a
#    fresh run from the current revision is required.
# 2. Note-only change never enters the fingerprint: the old run stays
#    fresh and signable, but sign still requires the latest
#    encounter_revision (stale body revision is 412).
# 3. Two physicians hold separate follow_up drafts on one signed baseline
#    with different history/effects edits; both reconcile to confirmed and
#    sign sequentially -> both signed, author_ids distinct, history
#    provenance distinct, no merge/overwrite.
# ---------------------------------------------------------------------------


def _s4_followup_variant(flag_id, flag_value, tardive_severity, meds, baseline_id):
    draft = _r3_clinical_draft(meds, _R3_DDI_VERSION, _r3_meds_fingerprint(
        [m.get("catalog_drug_id", "") for m in meds if "catalog_drug_id" in m]
        or [_R3_MED_A]
    ))
    draft["history"] = {
        "definition_version": _R3_HIST_VERSION,
        "values": {flag_id: {"status": "known", "value": flag_value}},
    }
    draft["effects"] = {
        "definition_version": _R3_HIST_VERSION,
        "values": {
            "tardive_dyskinesia": {
                "status": "present",
                "severity": tardive_severity,
            },
            "akathisia": {"status": "absent", "severity": None},
            "parkinsonism": {"status": "absent", "severity": None},
            "acute_dystonia": {"status": "not_assessed", "severity": None},
        },
    }
    draft["history_reconciliation"] = {
        "status": "confirmed",
        "baseline_encounter_id": baseline_id,
    }
    return draft


def test_s51_slice4_analytical_edit_stales_old_run_and_sign_needs_new_run(
    monkeypatch,
):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(_R3_HISTORY_DIR))
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    _r3_reset_full()
    _r3_insert_ddi()
    _r3_insert_bundle("registration", _R3_REG_BUNDLE)
    bodies = []
    server, thread = _r3_start_provider(bodies)
    try:
        host, port = server.server_address
        _r3_insert_provider(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as author:
            login(admin)
            create_physician(admin, "r3s4stale", "r3-s4-stale-create")
            login(author, "r3s4stale", "secret", "physician")
            encounter_id, run_id = _r3_seed_registration(
                author, "0865000001", "r3-s4a"
            )
            revision = _r3_revision(author, encounter_id)
            assert author.get(f"/api/v1/runs/{run_id}").json()["stale"] is False

            edited = _r3_clinical_draft(
                [{"catalog_drug_id": _R3_MED_A}],
                _R3_DDI_VERSION,
                _r3_meds_fingerprint([_R3_MED_A, _R3_MED_B]),
            )
            edited["history"] = {
                "definition_version": _R3_HIST_VERSION,
                "values": {
                    "synthetic_flag_false": {"status": "known", "value": False},
                },
            }
            patched = author.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": edited},
                headers=mutation_headers(author, revision=revision),
            )
            assert patched.status_code == 200
            fresh_rev = _r3_revision(author, encounter_id)
            assert fresh_rev == revision + 1

            stale_body = author.get(f"/api/v1/runs/{run_id}").json()
            assert stale_body["stale"] is True

            denied = author.post(
                f"/api/v1/encounters/{encounter_id}/sign",
                json=_r3_sign_body(fresh_rev, run_id, 1),
                headers=mutation_headers(
                    author, key="r3-s4a-sign-old", revision=fresh_rev
                ),
            )
            assert denied.status_code == 409

            new_run = _r3_build_succeeded(
                author, encounter_id, fresh_rev, "r3-s4a-new"
            )
            assert new_run != run_id
            assert author.get(f"/api/v1/runs/{new_run}").json()["stale"] is False
            ok = author.post(
                f"/api/v1/encounters/{encounter_id}/sign",
                json=_r3_sign_body(fresh_rev, new_run, 1),
                headers=mutation_headers(
                    author, key="r3-s4a-sign-new", revision=fresh_rev
                ),
            )
            assert ok.status_code in (200, 201)
            assert encounter_body(ok.json())["state"] == "signed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_s51_slice4_note_only_keeps_run_fresh_but_sign_needs_current_revision(
    monkeypatch,
):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(_R3_HISTORY_DIR))
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    _r3_reset_full()
    _r3_insert_ddi()
    _r3_insert_bundle("registration", _R3_REG_BUNDLE)
    bodies = []
    server, thread = _r3_start_provider(bodies)
    try:
        host, port = server.server_address
        _r3_insert_provider(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as author:
            login(admin)
            create_physician(admin, "r3s4note", "r3-s4-note-create")
            login(author, "r3s4note", "secret", "physician")
            encounter_id, run_id = _r3_seed_registration(
                author, "0865000002", "r3-s4n"
            )
            revision = _r3_revision(author, encounter_id)

            noted = author.post(
                f"/api/v1/encounters/{encounter_id}/notes",
                json={
                    "page": "history",
                    "text": "SYNTHETIC-S51-S4-NOTE-test-only",
                },
                headers=mutation_headers(author, key="r3-s4n-note-1"),
            )
            assert noted.status_code == 201
            assert _r3_revision(author, encounter_id) == revision
            assert author.get(f"/api/v1/runs/{run_id}").json()["stale"] is False

            stale_rev = author.post(
                f"/api/v1/encounters/{encounter_id}/sign",
                json=_r3_sign_body(revision - 1, run_id, 1),
                headers=mutation_headers(
                    author, key="r3-s4n-sign-stale", revision=revision - 1
                ),
            )
            assert stale_rev.status_code == 412

            ok = author.post(
                f"/api/v1/encounters/{encounter_id}/sign",
                json=_r3_sign_body(revision, run_id, 1),
                headers=mutation_headers(
                    author, key="r3-s4n-sign-ok", revision=revision
                ),
            )
            assert ok.status_code in (200, 201)
            assert encounter_body(ok.json())["state"] == "signed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_s51_slice4_reconciled_followups_keep_distinct_authors_and_history(
    monkeypatch,
):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(_R3_HISTORY_DIR))
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    _r3_reset_full()
    _r3_insert_ddi()
    _r3_insert_bundle("registration", _R3_REG_BUNDLE)
    _r3_insert_bundle("followup", _R3_FU_BUNDLE)
    bodies = []
    server, thread = _r3_start_provider(bodies)
    try:
        host, port = server.server_address
        _r3_insert_provider(f"http://{host}:{port}")
        with (
            TestClient(app) as admin,
            TestClient(app) as phys_a,
            TestClient(app) as phys_b,
        ):
            login(admin)
            create_physician(admin, "r3s4fua", "r3-s4-fu-create-a")
            create_physician(admin, "r3s4fub", "r3-s4-fu-create-b")
            me_a = login(phys_a, "r3s4fua", "secret", "physician")
            me_b = login(phys_b, "r3s4fub", "secret", "physician")

            patient, baseline = create_patient(phys_a, "0865000003", "r3-s4f-p")
            baseline_id = baseline["id"]
            meds = [{"catalog_drug_id": m} for m in [_R3_MED_A, _R3_MED_B]]
            fingerprint = _r3_meds_fingerprint([_R3_MED_A, _R3_MED_B])
            seeded = phys_a.patch(
                f"/api/v1/encounters/{baseline_id}",
                json={
                    "draft_data": _r3_clinical_draft(
                        meds, _R3_DDI_VERSION, fingerprint
                    )
                },
                headers=mutation_headers(phys_a, revision=baseline["revision"]),
            )
            assert seeded.status_code == 200
            base_rev = _r3_revision(phys_a, baseline_id)
            base_run = _r3_build_succeeded(
                phys_a, baseline_id, base_rev, "r3-s4f-base"
            )
            assert _r3_save_plan(phys_a, baseline_id, "r3-s4f-base-plan") == 1
            base_rev = _r3_revision(phys_a, baseline_id)
            signed_base = phys_a.post(
                f"/api/v1/encounters/{baseline_id}/sign",
                json=_r3_sign_body(base_rev, base_run, 1),
                headers=mutation_headers(
                    phys_a, key="r3-s4f-base-sign", revision=base_rev
                ),
            )
            assert signed_base.status_code in (200, 201)

            created_a = phys_a.post(
                f"/api/v1/patients/{patient['id']}/encounters",
                json={"baseline_encounter_id": baseline_id},
                headers=mutation_headers(phys_a, "r3-s4f-mk-a"),
            )
            assert created_a.status_code == 201
            created_b = phys_b.post(
                f"/api/v1/patients/{patient['id']}/encounters",
                json={"baseline_encounter_id": baseline_id},
                headers=mutation_headers(phys_b, "r3-s4f-mk-b"),
            )
            assert created_b.status_code == 201
            fid_a = encounter_body(created_a.json())["id"]
            fid_b = encounter_body(created_b.json())["id"]
            assert fid_a != fid_b

            draft_a = _s4_followup_variant(
                "synthetic_flag_true",
                True,
                "synthetic_tardive_severity_one",
                meds,
                baseline_id,
            )
            draft_b = _s4_followup_variant(
                "synthetic_flag_false",
                False,
                "synthetic_tardive_severity_two",
                [{"catalog_drug_id": _R3_MED_A}],
                baseline_id,
            )
            patched_a = phys_a.patch(
                f"/api/v1/encounters/{fid_a}",
                json={"draft_data": draft_a},
                headers=mutation_headers(phys_a, revision=1),
            )
            assert patched_a.status_code == 200
            patched_b = phys_b.patch(
                f"/api/v1/encounters/{fid_b}",
                json={"draft_data": draft_b},
                headers=mutation_headers(phys_b, revision=1),
            )
            assert patched_b.status_code == 200

            rev_a = _r3_revision(phys_a, fid_a)
            rev_b = _r3_revision(phys_b, fid_b)
            run_a = _r3_build_succeeded(phys_a, fid_a, rev_a, "r3-s4f-a")
            run_b = _r3_build_succeeded(phys_b, fid_b, rev_b, "r3-s4f-b")
            assert _r3_save_plan(phys_a, fid_a, "r3-s4f-a-plan") == 1
            assert _r3_save_plan(phys_b, fid_b, "r3-s4f-b-plan") == 1

            sign_a = phys_a.post(
                f"/api/v1/encounters/{fid_a}/sign",
                json=_r3_sign_body(rev_a, run_a, 1),
                headers=mutation_headers(
                    phys_a, key="r3-s4f-sign-a", revision=rev_a
                ),
            )
            assert sign_a.status_code in (200, 201)

            # Owner decision (A): plan 2.3 requires explicit fresh
            # review/reconcile after sibling signs. F2 re-confirms with a
            # fresh confirmed history_reconciliation before its own sign.
            rev_b_now = _r3_revision(phys_b, fid_b)
            fresh_b = _s4_followup_variant(
                "synthetic_flag_false",
                False,
                "synthetic_tardive_severity_two",
                [{"catalog_drug_id": _R3_MED_A}],
                baseline_id,
            )
            repatch_b = phys_b.patch(
                f"/api/v1/encounters/{fid_b}",
                json={"draft_data": fresh_b},
                headers=mutation_headers(phys_b, revision=rev_b_now),
            )
            assert repatch_b.status_code == 200
            rev_b_fresh = _r3_revision(phys_b, fid_b)
            observed_b = phys_b.get(f"/api/v1/encounters/{fid_b}")
            assert observed_b.status_code == 200
            assert encounter_body(observed_b.json())["draft_data"][
                "history_reconciliation"
            ] == {"status": "confirmed", "baseline_encounter_id": baseline_id}
            run_b_fresh = run_b
            plan_rev_b = 1
            plan_read = phys_b.get(f"/api/v1/encounters/{fid_b}/secondary-plan")
            assert plan_read.status_code == 200
            plan_payload = plan_read.json()
            plan_current = plan_payload.get("current") or plan_payload.get(
                "secondary_plan"
            )
            plan_rev_b = int(plan_current["revision"])
            if phys_b.get(f"/api/v1/runs/{run_b}").json()["stale"] is True:
                run_b_fresh = _r3_build_succeeded(
                    phys_b, fid_b, rev_b_fresh, "r3-s4f-b-fresh"
                )
                saved_plan = phys_b.patch(
                    f"/api/v1/encounters/{fid_b}/secondary-plan",
                    json={"text": _R3_PLAN_TEXT},
                    headers=mutation_headers(
                        phys_b,
                        key="r3-s4f-b-plan-fresh",
                        revision=str(plan_rev_b),
                    ),
                )
                assert saved_plan.status_code == 200
                plan_saved = saved_plan.json()
                plan_cur = plan_saved.get("secondary_plan", plan_saved)
                plan_rev_b = int(plan_cur["revision"])
            sign_b = phys_b.post(
                f"/api/v1/encounters/{fid_b}/sign",
                json=_r3_sign_body(rev_b_fresh, run_b_fresh, plan_rev_b),
                headers=mutation_headers(
                    phys_b, key="r3-s4f-sign-b", revision=rev_b_fresh
                ),
            )
            assert sign_b.status_code in (200, 201)

            got_a = encounter_body(
                phys_a.get(f"/api/v1/encounters/{fid_a}").json()
            )
            got_b = encounter_body(
                phys_b.get(f"/api/v1/encounters/{fid_b}").json()
            )
            assert got_a["state"] == "signed"
            assert got_b["state"] == "signed"
            assert got_a["author_id"] == me_a["user"]["id"]
            assert got_b["author_id"] == me_b["user"]["id"]
            assert got_a["author_id"] != got_b["author_id"]
            assert got_a["draft_data"]["history"]["values"] == {
                "synthetic_flag_true": {"status": "known", "value": True}
            }
            assert got_b["draft_data"]["history"]["values"] == {
                "synthetic_flag_false": {"status": "known", "value": False}
            }
            assert got_a["draft_data"]["medications"] != got_b["draft_data"][
                "medications"
            ]
            assert (
                got_a["draft_data"]["history"]["provenance"]["actor_id"]
                == me_a["user"]["id"]
            )
            assert (
                got_b["draft_data"]["history"]["provenance"]["actor_id"]
                == me_b["user"]["id"]
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S07 pending / S51 slice-4b (RED, T1 only): discard cancels queued work.
# FR-16/22, NFR-04. Deterministic sequential HTTP (no threads). Reuses the
# _r3 run-start helpers above (synthetic registration bundle; no provider,
# no worker drain so the run stays queued/preparing; SQL is setup-only).
#
# Agreed contract under test (encounters.discard must revoke queued work,
# currently a no-op per encounters.py:597 docstring):
# - Author creates a draft + starts a run (POST /encounters/{id}/runs),
#   leaving it queued/preparing.
# - POST /encounters/{id}/discard with If-Match + {confirm true} -> 200
#   discarded.
# - GET /runs/{id} shows cancelled/ineligible (same cancelled vocabulary
#   slice-2 asserts via _s51_run_status) and POST /runs/{id}/retry -> 409.
# ---------------------------------------------------------------------------


def test_s51_slice4b_discard_cancels_queued_run():
    _r3_reset_full()
    _r3_insert_bundle("registration", _R3_REG_BUNDLE)
    with TestClient(app) as admin, TestClient(app) as author:
        login(admin)
        create_physician(admin, "r3s4bdiscard", "r3-s4b-discard-create")
        login(author, "r3s4bdiscard", "secret", "physician")
        _patient, encounter = create_patient(author, "0865000004", "r3-s4b-p")
        encounter_id = encounter["id"]
        revision = _r3_revision(author, encounter_id)
        started = author.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=mutation_headers(author, key="r3-s4b-run-1", revision=revision),
        )
        assert started.status_code == 202
        run_id = started.json()["run_id"]
        # Precondition: the run is still queued before discard.
        assert _s51_run_status(run_id) == "queued"

        current = _r3_revision(author, encounter_id)
        discarded = author.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={"confirm": True},
            headers=mutation_headers(
                author, key="r3-s4b-discard-1", revision=current
            ),
        )
        assert discarded.status_code == 200
        assert encounter_body(discarded.json())["state"] == "discarded"

        # Queued work is cancelled, never eligible.
        assert _s51_run_status(run_id) == "cancelled"
        body = author.get(f"/api/v1/runs/{run_id}").json()
        assert body["run"]["status"] == "cancelled"
        run_rev = int(body["run"]["revision"])
        retry = author.post(
            f"/api/v1/runs/{run_id}/retry",
            json={
                "question_key": _R3_QUESTION,
                "failed_stage": "estimating_cpts",
                "expected_run_revision": run_rev,
            },
            headers=mutation_headers(author, key="r3-s4b-retry-1"),
        )
        assert retry.status_code == 409

