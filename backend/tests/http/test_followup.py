"""S14 slice 1 (RED): follow-up creation + shared read + author-only edit (T1).

Scope: POST /api/v1/patients/{patient_id}/encounters with
{"baseline_encounter_id": ...} against a signed baseline. No follow-up
route exists yet: every test below currently fails with 404 (missing route).

Agreed contract under test:
- Signed baseline is fixture setup only, via direct SQL UPDATE
  encounters SET state='signed' (no bypass-sign production route).
- POST with CSRF + Idempotency-Key -> 201, kind "follow_up",
  state "draft", revision 1, author_id == creator, baseline linkage
  ("baseline_encounter_id") visible in the POST body and in
  GET /api/v1/encounters/{followup_id}.
- Shared read: any active physician and admin can GET the follow-up and
  see it in GET /patients/{id}/encounters (200).
- Author-only edit: PATCH by non-author -> 403, admin PATCH -> 403,
  anonymous GET -> 401 (existing session convention).
- Guards: follow-up against a draft (non-signed) baseline -> 409,
  missing baseline -> 404; admin create -> 403; anonymous -> 401;
  missing Idempotency-Key -> 422 (physician convention).
- All behavior assertions go through public HTTP; SQL is used only to
  mark the baseline signed during setup. Synthetic values only.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_followup():
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


def sign_baseline(encounter_id):
    """Fixture setup only: mark the registration draft as signed via SQL."""
    with db.transaction() as conn:
        conn.execute(
            text("UPDATE encounters SET state = 'signed' WHERE id = :id"),
            {"id": str(encounter_id)},
        )


def encounter_body(payload):
    if isinstance(payload, dict) and isinstance(payload.get("encounter"), dict):
        return payload["encounter"]
    return payload


def test_physician_creates_followup_from_signed_baseline():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "fudoc", "followup-create-fudoc")
        me = login(physician, "fudoc", "secret", "physician")
        patient, baseline = create_patient(physician, "0741111111", "followup-p1")
        sign_baseline(baseline["id"])

        created = physician.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": baseline["id"]},
            headers=mutation_headers(physician, "followup-key-1"),
        )
        assert created.status_code == 201
        followup = encounter_body(created.json())
        assert followup["kind"] == "follow_up"
        assert followup["state"] == "draft"
        assert followup["revision"] == 1
        assert followup["author_id"] == me["user"]["id"]
        assert followup["patient_id"] == patient["id"]
        assert followup["baseline_encounter_id"] == baseline["id"]

        fetched = physician.get(f"/api/v1/encounters/{followup['id']}")
        assert fetched.status_code == 200
        seen = encounter_body(fetched.json())
        assert seen["kind"] == "follow_up"
        assert seen["revision"] == 1
        assert seen["baseline_encounter_id"] == baseline["id"]


def test_shared_read_but_author_only_edit_on_followup():
    with (
        TestClient(app) as admin,
        TestClient(app) as author,
        TestClient(app) as other,
    ):
        login(admin)
        create_physician(admin, "fudocA", "followup-create-fudocA")
        create_physician(admin, "fudocB", "followup-create-fudocB")
        login(author, "fudocA", "secret", "physician")
        login(other, "fudocB", "secret", "physician")
        patient, baseline = create_patient(author, "0742222222", "followup-p2")
        sign_baseline(baseline["id"])

        created = author.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": baseline["id"]},
            headers=mutation_headers(author, "followup-key-2"),
        )
        assert created.status_code == 201
        followup_id = encounter_body(created.json())["id"]

        other_got = other.get(f"/api/v1/encounters/{followup_id}")
        assert other_got.status_code == 200
        assert encounter_body(other_got.json())["kind"] == "follow_up"
        admin_got = admin.get(f"/api/v1/encounters/{followup_id}")
        assert admin_got.status_code == 200

        listed = other.get(f"/api/v1/patients/{patient['id']}/encounters")
        assert listed.status_code == 200
        ids = [item["id"] for item in listed.json()["items"]]
        assert followup_id in ids

        other_patch = other.patch(
            f"/api/v1/encounters/{followup_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=mutation_headers(other, revision="1"),
        )
        assert other_patch.status_code == 403
        admin_patch = admin.patch(
            f"/api/v1/encounters/{followup_id}",
            json={"draft_data": {"complaint": "synthetic-test-value"}},
            headers=mutation_headers(admin, revision="1"),
        )
        assert admin_patch.status_code == 403

    with TestClient(app) as anon:
        denied = anon.get(f"/api/v1/encounters/{followup_id}")
        assert denied.status_code == 401


def test_followup_guards_baseline_state_auth_and_idempotency():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "fudocG", "followup-create-fudocG")
        login(physician, "fudocG", "secret", "physician")
        patient, draft_baseline = create_patient(physician, "0743333333", "followup-p3")

        # Draft (non-signed) baseline conflicts.
        conflicted = physician.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": draft_baseline["id"]},
            headers=mutation_headers(physician, "followup-key-3a"),
        )
        assert conflicted.status_code == 409

        # Missing baseline is not found.
        missing = physician.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": "00000000-0000-0000-0000-000000000000"},
            headers=mutation_headers(physician, "followup-key-3b"),
        )
        assert missing.status_code == 404

        sign_baseline(draft_baseline["id"])

        # Admin create is forbidden (physician-only, like POST /patients).
        admin_create = admin.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": draft_baseline["id"]},
            headers=mutation_headers(admin, "followup-key-3c"),
        )
        assert admin_create.status_code == 403

        # Missing Idempotency-Key is rejected.
        no_key = physician.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": draft_baseline["id"]},
            headers={"X-CSRF-Token": physician.cookies.get("xinsight_csrf")},
        )
        assert no_key.status_code == 422

    with TestClient(app) as anon:
        anon_create = anon.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": draft_baseline["id"]},
        )
        assert anon_create.status_code == 401


def test_other_open_drafts_visible_read_only_in_list():
    with TestClient(app) as admin, TestClient(app) as author:
        login(admin)
        create_physician(admin, "fudocL", "followup-create-fudocL")
        login(author, "fudocL", "secret", "physician")
        patient, baseline = create_patient(author, "0744444444", "followup-p4")
        sign_baseline(baseline["id"])

        created = author.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": baseline["id"]},
            headers=mutation_headers(author, "followup-key-4"),
        )
        assert created.status_code == 201
        followup_id = encounter_body(created.json())["id"]

        listed = author.get(f"/api/v1/patients/{patient['id']}/encounters")
        assert listed.status_code == 200
        items = listed.json()["items"]
        by_id = {item["id"]: item for item in items}
        assert baseline["id"] in by_id
        assert followup_id in by_id
        assert by_id[baseline["id"]]["state"] == "signed"
        assert by_id[followup_id]["kind"] == "follow_up"
        assert by_id[followup_id]["state"] == "draft"
        assert by_id[followup_id]["revision"] == 1


# S14 slice 2 (RED): follow-up baseline copy semantics (T1).
#
# Slice-1 leaves POST /patients/{id}/encounters creating an empty draft
# (draft_data {}). Slice-2 defines the copy contract, which does not exist
# yet: history values + medications must copy verbatim from the signed
# baseline, history provenance must restamp to the follow-up creator, and
# history_reconciliation must open as pending linked to the baseline, while
# PANSS/C-SSRS answers never copy (follow-up starts unanswered) and the
# baseline keeps its own scores. Guard pins (reconciliation shape, FR-14
# regimen exclusion) hold on the follow_up kind.
#
# Synthetic values only; SQL only marks the baseline signed during setup.

from pathlib import Path  # noqa: E402

SYNTHETIC_HISTORY_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "content" / "history"
)

_S2_PANSS_IDS = (
    ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]
    + ["N1", "N2", "N3", "N4", "N5", "N6", "N7"]
    + [
        "G1",
        "G2",
        "G3",
        "G4",
        "G5",
        "G6",
        "G7",
        "G8",
        "G9",
        "G10",
        "G11",
        "G12",
        "G13",
        "G14",
        "G15",
        "G16",
    ]
)


def test_followup_copies_history_and_medications_with_pending_reconciliation(
    monkeypatch,
):
    """Slice-2 copy contract (RED): baseline history/meds copy, recon pending."""
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(SYNTHETIC_HISTORY_DIR))
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "fudocS2a", "followup-s2a-fudoc")
        me = login(physician, "fudocS2a", "secret", "physician")
        patient, baseline = create_patient(physician, "0745555555", "followup-s2a-p1")
        values = {
            "synthetic_flag_true": {"status": "known", "value": True},
            "synthetic_flag_false": {"status": "known", "value": False},
        }
        medications = [
            {"catalog_drug_id": "synthetic-med-a"},
            {"unknown_label": "synthetic-med-b"},
        ]
        patched = physician.patch(
            f"/api/v1/encounters/{baseline['id']}",
            json={
                "draft_data": {
                    "history": {
                        "definition_version": "synthetic-history-v1",
                        "values": values,
                    },
                    "medications": medications,
                }
            },
            headers=mutation_headers(physician, revision=baseline["revision"]),
        )
        assert patched.status_code == 200
        sign_baseline(baseline["id"])

        created = physician.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": baseline["id"]},
            headers=mutation_headers(physician, "followup-s2a-key-1"),
        )
        assert created.status_code == 201
        draft = encounter_body(created.json())["draft_data"]
        assert draft["history"]["values"] == values
        assert draft["medications"] == medications
        recon = draft["history_reconciliation"]
        assert recon["status"] == "pending"
        assert recon["baseline_encounter_id"] == baseline["id"]
        assert draft["history"]["provenance"]["actor_id"] == me["user"]["id"]


def test_followup_starts_with_unanswered_panss_cssrs_but_baseline_scores_preserved(
    monkeypatch,
):
    """Slice-2 freshness pin: PANSS/C-SSRS never copy; baseline keeps scores."""
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(SYNTHETIC_HISTORY_DIR))
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "fudocS2b", "followup-s2b-fudoc")
        login(physician, "fudocS2b", "secret", "physician")
        patient, baseline = create_patient(physician, "0745555556", "followup-s2b-p1")
        panss_answers = {item_id: 1 for item_id in _S2_PANSS_IDS}
        cssrs_answers = {
            "L3": {"endorsed": True, "period": "historical"},
            "L4": {"endorsed": True, "period": "current"},
        }
        patched = physician.patch(
            f"/api/v1/encounters/{baseline['id']}",
            json={
                "draft_data": {
                    "panss": {"answers": panss_answers},
                    "cssrs": {"answers": cssrs_answers},
                }
            },
            headers=mutation_headers(physician, revision=baseline["revision"]),
        )
        assert patched.status_code == 200
        sign_baseline(baseline["id"])

        created = physician.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": baseline["id"]},
            headers=mutation_headers(physician, "followup-s2b-key-1"),
        )
        assert created.status_code == 201
        draft = encounter_body(created.json())["draft_data"]
        # Fresh scales: never copied as new answers ...
        assert "panss" not in draft
        assert "cssrs" not in draft
        # ... yet the follow-up still carries the pending baseline linkage
        # (slice-2 copy contract; RED: empty draft has no recon key).
        assert draft["history_reconciliation"]["status"] == "pending"
        assert (
            draft["history_reconciliation"]["baseline_encounter_id"] == baseline["id"]
        )

        fetched = physician.get(f"/api/v1/encounters/{baseline['id']}")
        assert fetched.status_code == 200
        baseline_draft = encounter_body(fetched.json())["draft_data"]
        assert baseline_draft["panss"]["answers"] == panss_answers
        assert baseline_draft["cssrs"]["answers"] == cssrs_answers


def test_followup_reconciliation_rejects_bare_marker_and_requires_object(monkeypatch):
    """Slice-2 guard pin on follow_up kind: bare recon 422, FR-14 dose 422."""
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(SYNTHETIC_HISTORY_DIR))
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "fudocS2c", "followup-s2c-fudoc")
        login(physician, "fudocS2c", "secret", "physician")
        patient, baseline = create_patient(physician, "0745555557", "followup-s2c-p1")
        seeded = physician.patch(
            f"/api/v1/encounters/{baseline['id']}",
            json={
                "draft_data": {
                    "history": {
                        "definition_version": "synthetic-history-v1",
                        "values": {
                            "synthetic_flag_true": {
                                "status": "known",
                                "value": True,
                            },
                        },
                    },
                }
            },
            headers=mutation_headers(physician, revision=baseline["revision"]),
        )
        assert seeded.status_code == 200
        sign_baseline(baseline["id"])

        created = physician.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": baseline["id"]},
            headers=mutation_headers(physician, "followup-s2c-key-1"),
        )
        assert created.status_code == 201
        followup_id = encounter_body(created.json())["id"]
        # Slice-2 copy contract: recon opens pending (RED: empty draft today).
        opened = encounter_body(created.json())["draft_data"]
        assert opened["history_reconciliation"]["status"] == "pending"
        assert (
            opened["history_reconciliation"]["baseline_encounter_id"] == baseline["id"]
        )

        bare = physician.patch(
            f"/api/v1/encounters/{followup_id}",
            json={"draft_data": {"history_reconciliation": "reconciled"}},
            headers=mutation_headers(physician, revision=1),
        )
        assert bare.status_code == 422
        fetched = physician.get(f"/api/v1/encounters/{followup_id}")
        assert fetched.status_code == 200
        assert encounter_body(fetched.json())["revision"] == 1

        confirmed = physician.patch(
            f"/api/v1/encounters/{followup_id}",
            json={"draft_data": {"history_reconciliation": {"status": "confirmed"}}},
            headers=mutation_headers(physician, revision=1),
        )
        assert confirmed.status_code == 200

        dosed = physician.patch(
            f"/api/v1/encounters/{followup_id}",
            json={
                "draft_data": {
                    "medications": [
                        {"catalog_drug_id": "synthetic-med-a", "dose": "10"}
                    ]
                }
            },
            headers=mutation_headers(physician, revision=2),
        )
        assert dosed.status_code == 422
        refetched = physician.get(f"/api/v1/encounters/{followup_id}")
        assert refetched.status_code == 200
        seen = encounter_body(refetched.json())
        assert seen["revision"] == 2
        assert "medications" not in seen["draft_data"]


# S14 slice 3 (RED): concurrent follow-up drafts + changed-baseline awareness (T1).
#
# (a) Coexistence: two physicians each open their own follow-up draft against
# the SAME signed baseline; both drafts persist side by side and stay
# author-owned (cross-edit denied). No sign logic involved.
# (b) Changed-baseline indicator (read-side only): once a NEWER signed record
# for the same patient exists, the older-baseline follow-up must surface
# `baseline_changed: True` on GET single + GET list, without rebasing its
# stored linkage and without blocking author edits (sign enforcement is
# S49/S51, never here).
#
# Synthetic values only; SQL only marks baselines signed / inserts the newer
# signed fixture row during setup.


def test_two_physicians_create_separate_followup_drafts():
    """Slice-3a: two physicians hold separate drafts on one signed baseline."""
    with (
        TestClient(app) as admin,
        TestClient(app) as author_a,
        TestClient(app) as author_b,
    ):
        login(admin)
        create_physician(admin, "fudocS3aA", "followup-s3a-fudocA")
        create_physician(admin, "fudocS3aB", "followup-s3a-fudocB")
        me_a = login(author_a, "fudocS3aA", "secret", "physician")
        me_b = login(author_b, "fudocS3aB", "secret", "physician")
        patient, baseline = create_patient(author_a, "0746666661", "followup-s3a-p1")
        sign_baseline(baseline["id"])

        created_a = author_a.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": baseline["id"]},
            headers=mutation_headers(author_a, "followup-s3a-key-A"),
        )
        assert created_a.status_code == 201
        created_b = author_b.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": baseline["id"]},
            headers=mutation_headers(author_b, "followup-s3a-key-B"),
        )
        assert created_b.status_code == 201
        draft_a = encounter_body(created_a.json())
        draft_b = encounter_body(created_b.json())

        assert draft_a["id"] != draft_b["id"]
        assert draft_a["author_id"] == me_a["user"]["id"]
        assert draft_b["author_id"] == me_b["user"]["id"]
        assert draft_a["baseline_encounter_id"] == baseline["id"]
        assert draft_b["baseline_encounter_id"] == baseline["id"]
        for draft in (draft_a, draft_b):
            assert draft["kind"] == "follow_up"
            assert draft["state"] == "draft"
            assert draft["revision"] == 1

        listed = author_a.get(f"/api/v1/patients/{patient['id']}/encounters")
        assert listed.status_code == 200
        items = listed.json()["items"]
        assert len(items) == 3
        by_id = {item["id"]: item for item in items}
        assert by_id[baseline["id"]]["state"] == "signed"
        assert by_id[draft_a["id"]]["author_id"] == me_a["user"]["id"]
        assert by_id[draft_b["id"]]["author_id"] == me_b["user"]["id"]

        own_patch = author_a.patch(
            f"/api/v1/encounters/{draft_a['id']}",
            json={"draft_data": {"complaint": "synthetic-s3a-value"}},
            headers=mutation_headers(author_a, revision="1"),
        )
        assert own_patch.status_code == 200
        cross_patch = author_b.patch(
            f"/api/v1/encounters/{draft_a['id']}",
            json={"draft_data": {"complaint": "synthetic-s3a-cross"}},
            headers=mutation_headers(author_b, revision="2"),
        )
        assert cross_patch.status_code == 403


def test_followup_reports_changed_baseline_after_newer_signed_record():
    """Slice-3b (RED): follow-up flags a newer signed record (read-side only)."""
    with (
        TestClient(app) as admin,
        TestClient(app) as author_a,
        TestClient(app) as author_b,
    ):
        login(admin)
        create_physician(admin, "fudocS3bA", "followup-s3b-fudocA")
        create_physician(admin, "fudocS3bB", "followup-s3b-fudocB")
        login(author_a, "fudocS3bA", "secret", "physician")
        me_b = login(author_b, "fudocS3bB", "secret", "physician")
        patient, baseline_b1 = create_patient(author_a, "0746666662", "followup-s3b-p1")
        sign_baseline(baseline_b1["id"])

        created = author_a.post(
            f"/api/v1/patients/{patient['id']}/encounters",
            json={"baseline_encounter_id": baseline_b1["id"]},
            headers=mutation_headers(author_a, "followup-s3b-key-1"),
        )
        assert created.status_code == 201
        followup_id = encounter_body(created.json())["id"]

        # Fixture setup only: a NEWER signed registration-kind record for the
        # same patient appears after F1 was drafted (inserted later, so its
        # created_at orders after F1). No production route creates this.
        with db.transaction() as conn:
            conn.execute(
                text(
                    "INSERT INTO encounters "
                    "(patient_id, kind, author_id, state, draft_data) "
                    "VALUES (:pid, 'registration', :author, 'signed', "
                    "CAST(:data AS jsonb))"
                ),
                {
                    "pid": str(patient["id"]),
                    "author": str(me_b["user"]["id"]),
                    "data": "{}",
                },
            )

        fetched = author_a.get(f"/api/v1/encounters/{followup_id}")
        assert fetched.status_code == 200
        body = encounter_body(fetched.json())
        # RED: no changed-baseline signal exists yet (KeyError today).
        assert body["baseline_changed"] is True

        listed = author_a.get(f"/api/v1/patients/{patient['id']}/encounters")
        assert listed.status_code == 200
        by_id = {item["id"]: item for item in listed.json()["items"]}
        assert by_id[followup_id]["baseline_changed"] is True

        # No auto-rebase: stored linkage still points at B1, still pending.
        assert body["baseline_encounter_id"] == baseline_b1["id"]
        assert body["draft_data"]["history_reconciliation"] == {
            "status": "pending",
            "baseline_encounter_id": baseline_b1["id"],
        }

        # No sign-blocking here (S49/S51 own that): author edit still works.
        patched = author_a.patch(
            f"/api/v1/encounters/{followup_id}",
            json={"draft_data": {"complaint": "synthetic-s3b-value"}},
            headers=mutation_headers(author_a, revision="1"),
        )
        assert patched.status_code == 200
