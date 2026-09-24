"""S56 item 1 (RED): exact-digest commit starts replacement; stale fails.

Scope: docs/dev/tasks.md S56 item 1; plan.md 10.3 steps 4-6;
seams T10 (restore commit interface) + T1 (authenticated HTTP vs real
PostgreSQL). SYNTHETIC VALUES ONLY.

Behavior under test (NOT implemented -- RED, expect 404/405 on POST
/api/v1/restores/commit since S55 left no commit route):
- Admin POST /api/v1/restores/commit
  {restore_id, confirmation_digest} with Idempotency-Key and the exact
  staged digest starts replacement: 200/202 with status
  committing/committed, GET /restores/{id} shows committing/committed,
  a pre-restore backup job exists via the public backup interface, and
  a second start with the same digest but a fresh key fails (fenced).
- Mutated (last hex char flipped), expired (backdated expires_at), and
  superseded (newer staging exists) digests fail 409/422 with a field
  error and NO live mutation (live patients byte-identical via
  GET /api/v1/patients).
- Physician POST -> 403, anonymous POST -> 401.

Full switch/no-mixed-traffic semantics belong to S56 slices 2-4 and are
NOT asserted here.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

import pytest

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_restore_commit():
    from x_insight.operations.restore import exit_maintenance

    exit_maintenance()
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, runs, run_questions, reasoning_jobs, "
                "reasoning_attempts, run_question_artifacts, run_proposals, "
                "audit_events, model_bundle_pointers, model_bundle_events, "
                "mcp_question_grants, provider_configs, "
                "provider_config_pointer, queue_fairness, ddi_dataset_releases, "
                "networks, network_versions, recovery_jobs"
            )
        )
    reset_all()
    yield
    reset_all()
    exit_maintenance()


def login(client, username="admin", password="admin", role="admin"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 200
    return response.json()


def admin_headers(client, key):
    return {
        "X-CSRF-Token": client.cookies.get("xinsight_csrf"),
        "Idempotency-Key": key,
    }


def create_physician(admin, username, key):
    created = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": "secret"},
        headers=admin_headers(admin, key),
    )
    assert created.status_code == 201
    return created.json()


def create_patient(physician, patient_id, key, **overrides):
    body = {
        "first_name": "Anna",
        "last_name": "Muller",
        "sex": "F",
        "age": 30,
        "patient_id": patient_id,
        "clinical_status": "first_time",
        **overrides,
    }
    response = physician.post(
        "/api/v1/patients", json=body, headers=admin_headers(physician, key)
    )
    assert response.status_code == 201
    return response.json()


SYNTHETIC_XML = (
    b'<?xml version="1.0"?><BIF VERSION="0.3"><NETWORK><NAME>s56</NAME></NETWORK></BIF>'
)


def seed_content_fixture():
    """Direct-SQL fixture setup (disposable storage init; assertions use T10/T1)."""
    xml_hash = hashlib.sha256(SYNTHETIC_XML).hexdigest()
    with db.transaction() as conn:
        network_id = (
            conn.execute(
                text("INSERT INTO networks(key) VALUES (:k) RETURNING id"),
                {"k": "s56-test-network"},
            )
            .mappings()
            .first()["id"]
        )
        conn.execute(
            text(
                "INSERT INTO network_versions "
                "(network_id, version, xml, sha256, byte_count, xsd_report, "
                "semantic_report, admission_report) "
                "VALUES (:nid, 1, :xml, :sha, :n, "
                "CAST(:xsd AS jsonb), CAST(:sem AS jsonb), CAST(:adm AS jsonb))"
            ),
            {
                "nid": str(network_id),
                "xml": SYNTHETIC_XML,
                "sha": xml_hash,
                "n": len(SYNTHETIC_XML),
                "xsd": json.dumps({"valid": True, "synthetic": True}),
                "sem": json.dumps({"executable": False, "synthetic": True}),
                "adm": json.dumps({"admitted": False, "synthetic": True}),
            },
        )
        conn.execute(
            text(
                "INSERT INTO provider_configs(revision, base_url, model) "
                "VALUES (1, :url, :model)"
            ),
            {"url": "http://localhost:9/synthetic", "model": "synthetic-test"},
        )
        conn.execute(
            text(
                "INSERT INTO ddi_dataset_releases "
                "(version, dataset_hash, source_inventory, review_record) "
                "VALUES (:v, :h, CAST(:inv AS jsonb), CAST(:rev AS jsonb))"
            ),
            {
                "v": "s56-synthetic-ddi-v1",
                "h": hashlib.sha256(b"s56-ddi").hexdigest(),
                "inv": json.dumps({"synthetic": True, "documents": 0}),
                "rev": json.dumps({"decision": "approved", "synthetic": True}),
            },
        )
    return xml_hash


def build_populated_backup_archive(admin, key):
    """Create + poll an S54 backup job, return (job_id, zip bytes)."""
    started = admin.post(
        "/api/v1/backups",
        json={},
        headers=admin_headers(admin, key),
    )
    assert started.status_code == 202
    job_id = started.json()["job_id"]

    status = None
    for _ in range(60):
        polled = admin.get(f"/api/v1/backups/{job_id}")
        assert polled.status_code == 200
        status = polled.json()["status"]
        if status == "succeeded":
            break
        assert status in ("queued", "running")
        time.sleep(0.5)
    assert status == "succeeded", f"backup job did not succeed: {status!r}"

    downloaded = admin.get(f"/api/v1/backups/{job_id}/download")
    assert downloaded.status_code == 200
    assert "zip" in downloaded.headers.get("content-type", "").lower()
    return job_id, downloaded.content


def validate_archive(admin, archive_bytes, key):
    return admin.post(
        "/api/v1/restores/validate",
        files=[
            ("archive", ("backup.zip", io.BytesIO(archive_bytes), "application/zip"))
        ],
        headers=admin_headers(admin, key),
    )


def assert_staged_contract(body):
    """Staged-validation contract (S55 item 1, already implemented)."""
    assert body["status"] == "staged"
    restore_id = body.get("restore_id", body.get("job_id", body.get("id")))
    assert restore_id, f"missing restore/job id: {body!r}"
    assert "schema_version" in body
    digest = body.get("confirmation_digest")
    assert isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), (
        f"confirmation_digest must be 64-hex sha256: {digest!r}"
    )
    assert isinstance(body.get("report"), dict), f"missing report: {body!r}"
    return restore_id, digest, body["report"]


def commit_restore(client, restore_id, digest, key):
    return client.post(
        "/api/v1/restores/commit",
        json={"restore_id": restore_id, "confirmation_digest": digest},
        headers=admin_headers(client, key),
    )


def flip_last_hex(digest):
    return digest[:-1] + ("0" if digest[-1] != "0" else "1")


def live_patients_snapshot(admin):
    listed = admin.get("/api/v1/patients", params={"limit": 100})
    assert listed.status_code == 200
    return listed.content


def test_restore_commit_exact_digest_starts_replacement():
    """S56 item 1 (RED, T10+T1): exact digest starts replacement + fences retry."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, f"s56doc{nonce}", f"s56-commit-phys-{nonce}")
        login(physician, f"s56doc{nonce}", "secret", "physician")
        create_patient(physician, "0056000001", f"s56-commit-patient-{nonce}")

        seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(
            admin, f"s56-commit-backup-{nonce}"
        )
        staged = validate_archive(admin, archive_bytes, f"s56-commit-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id, digest, _ = assert_staged_contract(staged.json())

        started = commit_restore(admin, restore_id, digest, f"s56-commit-go-{nonce}")
        assert started.status_code in (200, 202), (
            f"exact-digest commit must start replacement, got "
            f"{started.status_code}: {started.text[:500]!r}"
        )
        body = started.json()
        assert body["status"] in ("committing", "committed"), (
            f"commit must report committing/committed: {body!r}"
        )
        assert str(body.get("restore_id")) == str(restore_id)
        assert body.get("confirmation_digest") == digest
        assert "schema_version" in body

        # Slice 3 revokes pre-commit sessions on commit; re-authenticate
        # the same clients for the post-commit reads below.
        login(admin)

        reread = admin.get(f"/api/v1/restores/{restore_id}")
        assert reread.status_code == 200
        again = reread.json()
        assert again["status"] in ("committing", "committed"), (
            f"GET restores must show committing/committed: {again!r}"
        )
        assert again.get("confirmation_digest") == digest

        # Quiesce/fence/pre-backup observable at T10/T1: the commit must
        # have taken a pre-restore backup visible via the public backup
        # interface before switching.
        pre_id = (
            body.get("pre_restore_backup_id")
            or body.get("pre_restore_backup_job_id")
            or body.get("pre_backup_id")
        )
        assert isinstance(pre_id, str) and pre_id, (
            f"commit must return a pre-restore backup id: {body!r}"
        )
        pre = admin.get(f"/api/v1/backups/{pre_id}")
        assert pre.status_code == 200, (
            f"pre-restore backup must exist via public interface, got "
            f"{pre.status_code}: {pre.text[:300]!r}"
        )
        assert str(pre.json().get("job_id")) == str(pre_id)

        # Generation fenced: same digest with a fresh key cannot start a
        # second replacement once the first has begun.
        second = commit_restore(admin, restore_id, digest, f"s56-commit-retry-{nonce}")
        assert second.status_code in (409, 422), (
            f"second commit start must be fenced, got {second.status_code}: "
            f"{second.text[:500]!r}"
        )

        fenced = admin.get(f"/api/v1/restores/{restore_id}")
        assert fenced.status_code == 200
        assert fenced.json()["status"] in ("committing", "committed")


def test_restore_commit_stale_digest_rejected_live_unchanged():
    """S56 item 1 (RED, T10+T1): wrong/expired/superseded digests fail; live same."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, f"s56sdoc{nonce}", f"s56-stale-phys-{nonce}")
        login(physician, f"s56sdoc{nonce}", "secret", "physician")
        made = create_patient(physician, "0056000002", f"s56-stale-patient-{nonce}")
        patient_uuid = made["patient"]["id"]

        seed_content_fixture()
        _, archive_a = build_populated_backup_archive(
            admin, f"s56-stale-backup-a-{nonce}"
        )
        first = validate_archive(admin, archive_a, f"s56-stale-val-a-{nonce}")
        assert first.status_code in (200, 202)
        rid_a, digest_a, _ = assert_staged_contract(first.json())

        def assert_rejected(response, label):
            assert response.status_code in (409, 422), (
                f"{label} digest must fail 409/422, got {response.status_code}: "
                f"{response.text[:500]!r}"
            )
            body = response.json()
            assert body.get("field_errors"), (
                f"{label} failure must carry a field error: {body!r}"
            )
            blob = (
                str(body.get("code", ""))
                + str(body.get("message", ""))
                + str(body.get("field_errors", ""))
            ).lower()
            assert any(
                token in blob
                for token in (
                    "digest",
                    "confirm",
                    "stale",
                    "expired",
                    "superseded",
                    "mismatch",
                )
            ), f"{label} error must name the digest problem: {body!r}"

        def assert_live_unchanged(expected_bytes):
            after = admin.get("/api/v1/patients", params={"limit": 100})
            assert after.status_code == 200
            assert after.content == expected_bytes, "live patients mutated on reject"
            assert patient_uuid in after.text, "synthetic patient vanished on reject"
            with TestClient(app) as admin_again:
                login(admin_again)

        before = live_patients_snapshot(admin)

        # 1. Mutated digest: last hex char flipped.
        wrong = flip_last_hex(digest_a)
        assert wrong != digest_a
        assert_rejected(
            commit_restore(admin, rid_a, wrong, f"s56-stale-wrong-{nonce}"), "wrong"
        )
        assert_live_unchanged(before)

        # 2. Expired digest: backdate expires_at (disposable fixture setup),
        # GET shows expired, then the exact digest must fail.
        with db.transaction() as conn:
            conn.execute(
                text(
                    "UPDATE recovery_jobs SET expires_at = "
                    "now() - interval '1 hour' "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": rid_a},
            )
        stale_read = admin.get(f"/api/v1/restores/{rid_a}")
        assert stale_read.status_code == 200
        assert stale_read.json()["expired"] is True
        assert stale_read.json().get("confirmation_digest") == digest_a
        assert_rejected(
            commit_restore(admin, rid_a, digest_a, f"s56-stale-expired-{nonce}"),
            "expired",
        )
        assert_live_unchanged(before)

        # 3. Superseded digest: stage a newer archive, then the older exact
        # digest must fail even though it was once valid.
        create_patient(physician, "0056000003", f"s56-stale-patient-b-{nonce}")
        before = live_patients_snapshot(admin)
        _, archive_b = build_populated_backup_archive(
            admin, f"s56-stale-backup-b-{nonce}"
        )
        second_staged = validate_archive(admin, archive_b, f"s56-stale-val-b-{nonce}")
        assert second_staged.status_code in (200, 202)
        rid_b, digest_b, _ = assert_staged_contract(second_staged.json())
        assert digest_b != digest_a, "distinct archives must yield distinct digests"

        reread_a = admin.get(f"/api/v1/restores/{rid_a}")
        assert reread_a.status_code == 200
        assert reread_a.json()["superseded"] is True
        assert_rejected(
            commit_restore(admin, rid_a, digest_a, f"s56-stale-super-{nonce}"),
            "superseded",
        )
        assert_live_unchanged(before)

        # The current staging is untouched by the failed commits above.
        current = admin.get(f"/api/v1/restores/{rid_b}")
        assert current.status_code == 200
        assert current.json().get("confirmation_digest") == digest_b


def test_restore_commit_auth_matrix():
    """S56 item 1 (RED, T1): physician 403, anonymous 401 on POST commit."""
    nonce = uuid.uuid4().hex[:8]
    with (
        TestClient(app) as admin,
        TestClient(app) as physician,
        TestClient(app) as anon,
    ):
        login(admin)
        create_physician(admin, f"s56adoc{nonce}", f"s56-auth-phys-{nonce}")
        login(physician, f"s56adoc{nonce}", "secret", "physician")
        create_patient(physician, "0056000004", f"s56-auth-patient-{nonce}")
        seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(
            admin, f"s56-auth-backup-{nonce}"
        )
        staged = validate_archive(admin, archive_bytes, f"s56-auth-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id, digest, _ = assert_staged_contract(staged.json())

        phys = commit_restore(physician, restore_id, digest, f"s56-auth-phys-{nonce}")
        assert phys.status_code == 403, (
            f"physician commit must be denied, got {phys.status_code}: "
            f"{phys.text[:300]!r}"
        )

        anon_post = anon.post(
            "/api/v1/restores/commit",
            json={"restore_id": restore_id, "confirmation_digest": digest},
            headers={"Idempotency-Key": f"s56-auth-anon-{nonce}"},
        )
        assert anon_post.status_code == 401, (
            f"anonymous commit must be unauthenticated, got {anon_post.status_code}: "
            f"{anon_post.text[:300]!r}"
        )


# ---------------------------------------------------------------------------
# S56 item 2 (RED, slice 2): phased switch behind maintenance, no mixed
# traffic, old provider work fenced. Seams T10/T1/T8. SYNTHETIC VALUES ONLY.
#
# Slice 1 only marks committed + enters maintenance + bumps generation +
# pre-backup; it does NOT replace domain tables and installs NO maintenance
# write guard. These tests expect the slice-2 behavior and must RED for the
# missing replacement/guard (writes still 201/200, extra patient still live).
# Session revoke/audit/rollback belong to slices 3-4 and are NOT asserted.
# ---------------------------------------------------------------------------


def test_restore_commit_replaces_live_tables_not_merge():
    """S56 item 2 (RED, T10+T1): staged patients ENVELOP live after commit.

    Deterministic: archive built from state with P_STAGED only, then
    P_LIVE_EXTRA created live, old archive validated + committed. After
    commit GET /patients must show P_STAGED present and P_LIVE_EXTRA gone
    (replacement, never merge). Currently RED: slice 1 never switches
    tables, so both remain live.
    """
    from x_insight.operations.restore import exit_maintenance

    exit_maintenance()
    nonce = uuid.uuid4().hex[:8]
    staged_pid = "0056000011"
    extra_pid = "0056000012"
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, f"s56rdoc{nonce}", f"s56-replace-phys-{nonce}")
        login(physician, f"s56rdoc{nonce}", "secret", "physician")
        create_patient(physician, staged_pid, f"s56-replace-staged-{nonce}")

        seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(
            admin, f"s56-replace-backup-{nonce}"
        )
        # Live diverges AFTER the backup: extra patient is not in the archive.
        create_patient(physician, extra_pid, f"s56-replace-extra-{nonce}")

        staged = validate_archive(admin, archive_bytes, f"s56-replace-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id, digest, _ = assert_staged_contract(staged.json())

        started = commit_restore(admin, restore_id, digest, f"s56-replace-go-{nonce}")
        assert started.status_code in (200, 202), (
            f"commit must start, got {started.status_code}: {started.text[:300]!r}"
        )
        assert started.json()["status"] in ("committing", "committed")

        # Slice 3 revokes pre-commit sessions on commit; re-authenticate.
        login(admin)

        listed = admin.get("/api/v1/patients", params={"limit": 100})
        assert listed.status_code == 200
        ids = [item["patient_id"] for item in listed.json()["items"]]
        assert staged_pid in ids, f"staged patient must envelop live: {ids!r}"
        assert extra_pid not in ids, (
            f"replacement, never merge: extra live patient must be gone: {ids!r}"
        )


def test_restore_commit_maintenance_rejects_writes_allows_reads():
    """S56 item 2 (RED, T1): no mixed traffic during maintenance.

    After commit (before slice-3 reopen) maintenance is active: mutating
    writes POST /patients and PATCH /encounters/{id} must be 503 with a
    MAINTENANCE code, while GET reads stay 200. Currently RED: slice 1
    writes only the flag file and installs no write guard, so the POST
    still returns 201 and the PATCH still returns 200.
    """
    from x_insight.operations.restore import exit_maintenance, maintenance_active

    exit_maintenance()
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, f"s56mdoc{nonce}", f"s56-maint-phys-{nonce}")
        login(physician, f"s56mdoc{nonce}", "secret", "physician")
        made = create_patient(physician, "0056000013", f"s56-maint-patient-{nonce}")
        encounter_id = made["encounter"]["id"]
        encounter_rev = made["encounter"]["revision"]

        seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(
            admin, f"s56-maint-backup-{nonce}"
        )
        staged = validate_archive(admin, archive_bytes, f"s56-maint-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id, digest, _ = assert_staged_contract(staged.json())

        started = commit_restore(admin, restore_id, digest, f"s56-maint-go-{nonce}")
        assert started.status_code in (200, 202)

        # Slice 3 revokes pre-commit sessions on commit; re-authenticate
        # (login stays available under maintenance) for the reads/writes.
        login(admin)
        login(physician, f"s56mdoc{nonce}", "secret", "physician")

        # Precondition: slice 1 fencing flag is active (passes already).
        assert maintenance_active() is True, "maintenance flag must be active"

        # Reads stay available.
        reads = admin.get("/api/v1/patients", params={"limit": 100})
        assert reads.status_code == 200
        reread = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert reread.status_code == 200

        # Mutating writes are fenced: POST /patients.
        fresh = physician.post(
            "/api/v1/patients",
            json={
                "first_name": "Anna",
                "last_name": "Muller",
                "sex": "F",
                "age": 30,
                "patient_id": "0056000014",
                "clinical_status": "first_time",
            },
            headers=admin_headers(physician, f"s56-maint-write-{nonce}"),
        )
        assert fresh.status_code == 503, (
            f"POST /patients during maintenance must be 503, got "
            f"{fresh.status_code}: {fresh.text[:300]!r}"
        )
        assert fresh.json().get("code") == "MAINTENANCE", (
            f"POST /patients must carry MAINTENANCE code: {fresh.text[:300]!r}"
        )

        # Mutating writes are fenced: PATCH /encounters/{id}.
        patched = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": {"s56": "synthetic-maint-fenced"}},
            headers={
                "X-CSRF-Token": physician.cookies.get("xinsight_csrf"),
                "If-Match": str(encounter_rev),
            },
        )
        assert patched.status_code == 503, (
            f"PATCH encounter during maintenance must be 503, got "
            f"{patched.status_code}: {patched.text[:300]!r}"
        )
        assert patched.json().get("code") == "MAINTENANCE", (
            f"PATCH encounter must carry MAINTENANCE code: {patched.text[:300]!r}"
        )


def test_restore_commit_old_provider_work_fenced():
    """S56 item 2 (RED, T8+T10+T1): old provider results cannot commit.

    A job claimed before commit carries the pre-commit deployment
    generation; after commit bumps generation, its complete must return
    None (already implemented, stays green). Generation fencing also means
    the exact-digest second commit fails (green) and, with eligible work
    still queued, a worker claim under maintenance must return None (RED:
    queue.py installs no maintenance check, so it still claims the spare
    queued job). Setup uses direct-SQL queued rows (disposable storage
    init); all assertions use public T8/T10/T1 interfaces.
    """
    from x_insight.operations.restore import exit_maintenance
    from x_insight.reasoning import queue as reason_queue

    exit_maintenance()
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, f"s56fdoc{nonce}", f"s56-fence-phys-{nonce}")
        login(physician, f"s56fdoc{nonce}", "secret", "physician")
        made = create_patient(physician, "0056000015", f"s56-fence-patient-{nonce}")
        encounter_id = made["encounter"]["id"]

        with db.transaction() as conn:
            author_id = (
                conn.execute(
                    text("SELECT id FROM users WHERE username = :u"),
                    {"u": f"s56fdoc{nonce}"},
                )
                .mappings()
                .first()["id"]
            )
            # Two queued jobs: one claimed pre-commit (stale afterwards),
            # one spare so a post-commit claim proves fencing, not emptiness.
            for suffix in ("a", "b"):
                conn.execute(
                    text(
                        "INSERT INTO reasoning_jobs "
                        "(run_id, encounter_id, author_id, question_key, "
                        " ordinal, stage, status) "
                        "VALUES (gen_random_uuid(), CAST(:eid AS uuid), "
                        " :author, :qkey, 0, 'preparing_question', 'queued')"
                    ),
                    {
                        "eid": encounter_id,
                        "author": str(author_id),
                        "qkey": f"s56fence-{suffix}-{nonce}",
                    },
                )

        gen_before = reason_queue.get_deployment_generation()
        claimed = reason_queue.claim_next_job()
        assert claimed is not None, "pre-commit claim needs eligible work"
        assert int(claimed["deployment_generation"]) == int(gen_before)

        seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(
            admin, f"s56-fence-backup-{nonce}"
        )
        staged = validate_archive(admin, archive_bytes, f"s56-fence-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id, digest, _ = assert_staged_contract(staged.json())

        started = commit_restore(admin, restore_id, digest, f"s56-fence-go-{nonce}")
        assert started.status_code in (200, 202)

        # Slice 3 revokes pre-commit sessions on commit; re-authenticate
        # for the fenced-retry commit below (queue calls need no session).
        login(admin)

        gen_after = reason_queue.get_deployment_generation()
        assert int(gen_after) == int(gen_before) + 1, (
            f"generation must bump on commit: {gen_before!r} -> {gen_after!r}"
        )

        # Old provider work cannot commit: stale generation fails.
        done = reason_queue.complete_job(
            str(claimed["job_id"]), str(claimed["lease_token"])
        )
        assert done is None, (
            f"pre-commit claimed job must not complete after generation bump: "
            f"{done!r}"
        )

        # Same digest cannot start a second replacement (fenced).
        second = commit_restore(admin, restore_id, digest, f"s56-fence-retry-{nonce}")
        assert second.status_code in (409, 422), (
            f"second commit must be fenced, got {second.status_code}: "
            f"{second.text[:300]!r}"
        )

        # Worker claim under maintenance must refuse despite spare queued work.
        spare = reason_queue.claim_next_job()
        assert spare is None, (
            f"worker claim under maintenance must return None, got {spare!r}"
        )


# ---------------------------------------------------------------------------
# S56 item 3 (RED, slice 3): revoke, cancel-for-restart, audit/log, verified
# reopen. Seams T10/T1/T8. SYNTHETIC VALUES ONLY.
#
# Slice 2 preserves live sessions across the table switch (see the
# "sessions preserved for slice-3 revoke" operator-log note) and never
# cancels restored nonterminal work, records no reopen route, and leaves
# maintenance fenced. These tests expect the slice-3 behavior and must RED
# on: old cookies still accepted, restored run/job still nonterminal, and
# POST /restores/{id}/reopen missing (404) with writes still 503 after it.
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402


def test_restore_commit_revokes_sessions_and_grants():
    """S56 item 3 (RED, T10+T1): commit revokes pre-commit sessions/grants.

    Admin + physician log in BEFORE commit (cookies held); after commit
    both old cookies must be rejected (GET /me 401) while a fresh admin
    login -- and a fresh physician login, since staged users preserve
    live hashes -- succeeds (GET /me 200).

    Grants gap (honest): one grant row is seeded pre-backup so it flows
    through backup/stage/restore, but ``mcp_question_grants.revoked_at``
    has NO public HTTP observable (only the private stdio MCP server
    checks it), so revocation itself is asserted here via the session
    seam; the revoke-all SQL belongs to the slice-3 implementation.
    Currently RED: slice 2 re-inserts live sessions, so old cookies
    still return 200.
    """
    nonce = uuid.uuid4().hex[:8]
    username = f"s56sdoc{nonce}"
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, username, f"s56-sess-phys-{nonce}")
        login(physician, username, "secret", "physician")
        create_patient(physician, "0056000021", f"s56-sess-patient-{nonce}")

        with db.transaction() as conn:
            author_id = (
                conn.execute(
                    text("SELECT id FROM users WHERE username = :u"),
                    {"u": username},
                )
                .mappings()
                .first()["id"]
            )
            conn.execute(
                text(
                    "INSERT INTO mcp_question_grants "
                    "(grant_token, actor_id, question_key) "
                    "VALUES (:grant, CAST(:actor AS uuid), :qkey)"
                ),
                {
                    "grant": f"s56-sess-grant-{nonce}",
                    "actor": str(author_id),
                    "qkey": f"s56sess-{nonce}",
                },
            )

        seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(
            admin, f"s56-sess-backup-{nonce}"
        )
        staged = validate_archive(admin, archive_bytes, f"s56-sess-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id, digest, _ = assert_staged_contract(staged.json())

        started = commit_restore(admin, restore_id, digest, f"s56-sess-go-{nonce}")
        assert started.status_code in (200, 202), (
            f"commit must start, got {started.status_code}: {started.text[:300]!r}"
        )

        for client, label in ((admin, "admin"), (physician, "physician")):
            me = client.get("/api/v1/me")
            assert me.status_code == 401, (
                f"pre-commit {label} session must be revoked after commit, "
                f"got {me.status_code}: {me.text[:300]!r}"
            )

        with TestClient(app) as admin_new:
            login(admin_new)
            assert admin_new.get("/api/v1/me").status_code == 200
        with TestClient(app) as physician_new:
            login(physician_new, username, "secret", "physician")
            assert physician_new.get("/api/v1/me").status_code == 200


def test_restore_commit_cancels_nonterminal_jobs_for_restart():
    """S56 item 3 (RED, T10+T1): restored nonterminal work cancels for restart.

    A nonterminal run (``inferring``) + queued job is seeded via direct
    SQL BEFORE the backup, so it is part of the staged archive; after
    commit the public GET /runs/{id} (fresh physician login, reads stay
    available under maintenance) must report the run AND its job as
    ``cancelled`` for explicit restart. Currently RED: slice 2 restores
    staged rows with their live statuses untouched.
    """
    nonce = uuid.uuid4().hex[:8]
    username = f"s56cdoc{nonce}"
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, username, f"s56-cancel-phys-{nonce}")
        login(physician, username, "secret", "physician")
        made = create_patient(physician, "0056000022", f"s56-cancel-patient-{nonce}")
        encounter_id = made["encounter"]["id"]
        patient_uuid = made["patient"]["id"]

        with db.transaction() as conn:
            author_id = (
                conn.execute(
                    text("SELECT id FROM users WHERE username = :u"),
                    {"u": username},
                )
                .mappings()
                .first()["id"]
            )
            run_id = (
                conn.execute(
                    text(
                        "INSERT INTO runs (encounter_id, author_id, patient_id, "
                        "encounter_revision, workflow, snapshot, snapshot_hash, "
                        "fingerprint, bundle_hash, pins, status) "
                        "VALUES (CAST(:eid AS uuid), CAST(:author AS uuid), "
                        "CAST(:pid AS uuid), 1, 'registration', "
                        "CAST(:snap AS jsonb), :sh, :fp, :bh, "
                        "CAST(:pins AS jsonb), 'inferring') RETURNING id"
                    ),
                    {
                        "eid": encounter_id,
                        "author": str(author_id),
                        "pid": patient_uuid,
                        "snap": json.dumps({"synthetic": True}),
                        "sh": f"s56snap-{nonce}",
                        "fp": f"s56fp-{nonce}",
                        "bh": f"s56bh-{nonce}",
                        "pins": json.dumps({}),
                    },
                )
                .mappings()
                .first()["id"]
            )
            conn.execute(
                text(
                    "INSERT INTO reasoning_jobs "
                    "(run_id, encounter_id, author_id, question_key, "
                    " ordinal, stage, status) "
                    "VALUES (CAST(:rid AS uuid), CAST(:eid AS uuid), "
                    " CAST(:author AS uuid), :qkey, 0, "
                    " 'estimating_cpts', 'queued')"
                ),
                {
                    "rid": str(run_id),
                    "eid": encounter_id,
                    "author": str(author_id),
                    "qkey": f"s56cancel-{nonce}",
                },
            )

        seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(
            admin, f"s56-cancel-backup-{nonce}"
        )
        staged = validate_archive(admin, archive_bytes, f"s56-cancel-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id, digest, _ = assert_staged_contract(staged.json())

        started = commit_restore(admin, restore_id, digest, f"s56-cancel-go-{nonce}")
        assert started.status_code in (200, 202), (
            f"commit must start, got {started.status_code}: {started.text[:300]!r}"
        )

        with TestClient(app) as physician_new:
            login(physician_new, username, "secret", "physician")
            reread = physician_new.get(f"/api/v1/runs/{run_id}")
            assert reread.status_code == 200, (
                f"restored run must stay readable, got {reread.status_code}: "
                f"{reread.text[:300]!r}"
            )
            body = reread.json()
            assert body["run"]["status"] == "cancelled", (
                f"restored nonterminal run must cancel for restart: {body['run']!r}"
            )
            assert body["jobs"], f"restored run must keep its job rows: {body!r}"
            assert body["jobs"][0]["status"] == "cancelled", (
                f"restored queued job must cancel for restart: "
                f"{body['jobs'][0]!r}"
            )


def test_restore_commit_audit_log_and_reopen_health():
    """S56 item 3 (RED, T10+T1): audit/log recorded, verified reads, reopen.

    After commit (fresh admin login, so this holds both before and after
    session revoke): GET /audit-events shows ``restore.commit`` naming
    the restore_id; the external operator recovery log (the T10 operator
    seam) carries a committed line for the restore_id; login/reads pass
    while maintenance stays fenced (GET /patients 200 with the staged
    patient, GET /restores/{id} committed, staged network XML hash
    traceable in the report, pre-restore backup manifest readable).
    Then explicit admin POST /restores/{id}/reopen returns 200 and
    writes work again (POST /patients 201). Currently RED: no reopen
    route exists (404) so post-reopen writes stay 503.
    """
    from x_insight.operations.restore import recovery_log_path

    nonce = uuid.uuid4().hex[:8]
    username = f"s56rdoc{nonce}"
    staged_pid = "0056000023"
    reopen_pid = "0056000024"
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, username, f"s56-reopen-phys-{nonce}")
        login(physician, username, "secret", "physician")
        create_patient(physician, staged_pid, f"s56-reopen-patient-{nonce}")

        xml_hash = seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(
            admin, f"s56-reopen-backup-{nonce}"
        )
        staged = validate_archive(admin, archive_bytes, f"s56-reopen-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id, digest, _ = assert_staged_contract(staged.json())

        started = commit_restore(admin, restore_id, digest, f"s56-reopen-go-{nonce}")
        assert started.status_code in (200, 202), (
            f"commit must start, got {started.status_code}: {started.text[:300]!r}"
        )
        pre_id = started.json().get("pre_restore_backup_id")
        assert isinstance(pre_id, str) and pre_id

        with TestClient(app) as admin_new, TestClient(app) as physician_new:
            login(admin_new)
            login(physician_new, username, "secret", "physician")

            audit = admin_new.get(
                "/api/v1/audit-events",
                params={"operation": "restore.commit", "limit": 100},
            )
            assert audit.status_code == 200, (
                f"audit list must stay readable, got {audit.status_code}: "
                f"{audit.text[:300]!r}"
            )
            items = audit.json()["items"]
            assert any(
                item.get("operation") == "restore.commit"
                and str(item.get("result_reference")) == str(restore_id)
                for item in items
            ), f"restore.commit audit must name the restore: {items!r}"

            log_text = Path(recovery_log_path()).read_text(encoding="utf-8")
            assert str(restore_id) in log_text and "committed" in log_text, (
                "operator recovery log must carry the committed restore line"
            )

            listed = admin_new.get("/api/v1/patients", params={"limit": 100})
            assert listed.status_code == 200
            assert staged_pid in listed.text, "staged patient must be readable"

            reread = admin_new.get(f"/api/v1/restores/{restore_id}")
            assert reread.status_code == 200
            assert reread.json()["status"] == "committed"
            files = reread.json()["report"].get("files", [])
            assert any(
                isinstance(entry, dict) and entry.get("sha256") == xml_hash
                for entry in files
            ), f"staged network XML hash must be traceable: {files!r}"

            pre = admin_new.get(f"/api/v1/backups/{pre_id}")
            assert pre.status_code == 200, (
                f"pre-restore backup manifest must be readable, got "
                f"{pre.status_code}: {pre.text[:300]!r}"
            )

            fenced = physician_new.post(
                "/api/v1/patients",
                json={
                    "first_name": "Anna",
                    "last_name": "Muller",
                    "sex": "F",
                    "age": 30,
                    "patient_id": reopen_pid,
                    "clinical_status": "first_time",
                },
                headers=admin_headers(physician_new, f"s56-reopen-fenced-{nonce}"),
            )
            assert fenced.status_code == 503, (
                "writes must stay fenced until explicit reopen, got "
                f"{fenced.status_code}: {fenced.text[:300]!r}"
            )

            reopen = admin_new.post(
                f"/api/v1/restores/{restore_id}/reopen",
                headers=admin_headers(admin_new, f"s56-reopen-key-{nonce}"),
            )
            assert reopen.status_code == 200, (
                f"explicit admin reopen must succeed, got {reopen.status_code}: "
                f"{reopen.text[:300]!r}"
            )
            assert str(reopen.json().get("restore_id")) == str(restore_id)

            after = physician_new.post(
                "/api/v1/patients",
                json={
                    "first_name": "Anna",
                    "last_name": "Muller",
                    "sex": "F",
                    "age": 30,
                    "patient_id": reopen_pid,
                    "clinical_status": "first_time",
                },
                headers=admin_headers(physician_new, f"s56-reopen-write-{nonce}"),
            )
            assert after.status_code == 201, (
                f"writes must work after reopen, got {after.status_code}: "
                f"{after.text[:300]!r}"
            )


# ---------------------------------------------------------------------------
# S56 item 4 (RED, slice 4): failure injection with rollback / held
# maintenance. Seams T10/T1. SYNTHETIC VALUES ONLY.
#
# Expected interface (NOT implemented -- restore.py reads none of these,
# so commits succeed despite the flags and every test below REDs):
# - Env-controlled injection points, armed when the value is "1":
#     X_INSIGHT_RESTORE_FAIL_BEFORE_SWITCH (raise after the pre-restore
#       backup, before the table switch),
#     X_INSIGHT_RESTORE_FAIL_DURING_RESTART (raise during the restart-signal
#       phase, after the switch),
#     X_INSIGHT_RESTORE_FAIL_AT_HEALTH (poison the verified-read health
#       check used by explicit reopen).
#   Because restore.py caches env values in module constants at import
#   (see the S55 oversized case), tests patch both the env var and the
#   same-suffix module-attr mirror (RESTORE_FAIL_*; created here with
#   raising=False since the implementation does not define them yet).
# - Rollback mechanism: restore the pre-restore backup archive (the
#   pre_restore_backup_id zip, readable via GET /backups/{id}) over the
#   live tables plus restore the pre-commit deployment generation; the
#   commit answers 503 (maintenance held, retryable), GET /restores/{id}
#   stays "staged" and exposes pre_restore_backup_id, maintenance stays
#   active (writes 503 MAINTENANCE, reads 200), reopen answers 503 until a
#   later healthy commit+reopen, and the external operator log carries an
#   outcome "rolled_back" line. Outcome vocabulary: "committed" /
#   "rolled_back" / "reopened".
# - Chosen semantic (documented per test): BEFORE_SWITCH and DURING_RESTART
#   failures roll back to the pre-restore backup (no switch survives); an
#   AT_HEALTH failure keeps the already-replaced tables + maintenance (no
#   auto-rollback) until a healthy reopen.
# All rollback assertions use public HTTP only (patients, login, restores,
# backups); the operator log file is the T10 operator seam already used in
# slice 3. No UI coverage (dev-frontend owns T9).
# ---------------------------------------------------------------------------

FAIL_BEFORE_SWITCH_ENV = "X_INSIGHT_RESTORE_FAIL_BEFORE_SWITCH"
FAIL_DURING_RESTART_ENV = "X_INSIGHT_RESTORE_FAIL_DURING_RESTART"
FAIL_AT_HEALTH_ENV = "X_INSIGHT_RESTORE_FAIL_AT_HEALTH"


def _arm_fail_flag(monkeypatch, env_name):
    """Arm an S56-slice-4 failure flag via env + module-attr mirror."""
    from x_insight.operations import restore as restore_ops

    monkeypatch.setenv(env_name, "1")
    monkeypatch.setattr(
        restore_ops, env_name.replace("X_INSIGHT_", ""), True, raising=False
    )


def _clear_fail_flag(monkeypatch, env_name):
    """Clear an S56-slice-4 failure flag via env + module-attr mirror."""
    from x_insight.operations import restore as restore_ops

    monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setattr(
        restore_ops, env_name.replace("X_INSIGHT_", ""), False, raising=False
    )


def reopen_restore(client, restore_id, key):
    return client.post(
        f"/api/v1/restores/{restore_id}/reopen",
        headers=admin_headers(client, key),
    )


def _new_patient_body(patient_id):
    return {
        "first_name": "Anna",
        "last_name": "Muller",
        "sex": "F",
        "age": 30,
        "patient_id": patient_id,
        "clinical_status": "first_time",
    }


def test_restore_commit_failure_before_switch_rolls_back(monkeypatch):
    """S56 item 4 (RED, T10+T1): FAIL_BEFORE_SWITCH rolls back, holds fence.

    Chosen semantic: a failure raised after the pre-restore backup but
    before the table switch restores the prior database/configuration
    (pre-restore backup archive over live tables + pre-commit
    generation), keeps maintenance active, and refuses reopen until a
    later healthy commit+reopen. No switch survives: live patients stay
    byte-identical (extra live patient still present, nothing replaced).
    Currently RED: restore.py ignores the flag, so the commit succeeds
    (202) instead of failing (503/500) with a rollback.
    """
    nonce = uuid.uuid4().hex[:8]
    username = f"s56bdoc{nonce}"
    staged_pid = "0056000031"
    extra_pid = "0056000032"
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, username, f"s56-bswitch-phys-{nonce}")
        login(physician, username, "secret", "physician")
        create_patient(physician, staged_pid, f"s56-bswitch-staged-{nonce}")

        seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(
            admin, f"s56-bswitch-backup-{nonce}"
        )
        # Live diverges AFTER the backup: extra patient is not in the archive.
        create_patient(physician, extra_pid, f"s56-bswitch-extra-{nonce}")

        staged = validate_archive(admin, archive_bytes, f"s56-bswitch-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id, digest, _ = assert_staged_contract(staged.json())
        before = live_patients_snapshot(admin)

        _arm_fail_flag(monkeypatch, FAIL_BEFORE_SWITCH_ENV)
        failed = commit_restore(admin, restore_id, digest, f"s56-bswitch-go-{nonce}")
        assert failed.status_code in (500, 503), (
            f"injected before-switch failure must fail 500/503 with rollback, "
            f"got {failed.status_code}: {failed.text[:500]!r}"
        )

        with TestClient(app) as admin_new, TestClient(app) as physician_new:
            login(admin_new)
            login(physician_new, username, "secret", "physician")

            # Rollback: live byte-identical via public HTTP (extra present,
            # no replacement survived).
            after = admin_new.get("/api/v1/patients", params={"limit": 100})
            assert after.status_code == 200
            assert after.content == before, "rollback must leave live unchanged"
            assert extra_pid in after.text, "extra live patient must survive"
            assert staged_pid in after.text, "pre-existing live patient must survive"

            # Restore row stays staged (never committed) and names the
            # pre-restore backup, readable via the public backup interface.
            reread = admin_new.get(f"/api/v1/restores/{restore_id}")
            assert reread.status_code == 200
            assert reread.json()["status"] == "staged", (
                f"rolled-back restore must read staged: {reread.text[:300]!r}"
            )
            pre_id = reread.json().get("pre_restore_backup_id")
            assert isinstance(pre_id, str) and pre_id, (
                f"rollback must expose its pre-restore backup: "
                f"{reread.text[:300]!r}"
            )
            pre = admin_new.get(f"/api/v1/backups/{pre_id}")
            assert pre.status_code == 200, (
                f"pre-restore backup must exist, got {pre.status_code}: "
                f"{pre.text[:300]!r}"
            )

            # Maintenance REMAINS active: reads 200, writes 503 MAINTENANCE.
            reads = admin_new.get("/api/v1/patients", params={"limit": 100})
            assert reads.status_code == 200
            fenced = physician_new.post(
                "/api/v1/patients",
                json=_new_patient_body("0056000033"),
                headers=admin_headers(physician_new, f"s56-bswitch-fenced-{nonce}"),
            )
            assert fenced.status_code == 503, (
                f"writes must stay fenced after rollback, got "
                f"{fenced.status_code}: {fenced.text[:300]!r}"
            )
            assert fenced.json().get("code") == "MAINTENANCE"

            # Explicit reopen FAILS 503 (target never verified healthy;
            # maintenance held) until a later healthy commit+reopen.
            reopen = reopen_restore(
                admin_new, restore_id, f"s56-bswitch-reopen-{nonce}"
            )
            assert reopen.status_code == 503, (
                f"reopen after rollback must be 503, got {reopen.status_code}: "
                f"{reopen.text[:300]!r}"
            )

        # Clearing the flag restores operability: a fresh validate+commit
        # succeeds, proving the rollback left configuration sane.
        _clear_fail_flag(monkeypatch, FAIL_BEFORE_SWITCH_ENV)
        with TestClient(app) as admin_new, TestClient(app) as physician_new:
            login(admin_new)
            login(physician_new, username, "secret", "physician")
            restaged = validate_archive(
                admin_new, archive_bytes, f"s56-bswitch-reval-{nonce}"
            )
            assert restaged.status_code in (200, 202)
            rid2, digest2, _ = assert_staged_contract(restaged.json())
            retried = commit_restore(
                admin_new, rid2, digest2, f"s56-bswitch-retry-{nonce}"
            )
            assert retried.status_code in (200, 202), (
                f"commit after clearing the flag must succeed, got "
                f"{retried.status_code}: {retried.text[:300]!r}"
            )
            assert retried.json()["status"] in ("committing", "committed")


def test_restore_commit_failure_during_restart_rolls_back(monkeypatch):
    """S56 item 4 (RED, T10+T1): FAIL_DURING_RESTART rolls back + logs it.

    Chosen semantic: same as BEFORE_SWITCH -- a failure during the
    restart-signal phase rolls back to the pre-restore backup (prior
    database/configuration), holds maintenance, refuses reopen with 503,
    and appends an outcome "rolled_back" operator-log line naming the
    restore. Currently RED: restore.py ignores the flag, so the commit
    succeeds (202, outcome "committed") instead of failing with rollback.
    """
    from x_insight.operations.restore import recovery_log_path

    nonce = uuid.uuid4().hex[:8]
    username = f"s56rdoc{nonce}"
    staged_pid = "0056000035"
    extra_pid = "0056000036"
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, username, f"s56-drestart-phys-{nonce}")
        login(physician, username, "secret", "physician")
        create_patient(physician, staged_pid, f"s56-drestart-staged-{nonce}")

        seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(
            admin, f"s56-drestart-backup-{nonce}"
        )
        create_patient(physician, extra_pid, f"s56-drestart-extra-{nonce}")

        staged = validate_archive(admin, archive_bytes, f"s56-drestart-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id, digest, _ = assert_staged_contract(staged.json())
        before = live_patients_snapshot(admin)

        _arm_fail_flag(monkeypatch, FAIL_DURING_RESTART_ENV)
        failed = commit_restore(admin, restore_id, digest, f"s56-drestart-go-{nonce}")
        assert failed.status_code in (500, 503), (
            f"injected restart failure must fail 500/503 with rollback, "
            f"got {failed.status_code}: {failed.text[:500]!r}"
        )

        with TestClient(app) as admin_new, TestClient(app) as physician_new:
            login(admin_new)
            login(physician_new, username, "secret", "physician")

            after = admin_new.get("/api/v1/patients", params={"limit": 100})
            assert after.status_code == 200
            assert after.content == before, "rollback must leave live unchanged"
            assert extra_pid in after.text, "extra live patient must survive"

            reread = admin_new.get(f"/api/v1/restores/{restore_id}")
            assert reread.status_code == 200
            assert reread.json()["status"] == "staged", (
                f"rolled-back restore must read staged: {reread.text[:300]!r}"
            )
            pre_id = reread.json().get("pre_restore_backup_id")
            assert isinstance(pre_id, str) and pre_id, (
                f"rollback must expose its pre-restore backup: "
                f"{reread.text[:300]!r}"
            )
            pre = admin_new.get(f"/api/v1/backups/{pre_id}")
            assert pre.status_code == 200

            log_text = Path(recovery_log_path()).read_text(encoding="utf-8")
            assert str(restore_id) in log_text and "rolled_back" in log_text, (
                "operator recovery log must carry the rolled_back restore line"
            )

            reads = admin_new.get("/api/v1/patients", params={"limit": 100})
            assert reads.status_code == 200
            fenced = physician_new.post(
                "/api/v1/patients",
                json=_new_patient_body("0056000044"),
                headers=admin_headers(physician_new, f"s56-drestart-fenced-{nonce}"),
            )
            assert fenced.status_code == 503
            assert fenced.json().get("code") == "MAINTENANCE"

            reopen = reopen_restore(
                admin_new, restore_id, f"s56-drestart-reopen-{nonce}"
            )
            assert reopen.status_code == 503, (
                f"reopen after rollback must be 503, got {reopen.status_code}: "
                f"{reopen.text[:300]!r}"
            )

        _clear_fail_flag(monkeypatch, FAIL_DURING_RESTART_ENV)
        with TestClient(app) as admin_new:
            login(admin_new)
            restaged = validate_archive(
                admin_new, archive_bytes, f"s56-drestart-reval-{nonce}"
            )
            assert restaged.status_code in (200, 202)
            rid2, digest2, _ = assert_staged_contract(restaged.json())
            retried = commit_restore(
                admin_new, rid2, digest2, f"s56-drestart-retry-{nonce}"
            )
            assert retried.status_code in (200, 202), (
                f"commit after clearing the flag must succeed, got "
                f"{retried.status_code}: {retried.text[:300]!r}"
            )


def test_restore_commit_failure_at_health_keeps_maintenance(monkeypatch):
    """S56 item 4 (RED, T10+T1): FAIL_AT_HEALTH holds fence without rollback.

    Chosen semantic (differs from switch/restart failures by design): the
    commit itself succeeds and the staged tables DO replace live (extra
    live patient gone, staged patient present, GET restores "committed"),
    but the poisoned verified-read health check refuses explicit reopen
    (503, maintenance stays: writes 503 MAINTENANCE, reads 200) -- no
    auto-rollback, since the replaced state is the validated staged
    content. After clearing the flag, reopen returns 200, writes work
    again (201), and the staged data stays readable. Currently RED:
    restore.py ignores the flag, so reopen succeeds (200) instead of 503.
    """
    nonce = uuid.uuid4().hex[:8]
    username = f"s56hdoc{nonce}"
    staged_pid = "0056000037"
    extra_pid = "0056000038"
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, username, f"s56-athealth-phys-{nonce}")
        login(physician, username, "secret", "physician")
        create_patient(physician, staged_pid, f"s56-athealth-staged-{nonce}")

        seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(
            admin, f"s56-athealth-backup-{nonce}"
        )
        create_patient(physician, extra_pid, f"s56-athealth-extra-{nonce}")

        staged = validate_archive(admin, archive_bytes, f"s56-athealth-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id, digest, _ = assert_staged_contract(staged.json())

        _arm_fail_flag(monkeypatch, FAIL_AT_HEALTH_ENV)
        started = commit_restore(admin, restore_id, digest, f"s56-athealth-go-{nonce}")
        assert started.status_code in (200, 202), (
            f"commit with only the health flag armed must still commit, got "
            f"{started.status_code}: {started.text[:300]!r}"
        )
        assert started.json()["status"] in ("committing", "committed")

        with TestClient(app) as admin_new, TestClient(app) as physician_new:
            login(admin_new)
            login(physician_new, username, "secret", "physician")

            # No rollback at the health stage: replaced state survives.
            listed = admin_new.get("/api/v1/patients", params={"limit": 100})
            assert listed.status_code == 200
            ids = [item["patient_id"] for item in listed.json()["items"]]
            assert staged_pid in ids, f"staged patient must be live: {ids!r}"
            assert extra_pid not in ids, (
                f"replacement, never merge: extra live patient must be gone: "
                f"{ids!r}"
            )
            reread = admin_new.get(f"/api/v1/restores/{restore_id}")
            assert reread.status_code == 200
            assert reread.json()["status"] == "committed"

            # But reopen is refused: health fails, maintenance stays.
            reopen = reopen_restore(
                admin_new, restore_id, f"s56-athealth-reopen-{nonce}"
            )
            assert reopen.status_code == 503, (
                f"reopen with poisoned health must be 503, got "
                f"{reopen.status_code}: {reopen.text[:300]!r}"
            )
            reads = admin_new.get("/api/v1/patients", params={"limit": 100})
            assert reads.status_code == 200
            fenced = physician_new.post(
                "/api/v1/patients",
                json=_new_patient_body("0056000046"),
                headers=admin_headers(physician_new, f"s56-athealth-fenced-{nonce}"),
            )
            assert fenced.status_code == 503
            assert fenced.json().get("code") == "MAINTENANCE"

        # Clearing the flag heals the target: reopen 200, writes 201, and
        # the staged (replaced) data stays readable -- rollback NOT needed.
        _clear_fail_flag(monkeypatch, FAIL_AT_HEALTH_ENV)
        with TestClient(app) as admin_new, TestClient(app) as physician_new:
            login(admin_new)
            login(physician_new, username, "secret", "physician")
            reopened = reopen_restore(
                admin_new, restore_id, f"s56-athealth-reopen2-{nonce}"
            )
            assert reopened.status_code == 200, (
                f"reopen after clearing the flag must succeed, got "
                f"{reopened.status_code}: {reopened.text[:300]!r}"
            )
            assert str(reopened.json().get("restore_id")) == str(restore_id)
            written = physician_new.post(
                "/api/v1/patients",
                json=_new_patient_body("0056000049"),
                headers=admin_headers(physician_new, f"s56-athealth-write-{nonce}"),
            )
            assert written.status_code == 201, (
                f"writes must work after healthy reopen, got "
                f"{written.status_code}: {written.text[:300]!r}"
            )
            readable = admin_new.get("/api/v1/patients", params={"limit": 100})
            assert readable.status_code == 200
            assert staged_pid in readable.text, "staged data must stay readable"

