"""S54 slice 1 (RED): consistent full backup over a populated system.

Scope: docs/dev/plan.md 10.2, docs/dev/tasks.md S54 item 1;
seams T10 (backup commands / HTTP backup interface) + T1 (authenticated
HTTP vs real PostgreSQL). SYNTHETIC VALUES ONLY.

Behavior under test (NOT implemented -- RED, expect 404 on POST
/api/v1/backups since no backup code exists):
- Admin POST /api/v1/backups -> 202 with a job id.
- Polling GET /api/v1/backups/{id} eventually shows succeeded.
- GET /api/v1/backups/{id}/download returns a zip archive whose
  manifest.json lists: database snapshot, original + effective XML
  artifacts, accepted CPTs, prompts/templates, content/DDI provenance,
  per-file sha256 checksums, schema/app versions, timestamp, backup
  identity.
- The manifest covers at least: patients/encounters rows, one network
  original XML hash, one DDI dataset version, one provider-config
  revision reference.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_backup():
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, runs, run_questions, reasoning_jobs, "
                "reasoning_attempts, run_question_artifacts, run_proposals, "
                "audit_events, model_bundle_pointers, model_bundle_events, "
                "mcp_question_grants, provider_configs, "
                "provider_config_pointer, queue_fairness, ddi_dataset_releases, "
                "networks, network_versions"
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
    b"<?xml version=\"1.0\"?>"
    b"<BIF VERSION=\"0.3\"><NETWORK><NAME>s54</NAME></NETWORK></BIF>"
)


def seed_content_fixture():
    """Direct-SQL fixture setup (disposable storage init; assertions use T10).

    Seeds one network original XML (+ effective bytes recorded alongside),
    one DDI dataset release, and one provider-config revision so the slice-1
    manifest has representative content to cover.
    """
    xml_hash = hashlib.sha256(SYNTHETIC_XML).hexdigest()
    with db.transaction() as conn:
        network_id = (
            conn.execute(
                text("INSERT INTO networks(key) VALUES (:k) RETURNING id"),
                {"k": "s54-test-network"},
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
                "v": "s54-synthetic-ddi-v1",
                "h": hashlib.sha256(b"s54-ddi").hexdigest(),
                "inv": json.dumps({"synthetic": True, "documents": 0}),
                "rev": json.dumps({"decision": "approved", "synthetic": True}),
            },
        )
    return xml_hash


def test_backup_full_archive_manifest():
    """S54 item 1 (RED): backup zip manifest covers DB/XML/DDI/config (T10)."""
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "backupdoc", "s54-backup-create")
        login(physician, "backupdoc", "secret", "physician")
        made = create_patient(physician, "0054000001", "s54-backup-patient")
        patient_uuid = made["patient"]["id"]

        xml_hash = seed_content_fixture()

        started = admin.post(
            "/api/v1/backups",
            json={},
            headers=admin_headers(admin, "s54-backup-start"),
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
        assert status == "succeeded"

        downloaded = admin.get(f"/api/v1/backups/{job_id}/download")
        assert downloaded.status_code == 200
        assert "zip" in downloaded.headers.get("content-type", "").lower()

        archive = zipfile.ZipFile(io.BytesIO(downloaded.content))
        manifest = json.loads(archive.read("manifest.json"))

        for field in (
            "timestamp",
            "backup_id",
            "schema_version",
            "app_version",
            "files",
        ):
            assert field in manifest, f"manifest missing {field!r}"
        assert isinstance(manifest["files"], list) and manifest["files"]
        for entry in manifest["files"]:
            assert "path" in entry and "sha256" in entry

        blob = json.dumps(manifest).lower()
        assert str(patient_uuid).lower() in blob  # patients/encounters rows
        assert xml_hash.lower() in blob  # network original XML hash
        assert "s54-synthetic-ddi-v1" in blob  # DDI dataset version
        assert "provider" in blob and "1" in blob  # provider-config revision


def test_backup_concurrent_mutation_snapshot_coherent():
    """S54 item 2: concurrent mutation cannot mix the backup snapshot (T10).

    Starts a backup job, and WHILE the build is in flight mutates the
    disposable system through public HTTP (physician creates another
    patient, which atomically adds a patient + registration encounter +
    audit row). The finished archive must be INTERNALLY coherent -- every
    sha256 matches, row counts match the manifest inventory, exported
    network XML bytes match the row dump -- and must reflect ONE snapshot
    (pre- or post-mutation throughout, never a mix: no dangling
    encounter.patient references; the mutated patient and its registration
    encounter are either both present or both absent).

    Overlap is forced deterministically: a moderately large synthetic
    network XML seeded via direct-SQL fixture setup stretches the build to
    ~1s while the concurrent HTTP mutation takes ~0.1s; the mutator runs
    on a second TestClient in a thread. A probe (status samples taken while
    the mutation is committed) fails RED with a clear message when no
    overlap occurred, so the test can never pass vacuously.
    SYNTHETIC VALUES ONLY.
    """
    import base64
    import os
    import threading

    RACE_PATIENT = "0054000012"

    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "backuprace", "s54-race-create")
        login(physician, "backuprace", "secret", "physician")
        baseline = create_patient(physician, "0054000011", "s54-race-baseline")
        baseline_uuid = baseline["patient"]["id"]

        # Direct-SQL seeding only: one large synthetic network XML slows the
        # archive build (~1s) so the concurrent mutation lands mid-build.
        big_xml = os.urandom(16_000_000)
        big_hash = hashlib.sha256(big_xml).hexdigest()
        with db.transaction() as conn:
            network_id = (
                conn.execute(
                    text("INSERT INTO networks(key) VALUES (:k) RETURNING id"),
                    {"k": "s54-race-network"},
                )
                .mappings()
                .first()["id"]
            )
            conn.execute(
                text(
                    "INSERT INTO network_versions "
                    "(network_id, version, xml, sha256, byte_count, "
                    "xsd_report, semantic_report, admission_report) "
                    "VALUES (:nid, 1, :xml, :sha, :n, "
                    "CAST(:rep AS jsonb), CAST(:rep AS jsonb), "
                    "CAST(:rep AS jsonb))"
                ),
                {
                    "nid": str(network_id),
                    "xml": big_xml,
                    "sha": big_hash,
                    "n": len(big_xml),
                    "rep": json.dumps({"synthetic": True}),
                },
            )

        started = admin.post(
            "/api/v1/backups",
            json={},
            headers=admin_headers(admin, "s54-race-start"),
        )
        assert started.status_code == 202
        job_id = started.json()["job_id"]

        mutation: dict = {}

        def _mutate() -> None:
            try:
                mutation["started_at"] = time.monotonic()
                response = physician.post(
                    "/api/v1/patients",
                    json={
                        "first_name": "Anna",
                        "last_name": "Muller",
                        "sex": "F",
                        "age": 30,
                        "patient_id": RACE_PATIENT,
                        "clinical_status": "first_time",
                    },
                    headers=admin_headers(physician, "s54-race-mutate"),
                )
                mutation["finished_at"] = time.monotonic()
                mutation["status"] = response.status_code
                if response.status_code == 201:
                    body = response.json()
                    mutation["patient_uuid"] = body["patient"]["id"]
                    mutation["encounter_id"] = body["encounter"]["id"]
                else:
                    mutation["body"] = response.text[:500]
            except Exception as exc:  # re-raised in the main thread
                mutation["finished_at"] = time.monotonic()
                mutation["error"] = repr(exc)

        worker = threading.Thread(target=_mutate, daemon=True)
        worker.start()

        samples: list = []
        status = None
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            polled = admin.get(f"/api/v1/backups/{job_id}")
            assert polled.status_code == 200
            status = polled.json()["status"]
            samples.append((time.monotonic(), status))
            if status == "succeeded":
                break
            assert status in ("queued", "running")
            time.sleep(0.05)
        worker.join(timeout=60)
        assert not worker.is_alive(), "mutator thread hung"

        assert mutation.get("status") == 201, (
            f"concurrent public-HTTP mutation failed: {mutation}"
        )
        assert status == "succeeded", f"backup job did not succeed: {status}"
        done_at = mutation["finished_at"]
        if not any(
            sample_status in ("queued", "running") and sample_at >= done_at
            for sample_at, sample_status in samples
        ):
            pytest.fail("no overlap observed — slice 2 not exercised")

        downloaded = admin.get(f"/api/v1/backups/{job_id}/download")
        assert downloaded.status_code == 200
        archive = zipfile.ZipFile(io.BytesIO(downloaded.content))
        manifest = json.loads(archive.read("manifest.json"))

        # 1. Every manifest sha256 matches the actual zip entry bytes.
        assert isinstance(manifest["files"], list) and manifest["files"]
        for entry in manifest["files"]:
            payload = archive.read(entry["path"])
            assert hashlib.sha256(payload).hexdigest() == entry["sha256"], (
                entry["path"]
            )
            assert len(payload) == entry["bytes"], entry["path"]

        # 2. database/<table>.json row counts and bytes match the inventory.
        assert isinstance(manifest["tables"], dict) and manifest["tables"]
        dumped: dict = {}
        for table, inventory in manifest["tables"].items():
            payload = archive.read(f"database/{table}.json")
            assert hashlib.sha256(payload).hexdigest() == inventory["sha256"], (
                table
            )
            rows = json.loads(payload)
            assert len(rows) == inventory["rows"], table
            dumped[table] = rows

        # 3. Exported network XML bytes hash-match the manifest and the dump.
        network_rows = {row["id"]: row for row in dumped["network_versions"]}
        assert big_hash in {
            row.get("sha256") for row in dumped["network_versions"]
        }
        artifact_paths = [
            entry["path"]
            for entry in manifest["files"]
            if entry["path"].startswith("artifacts/networks/")
        ]
        assert artifact_paths, "network artifacts missing from manifest"
        for path in artifact_paths:
            raw = archive.read(path)
            version_id = path.rsplit("/", 1)[1].removesuffix(".xml")
            assert version_id in network_rows, path
            stored = network_rows[version_id]["xml"]
            assert isinstance(stored, dict) and "base64" in stored
            assert base64.b64decode(stored["base64"]) == raw

        # 4. No dangling references: one consistent snapshot, never a mix.
        patient_ids = {row["id"] for row in dumped["patients"]}
        dumped_texts = {row["patient_id_text"] for row in dumped["patients"]}
        assert "0054000011" in dumped_texts  # baseline always present
        assert str(baseline_uuid).lower() in {
            pid.lower() for pid in patient_ids
        }
        encounter_rows = dumped["encounters"]
        assert encounter_rows, "registration encounters missing from dump"
        for encounter in encounter_rows:
            assert encounter["patient_id"] in patient_ids, (
                f"dangling encounter.patient reference: {encounter['id']}"
            )
        for note in dumped.get("encounter_notes", []):
            assert note["encounter_id"] in {
                encounter["id"] for encounter in encounter_rows
            }, f"dangling note.encounter reference: {note['id']}"

        # 5. The backup is wholly pre- or post-mutation: the concurrently
        # created patient and its registration encounter are both present
        # or both absent -- never exactly one of the two.
        mutated_uuid = mutation["patient_uuid"]
        mutated_present = RACE_PATIENT in dumped_texts
        if mutated_present:
            assert mutated_uuid in patient_ids
            assert any(
                encounter["patient_id"] == mutated_uuid
                for encounter in encounter_rows
            ), "post-mutation snapshot lacks the registration encounter"
        else:
            assert mutated_uuid not in patient_ids
            assert all(
                encounter["patient_id"] != mutated_uuid
                for encounter in encounter_rows
            ), "pre-mutation snapshot mixes in the concurrent encounter"


def test_backup_exclusions_auth_audit(monkeypatch):
    """S54 item 3: secrets excluded, ciphertext kept + re-entry note, auth,
    progress, audit (T10+T1). SYNTHETIC VALUES ONLY.

    - Deployment key sentinel via X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY;
      provider config saved WITH an API key through admin PUT /api-settings
      so key_ciphertext exists in the DB.
    - Active admin + physician sessions keep the sessions table non-empty.
    - Backup zip: sentinel nowhere, no session token/hash anywhere,
      key_ciphertext present by design, manifest has a key-reentry note.
    - Auth matrix on POST /backups, GET /backups/{id}, GET download:
      anonymous 401, physician 403, admin success; download is
      Cache-Control: private, no-store.
    - Progress: poll from creation; non-terminal seen OR terminal
      succeeded with manifest summary + completed_at (DB) present.
    - Audit: admin sees backup.create + backup.download events referencing
      the job id, with no secret values in payloads.
    """
    import uuid

    sentinel = f"s54-sentinel-key-{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY", sentinel)
    api_key = "synthetic-s54-slice3-api-key-001"

    with (
        TestClient(app) as admin,
        TestClient(app) as physician,
        TestClient(app) as anon,
    ):
        login(admin)
        create_physician(admin, "backupexcl", "s54-excl-create")
        login(physician, "backupexcl", "secret", "physician")

        saved = admin.put(
            "/api/v1/api-settings",
            json={
                "base_url": "https://provider.example/v1",
                "model": "synthetic-s54-slice3",
                "key_action": "replace",
                "api_key": api_key,
            },
            headers={"X-CSRF-Token": admin.cookies.get("xinsight_csrf")},
        )
        assert saved.status_code == 200, saved.text

        with db.transaction() as conn:
            rows = conn.execute(
                text("SELECT key_ciphertext FROM provider_configs")
            ).all()
        ciphertexts = [row[0] for row in rows if row[0]]
        assert ciphertexts, "provider key_ciphertext missing after save"
        ciphertext = str(ciphertexts[-1])
        # Non-vacuity 1: the sentinel key was active during the build --
        # the stored ciphertext decrypts to the synthetic API key only
        # with this deployment key set.
        from x_insight.reasoning.provider_config import decrypt_api_key

        assert decrypt_api_key(ciphertext) == api_key

        with db.transaction() as conn:
            session_count = conn.execute(
                text("SELECT count(*) FROM sessions")
            ).scalar()
            token_hashes = [
                row[0]
                for row in conn.execute(text("SELECT token_hash FROM sessions")).all()
            ]
            csrf_values = [
                row[0]
                for row in conn.execute(text("SELECT csrf_token FROM sessions")).all()
            ]
        # Non-vacuity 2: sessions table really was non-empty at backup time.
        assert session_count is not None and int(session_count) >= 2
        assert len(token_hashes) >= 2 and all(token_hashes)
        raw_tokens = [
            client.cookies.get("xinsight_session")
            for client in (admin, physician)
        ]
        raw_tokens = [token for token in raw_tokens if token]

        # Auth matrix on POST before the admin creates the job.
        anon_post = anon.post(
            "/api/v1/backups",
            json={},
            headers={"Idempotency-Key": "s54-excl-anon"},
        )
        assert anon_post.status_code == 401
        phys_post = physician.post(
            "/api/v1/backups",
            json={},
            headers=admin_headers(physician, "s54-excl-phys"),
        )
        assert phys_post.status_code == 403

        started = admin.post(
            "/api/v1/backups",
            json={},
            headers=admin_headers(admin, "s54-excl-start"),
        )
        assert started.status_code == 202
        job_id = started.json()["job_id"]

        seen: list = []
        status = None
        for _ in range(60):
            polled = admin.get(f"/api/v1/backups/{job_id}")
            assert polled.status_code == 200
            status = polled.json()["status"]
            seen.append(status)
            if status == "succeeded":
                break
            assert status in ("queued", "running")
            time.sleep(0.5)
        assert status == "succeeded", f"backup job did not succeed: {status}"
        saw_nonterminal = any(item in ("queued", "running") for item in seen)

        final_get = admin.get(f"/api/v1/backups/{job_id}")
        assert final_get.status_code == 200
        final_body = final_get.json()
        assert final_body["status"] == "succeeded"
        assert isinstance(final_body.get("manifest"), dict)
        assert final_body["manifest"].get("files")
        if not saw_nonterminal:
            with db.transaction() as conn:
                completed_at = conn.execute(
                    text(
                        "SELECT completed_at FROM recovery_jobs "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {"id": job_id},
                ).scalar()
            assert completed_at is not None

        assert anon.get(f"/api/v1/backups/{job_id}").status_code == 401
        assert physician.get(f"/api/v1/backups/{job_id}").status_code == 403
        assert anon.get(f"/api/v1/backups/{job_id}/download").status_code == 401
        assert (
            physician.get(f"/api/v1/backups/{job_id}/download").status_code == 403
        )

        downloaded = admin.get(f"/api/v1/backups/{job_id}/download")
        assert downloaded.status_code == 200
        assert (
            downloaded.headers.get("cache-control") == "private, no-store"
        ), downloaded.headers.get("cache-control")
        assert "zip" in downloaded.headers.get("content-type", "").lower()

        archive = zipfile.ZipFile(io.BytesIO(downloaded.content))
        names = archive.namelist()
        assert "manifest.json" in names
        assert "database/sessions.json" not in names
        blob = b"".join(archive.read(name) for name in names)

        assert sentinel.encode() not in blob
        for forbidden in token_hashes:
            assert str(forbidden).encode() not in blob
        for forbidden in [value for value in csrf_values if value]:
            assert str(forbidden).encode() not in blob
        for forbidden in raw_tokens:
            assert str(forbidden).encode() not in blob
        assert ciphertext.encode() in blob
        assert api_key.encode() not in blob

        manifest = json.loads(archive.read("manifest.json"))
        note = str(manifest.get("key_reentry_note", ""))
        assert "X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY" in note
        assert "re-entry" in note.lower() or "reentry" in note.lower()

        for operation in ("backup.create", "backup.download"):
            listed = admin.get(
                "/api/v1/audit-events",
                params={"operation": operation, "limit": 100},
            )
            assert listed.status_code == 200
            items = listed.json()["items"]
            assert any(
                item.get("result_reference") == job_id for item in items
            ), f"missing {operation} audit event for {job_id}"
        audit_text = json.dumps(
            admin.get(
                "/api/v1/audit-events", params={"limit": 100}
            ).json()
        )
        assert sentinel not in audit_text
        assert api_key not in audit_text
        assert ciphertext not in audit_text


def test_backup_interrupted_build_fails_clean(monkeypatch, tmp_path):
    """S54 item 4: interrupted build fails clean; retry keeps priors (T10).

    Black-box + OS-level fault only (no app-function patching, no private
    imports): staging is steered exclusively through the X_INSIGHT_BACKUP_DIR
    environment value, and the interruption is a filesystem fault (staging
    path under a regular file, so directory creation must fail even as
    root). SYNTHETIC VALUES ONLY.

    - Job A (good dir) succeeds; its download bytes + sha256 are kept.
    - Job B (faulted dir) must reach terminal ``failed`` with an error
      message, and its download must be 409 (never a complete archive).
    - No ``*job-B*`` file and no ``*.partial`` file may remain anywhere
      under the test staging area; the good dir still holds job A's
      archive.
    - Job C (good dir restored) succeeds, downloads fine, and job A still
      downloads byte-identical content (retry never overwrote job A).
    """
    import hashlib
    import os
    import time

    good_dir = tmp_path / "backups-good"
    good_dir.mkdir()
    monkeypatch.setenv("X_INSIGHT_BACKUP_DIR", str(good_dir))

    def _start_backup(client, key):
        started = client.post(
            "/api/v1/backups", json={}, headers=admin_headers(client, key)
        )
        assert started.status_code == 202
        return started.json()["job_id"]

    def _poll_terminal(client, job_id, timeout_s=30.0):
        deadline = time.monotonic() + timeout_s
        status = None
        body: dict = {}
        while time.monotonic() < deadline:
            polled = client.get(f"/api/v1/backups/{job_id}")
            assert polled.status_code == 200
            body = polled.json()
            status = body["status"]
            if status in ("succeeded", "failed"):
                return status, body
            assert status in ("queued", "running")
            time.sleep(0.1)
        raise AssertionError(
            f"backup job {job_id} never reached a terminal state "
            f"(last status={status!r})"
        )

    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "backupclean", "s54-clean-create")
        login(physician, "backupclean", "secret", "physician")
        create_patient(physician, "0054000041", "s54-clean-patient")

        # 1. GOOD backup A.
        job_a = _start_backup(admin, "s54-clean-a")
        status_a, _ = _poll_terminal(admin, job_a)
        assert status_a == "succeeded", f"good backup A failed: {status_a!r}"
        download_a1 = admin.get(f"/api/v1/backups/{job_a}/download")
        assert download_a1.status_code == 200
        sha_a1 = hashlib.sha256(download_a1.content).hexdigest()

        # 2. INTERRUPTED build B: staging path under a regular file, so
        # archive creation must fail at the OS level (root-safe fault).
        blocker = tmp_path / "blocker"
        blocker.write_bytes(b"s54-slice4-blocker")
        fault_staging = str(blocker / "unwritable-subdir")
        monkeypatch.setenv("X_INSIGHT_BACKUP_DIR", fault_staging)
        job_b = _start_backup(admin, "s54-clean-b")
        status_b, body_b = _poll_terminal(admin, job_b)
        assert status_b == "failed", (
            f"interrupted build did not fail: status={status_b!r} body={body_b!r}"
        )
        assert body_b.get("error"), "failed job must carry an error message"
        print(f"FAULT TRIGGERED: job_b status={status_b} error={body_b.get('error')!r}")
        download_b = admin.get(f"/api/v1/backups/{job_b}/download")
        assert download_b.status_code == 409

        # 3. No leftover complete-or-partial archive for the failed job.
        good_entries = sorted(os.listdir(str(good_dir)))
        print(f"GOOD DIR LISTING: {good_entries}")
        assert any(job_a in name for name in good_entries), (
            f"good job A archive missing: {good_entries}"
        )
        assert not any(job_b in name for name in good_entries), (
            f"failed job B left an archive: {good_entries}"
        )
        assert not any(name.endswith(".partial") for name in good_entries), (
            f"partial file left in good dir: {good_entries}"
        )
        assert not os.path.exists(fault_staging)
        leftovers = [str(path) for path in tmp_path.rglob(f"*{job_b}*")]
        assert leftovers == [], f"failed-job leftovers on disk: {leftovers}"

        # 4. RETRY with a working staging dir: new job C succeeds, and job
        # A still downloads byte-identical content.
        monkeypatch.setenv("X_INSIGHT_BACKUP_DIR", str(good_dir))
        job_c = _start_backup(admin, "s54-clean-c")
        status_c, _ = _poll_terminal(admin, job_c)
        assert status_c == "succeeded", f"retry backup C failed: {status_c!r}"
        download_c = admin.get(f"/api/v1/backups/{job_c}/download")
        assert download_c.status_code == 200
        assert zipfile.ZipFile(io.BytesIO(download_c.content)).namelist()
        download_a2 = admin.get(f"/api/v1/backups/{job_a}/download")
        assert download_a2.status_code == 200
        assert hashlib.sha256(download_a2.content).hexdigest() == sha_a1, (
            "retry overwrote the good prior backup A"
        )
