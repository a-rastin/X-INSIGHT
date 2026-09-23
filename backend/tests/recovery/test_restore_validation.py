"""S55 slice 1 (RED): valid archive stages into isolated staging + live unchanged.

Scope: docs/dev/tasks.md S55 item 1; plan.md 10.3;
seams T10 (restore validate/staging interface) + T1 (authenticated HTTP
vs real PostgreSQL). SYNTHETIC VALUES ONLY.

Behavior under test (NOT implemented -- RED, expect 404 on POST
/api/v1/restores/validate since no restore code exists):
- Valid app-generated backup archive (built via POST /api/v1/backups over
  a populated disposable system, then downloaded) posted as multipart
  file upload (field "archive") to POST /api/v1/restores/validate
  stages into isolated staging and reports backup date/schema/content/
  checksums/impact plus an immutable confirmation digest.
- GET /api/v1/restores/{id} returns the same digest + report, staged.
- Live-side reads through public HTTP show live state unchanged.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all
from x_insight.operations import restore as restore_ops


@pytest.fixture(autouse=True)
def clean_restore_validation():
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
    b'<?xml version="1.0"?><BIF VERSION="0.3"><NETWORK><NAME>s55</NAME></NETWORK></BIF>'
)


def seed_content_fixture():
    """Direct-SQL fixture setup (disposable storage init; assertions use T10/T1).

    Seeds one network_versions row, one ddi_dataset_releases row, and one
    provider_configs row so the S54 backup archive has representative
    content whose row counts/checksums the S55 validation report must echo.
    """
    xml_hash = hashlib.sha256(SYNTHETIC_XML).hexdigest()
    with db.transaction() as conn:
        network_id = (
            conn.execute(
                text("INSERT INTO networks(key) VALUES (:k) RETURNING id"),
                {"k": "s55-test-network"},
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
                "v": "s55-synthetic-ddi-v1",
                "h": hashlib.sha256(b"s55-ddi").hexdigest(),
                "inv": json.dumps({"synthetic": True, "documents": 0}),
                "rev": json.dumps({"decision": "approved", "synthetic": True}),
            },
        )
    return xml_hash


def build_populated_backup_archive(admin):
    """Create + poll an S54 backup job, return (job_id, zip bytes)."""
    started = admin.post(
        "/api/v1/backups",
        json={},
        headers=admin_headers(admin, "s55-backup-start"),
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


def validate_archive(admin, archive_bytes, key="s55-validate"):
    return admin.post(
        "/api/v1/restores/validate",
        files=[
            ("archive", ("backup.zip", io.BytesIO(archive_bytes), "application/zip"))
        ],
        headers=admin_headers(admin, key),
    )


def assert_staged_contract(body):
    """FUTURE contract for a staged validation (S55 item 1)."""
    assert body["status"] == "staged"
    restore_id = body.get("restore_id", body.get("job_id", body.get("id")))
    assert restore_id, f"missing restore/job id: {body!r}"
    assert "schema_version" in body
    digest = body.get("confirmation_digest")
    assert isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), (
        f"confirmation_digest must be 64-hex sha256: {digest!r}"
    )
    report = body.get("report")
    assert isinstance(report, dict), f"missing report: {body!r}"
    for field in (
        "backup_id",
        "backup_timestamp",
        "db_schema_revision",
        "app_version",
        "archive_sha256",
        "tables",
        "files",
        "impact",
        "key_reentry_note",
    ):
        assert field in report, f"report missing {field!r}"
    assert isinstance(report["tables"], dict) and report["tables"]
    assert isinstance(report["files"], list) and report["files"]
    for entry in report["files"]:
        assert "path" in entry and "sha256" in entry and "bytes" in entry
    impact = report["impact"]
    assert "live" in impact and "staged" in impact
    assert "patients" in impact["live"] and "patients" in impact["staged"]
    assert report["key_reentry_note"], "key-reentry note must be non-empty"
    return restore_id, digest, report


def test_restore_validate_stages_report_and_digest():
    """S55 item 1 (RED): valid archive stages; GET restores/{id} echoes it (T10)."""
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "restoredoc", "s55-restore-create")
        login(physician, "restoredoc", "secret", "physician")
        create_patient(physician, "0055000001", "s55-restore-patient")

        xml_hash = seed_content_fixture()
        backup_job_id, archive_bytes = build_populated_backup_archive(admin)
        archive_sha = hashlib.sha256(archive_bytes).hexdigest()

        validated = validate_archive(admin, archive_bytes, "s55-validate-a")
        assert validated.status_code in (200, 202)
        body = validated.json()
        restore_id, digest, report = assert_staged_contract(body)

        # Staged report reflects THIS backup: identity, checksum, content.
        assert report["backup_id"] == backup_job_id
        assert report["archive_sha256"] == archive_sha
        assert report["backup_timestamp"], "backup date must be reported"
        assert report["db_schema_revision"], "schema revision must be reported"
        blob = json.dumps(report).lower()
        assert xml_hash.lower() in blob  # network XML checksum surfaced
        assert "s55-synthetic-ddi-v1" in blob  # DDI dataset version surfaced

        reread = admin.get(f"/api/v1/restores/{restore_id}")
        assert reread.status_code == 200
        again = reread.json()
        assert again["status"] == "staged"
        assert again.get("confirmation_digest") == digest
        assert again.get("report") == report


def test_restore_validate_leaves_live_state_unchanged():
    """S55 item 1 (RED): staging never mutates live patients/login/jobs (T1)."""
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "restorelive", "s55-live-create")
        login(physician, "restorelive", "secret", "physician")
        made = create_patient(physician, "0055000002", "s55-live-patient")
        patient_uuid = made["patient"]["id"]

        seed_content_fixture()
        _, archive_bytes = build_populated_backup_archive(admin)

        live_before = admin.get("/api/v1/patients", params={"limit": 100})
        assert live_before.status_code == 200
        backups_before = admin.get("/api/v1/backups")
        backups_status = backups_before.status_code

        validated = validate_archive(admin, archive_bytes, "s55-validate-live")
        assert validated.status_code in (200, 202)
        assert_staged_contract(validated.json())

        # Live-side reads through public HTTP: patient still readable,
        # admin can still log in, backup jobs still listed.
        live_after = admin.get("/api/v1/patients", params={"limit": 100})
        assert live_after.status_code == 200
        assert live_after.json() == live_before.json()
        assert (
            any(
                str(item.get("id")) == str(patient_uuid)
                for item in live_after.json().get(
                    "items", live_after.json().get("patients", [])
                )
            )
            if isinstance(live_after.json(), dict)
            else str(patient_uuid) in live_after.text
        )

        with TestClient(app) as admin_again:
            login(admin_again)
            me = admin_again.get("/api/v1/me")
            assert me.status_code == 200

        backups_after = admin.get("/api/v1/backups")
        assert backups_after.status_code == backups_status
        if backups_status == 200:
            assert backups_after.json() == backups_before.json()


# ---------------------------------------------------------------------------
# S55 slice 2: mutant archives must FAIL BEFORE any live mutation.
#
# Scope: docs/dev/tasks.md S55 item 2; plan.md 10.3; seams T10 + T1.
# SYNTHETIC VALUES ONLY. Tests only; no backend changes in this cycle.
#
# Rejection codes below were confirmed against
# backend/src/x_insight/operations/restore.py (RestoreRejected codes) and
# operations/routes.py (422 with field_errors {"archive": <code>}; failures
# carry no restore id, so the GET-restores/{id} row check is skipped by
# design and live-unchanged is asserted through public HTTP instead).
# ---------------------------------------------------------------------------


def _s55s2_entries(raw):
    """Return [(name, payload)] for every stored file in a backup zip."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return [
            (info.filename, archive.read(info.filename))
            for info in archive.infolist()
            if not info.is_dir()
        ]


def _s55s2_manifest(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return json.loads(archive.read("manifest.json").decode("utf-8"))


def _s55s2_dump_manifest(manifest):
    return json.dumps(manifest, sort_keys=True).encode("utf-8")


def _s55s2_rebuild(entries, manifest_override=None, extra_infos=()):
    """Repack entries (optionally swapping manifest.json) plus extra ZipInfos."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            if name == "manifest.json" and manifest_override is not None:
                payload = manifest_override
            archive.writestr(name, payload)
        for info, payload in extra_infos:
            archive.writestr(info, payload)
    return buf.getvalue()


def _mutant_traversal(valid):
    marker = b"s55s2-evil-traversal-marker"
    extra = [(zipfile.ZipInfo("../../evil.txt"), marker + b"-payload")]
    return (
        _s55s2_rebuild(_s55s2_entries(valid), extra_infos=extra),
        "unsafe_path",
        marker,
        False,
    )


def _mutant_absolute(valid):
    marker = b"s55s2-evil-absolute-marker"
    extra = [(zipfile.ZipInfo("/abs/evil.txt"), marker + b"-payload")]
    return (
        _s55s2_rebuild(_s55s2_entries(valid), extra_infos=extra),
        "unsafe_path",
        marker,
        False,
    )


def _mutant_symlink(valid):
    marker = b"s55s2-evil-symlink-marker"
    info = zipfile.ZipInfo("s55s2-link.txt")
    info.external_attr = 0o120777 << 16  # symlink file-type bits
    return (
        _s55s2_rebuild(
            _s55s2_entries(valid), extra_infos=[(info, marker + b"-target")]
        ),
        "unsafe_path",
        marker,
        False,
    )


def _mutant_oversized(valid):
    # Valid bytes; the tiny expansion limit is applied at upload time.
    return valid, "expansion_too_large", b"s55s2-no-new-bytes", False


def _mutant_corrupt_hash(valid):
    probe = None
    out = []
    for name, payload in _s55s2_entries(valid):
        if name == "database/patients.json":
            flipped = bytearray(payload)
            flipped[0] ^= 0x01
            payload = bytes(flipped)
            probe = payload[:64]
        out.append((name, payload))
    assert probe is not None, "valid archive lacks database/patients.json"
    # Manifest left untouched, so the checksum check must fire first.
    return _s55s2_rebuild(out), "corrupt_hash", probe, False


def _mutant_unsupported_schema(valid):
    manifest = _s55s2_manifest(valid)
    manifest["db_schema_revision"] = "9999"
    # File hashes untouched: only the revision field changes.
    mutant = _s55s2_rebuild(
        _s55s2_entries(valid),
        manifest_override=_s55s2_dump_manifest(manifest),
    )
    return mutant, "unsupported_schema", b'"db_schema_revision": "9999"', False


def _mutant_missing_artifact(valid):
    probe = None
    out = []
    for name, payload in _s55s2_entries(valid):
        if name == "database/patients.json":
            probe = payload[:64]
            continue
        out.append((name, payload))
    assert probe is not None, "valid archive lacks database/patients.json"
    return _s55s2_rebuild(out), "missing_artifact", probe, False


def _mutant_malformed_content(valid):
    bad = b"not json{{{ s55s2-malformed"
    manifest = _s55s2_manifest(valid)
    for entry in manifest["files"]:
        if entry.get("path") == "database/patients.json":
            # Recompute this entry so the failure lands at JSON parse,
            # not at the earlier hash check.
            entry["sha256"] = hashlib.sha256(bad).hexdigest()
            entry["bytes"] = len(bad)
    out = [
        (name, bad if name == "database/patients.json" else payload)
        for name, payload in _s55s2_entries(valid)
    ]
    mutant = _s55s2_rebuild(out, manifest_override=_s55s2_dump_manifest(manifest))
    return mutant, "malformed_database_content", bad, False


_S55S2_MUTANTS = {
    "traversal": _mutant_traversal,
    "absolute": _mutant_absolute,
    "symlink": _mutant_symlink,
    "oversized": _mutant_oversized,
    "corrupt_hash": _mutant_corrupt_hash,
    "unsupported_schema": _mutant_unsupported_schema,
    "missing_artifact": _mutant_missing_artifact,
    "malformed_content": _mutant_malformed_content,
}

_S55S2_LIMIT_PATCH_CASES = {"oversized"}


def _assert_s55s2_rejected(admin, mutant, expected_code, probe, key):
    """POST a mutant; expect 422 + archive field error, no content echo."""
    response = validate_archive(admin, mutant, key)
    assert response.status_code == 422, (
        f"mutant must be rejected, got {response.status_code}: {response.text[:500]!r}"
    )
    body = response.json()
    field_errors = body.get("field_errors", {})
    assert "archive" in field_errors, f"missing archive field error: {body!r}"
    assert field_errors["archive"] == expected_code, (
        f"expected code {expected_code!r}, got {body!r}"
    )
    # Failure responses carry no restore id, so there is no staged row to
    # fetch via GET /api/v1/restores/{id} (skipped by design).
    assert "restore_id" not in body, f"failure leaked a restore id: {body!r}"
    # Untrusted archive content must never be reflected in the response.
    assert probe not in response.content, (
        f"response echoes untrusted archive bytes for {expected_code!r}"
    )
    return body


def _assert_s55s2_live_unchanged(admin, patient_uuid):
    listed = admin.get("/api/v1/patients", params={"limit": 100})
    assert listed.status_code == 200
    assert patient_uuid in listed.text, "synthetic patient vanished after reject"
    with TestClient(app) as admin_again:
        login(admin_again)  # admin login still works after failed stagings


@pytest.mark.parametrize("case", sorted(_S55S2_MUTANTS))
def test_restore_validate_mutant_rejected_before_live_mutation(case, monkeypatch):
    """S55 item 2 (T10+T1): each mutant archive is rejected; live unchanged."""
    builder = _S55S2_MUTANTS[case]
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "s55s2doc", f"s55s2-phys-{case}-{nonce}")
        login(physician, "s55s2doc", "secret", "physician")
        made = create_patient(physician, "0055000201", f"s55s2-patient-{case}-{nonce}")
        patient_uuid = made["patient"]["id"]

        seed_content_fixture()
        _, valid = build_populated_backup_archive(admin)
        mutant, expected_code, probe, _ = builder(valid)

        if case in _S55S2_LIMIT_PATCH_CASES:
            # restore.py caches the env value in a module constant at import;
            # patch both so the upload exercises the tiny expansion limit.
            monkeypatch.setenv("X_INSIGHT_RESTORE_MAX_EXPANDED_BYTES", "100")
            monkeypatch.setattr(restore_ops, "MAX_RESTORE_EXPANDED_BYTES", 100)

        body = _assert_s55s2_rejected(
            admin, mutant, expected_code, probe, f"s55s2-{case}-{nonce}"
        )
        if case in _S55S2_LIMIT_PATCH_CASES:
            blob = (body.get("message", "") + str(body.get("field_errors", ""))).lower()
            assert "expansion" in blob or "size" in blob or "limit" in blob, (
                f"oversized error must mention size/expansion/limit: {body!r}"
            )
        _assert_s55s2_live_unchanged(admin, patient_uuid)


# ---------------------------------------------------------------------------
# S55 slice 3: singleton identity, dangling references, artifact consistency,
# untrusted-SQL proof, and live readability under validation load.
#
# Scope: docs/dev/tasks.md S55 item 3; plan.md 10.3 steps 2-3;
# seams T10 + T1. SYNTHETIC VALUES ONLY. Tests only; no backend changes.
#
# Rejection codes asserted exactly below were confirmed against
# backend/src/x_insight/operations/restore.py (RestoreRejected codes):
# admin_singleton_violation, dangling_reference, artifact_mismatch,
# unsafe_xml/malformed_xml, corrupt_hash. Failures return 422 with
# field_errors {"archive": <code>} (operations/routes.py) and carry no
# restore id; live-unchanged is asserted through public HTTP instead.
# ---------------------------------------------------------------------------


def _s55s3_rows(valid, name):
    with zipfile.ZipFile(io.BytesIO(valid)) as archive:
        return json.loads(archive.read(name).decode("utf-8"))


def _s55s3_rehash(manifest, path, payload, table=None, rows=None):
    """Point one manifest files-entry (and its tables entry) at payload."""
    for entry in manifest["files"]:
        if entry.get("path") == path:
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
            entry["bytes"] = len(payload)
    if table is not None and isinstance(manifest.get("tables", {}).get(table), dict):
        manifest["tables"][table]["rows"] = len(rows)
        manifest["tables"][table]["sha256"] = hashlib.sha256(payload).hexdigest()


def _s55s3_rebuild(entries, swaps, manifest):
    out = [
        (name, swaps[name] if name in swaps else payload) for name, payload in entries
    ]
    return _s55s2_rebuild(out, manifest_override=_s55s2_dump_manifest(manifest))


def _s55s3_setup(admin, physician, nonce, tag, patient_code):
    """Log in, add a physician + synthetic patient, seed, return archive."""
    login(admin)
    create_physician(admin, f"s55s3{tag}doc", f"s55s3-{tag}-phys-{nonce}")
    login(physician, f"s55s3{tag}doc", "secret", "physician")
    made = create_patient(physician, patient_code, f"s55s3-{tag}-patient-{nonce}")
    seed_content_fixture()
    _, valid = build_populated_backup_archive(admin)
    return valid, made["patient"]["id"]


def _assert_s55s3_rejected(admin, mutant, expected_codes, probe, key):
    """POST a mutant; expect 422 + archive field error, no content echo."""
    if isinstance(expected_codes, str):
        expected_codes = {expected_codes}
    response = validate_archive(admin, mutant, key)
    assert response.status_code == 422, (
        f"mutant must be rejected, got {response.status_code}: {response.text[:500]!r}"
    )
    body = response.json()
    field_errors = body.get("field_errors", {})
    assert "archive" in field_errors, f"missing archive field error: {body!r}"
    assert field_errors["archive"] in expected_codes, (
        f"expected code in {sorted(expected_codes)!r}, got {body!r}"
    )
    assert "restore_id" not in body, f"failure leaked a restore id: {body!r}"
    assert probe not in response.content, (
        f"response echoes untrusted archive bytes for {field_errors['archive']!r}"
    )
    return body


def test_restore_validate_zero_admins_rejected():
    """S55 item 3 (T10+T1): archive with no admin row fails singleton check."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        archive, patient_uuid = _s55s3_setup(
            admin, physician, nonce, "noadm", "0055000301"
        )
        rows = _s55s3_rows(archive, "database/users.json")
        admins = [row for row in rows if row.get("role") == "admin"]
        assert admins, "test backup carries no admin row to remove"
        probe = str(admins[0].get("id")).encode("utf-8")
        kept = [row for row in rows if row.get("role") != "admin"]
        payload = json.dumps(kept, sort_keys=True).encode("utf-8")
        manifest = _s55s2_manifest(archive)
        _s55s3_rehash(manifest, "database/users.json", payload, "users", kept)
        mutant = _s55s3_rebuild(
            _s55s2_entries(archive), {"database/users.json": payload}, manifest
        )
        _assert_s55s3_rejected(
            admin, mutant, "admin_singleton_violation", probe, f"s55s3-noadm-{nonce}"
        )
        _assert_s55s2_live_unchanged(admin, patient_uuid)


def test_restore_validate_two_admins_rejected():
    """S55 item 3 (T10+T1): archive with two admin rows fails singleton check."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        archive, patient_uuid = _s55s3_setup(
            admin, physician, nonce, "twoadm", "0055000302"
        )
        rows = _s55s3_rows(archive, "database/users.json")
        admins = [row for row in rows if row.get("role") == "admin"]
        assert admins, "test backup carries no admin row to duplicate"
        clone = dict(admins[0])
        clone["id"] = str(uuid.uuid4())
        clone["username"] = "s55seviladmin"
        probe = b"s55seviladmin"
        grown = rows + [clone]
        payload = json.dumps(grown, sort_keys=True).encode("utf-8")
        manifest = _s55s2_manifest(archive)
        _s55s3_rehash(manifest, "database/users.json", payload, "users", grown)
        mutant = _s55s3_rebuild(
            _s55s2_entries(archive), {"database/users.json": payload}, manifest
        )
        _assert_s55s3_rejected(
            admin, mutant, "admin_singleton_violation", probe, f"s55s3-twoadm-{nonce}"
        )
        _assert_s55s2_live_unchanged(admin, patient_uuid)


def test_restore_validate_dangling_encounter_rejected():
    """S55 item 3 (T10+T1): encounter naming an unknown patient is rejected."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        archive, patient_uuid = _s55s3_setup(
            admin, physician, nonce, "dang", "0055000303"
        )
        rows = _s55s3_rows(archive, "database/encounters.json")
        assert rows, "test backup carries no encounter to dangle"
        ghost = str(uuid.uuid4())
        rows[0]["patient_id"] = ghost
        probe = ghost.encode("utf-8")
        payload = json.dumps(rows, sort_keys=True).encode("utf-8")
        manifest = _s55s2_manifest(archive)
        _s55s3_rehash(manifest, "database/encounters.json", payload, "encounters", rows)
        mutant = _s55s3_rebuild(
            _s55s2_entries(archive), {"database/encounters.json": payload}, manifest
        )
        _assert_s55s3_rejected(
            admin, mutant, "dangling_reference", probe, f"s55s3-dang-{nonce}"
        )

        notes = _s55s3_rows(archive, "database/encounter_notes.json")
        if notes:
            ghost_eid = str(uuid.uuid4())
            notes[0]["encounter_id"] = ghost_eid
            note_probe = ghost_eid.encode("utf-8")
            note_payload = json.dumps(notes, sort_keys=True).encode("utf-8")
            manifest2 = _s55s2_manifest(archive)
            _s55s3_rehash(
                manifest2,
                "database/encounter_notes.json",
                note_payload,
                "encounter_notes",
                notes,
            )
            note_mutant = _s55s3_rebuild(
                _s55s2_entries(archive),
                {"database/encounter_notes.json": note_payload},
                manifest2,
            )
            _assert_s55s3_rejected(
                admin,
                note_mutant,
                "dangling_reference",
                note_probe,
                f"s55s3-dangnote-{nonce}",
            )
        _assert_s55s2_live_unchanged(admin, patient_uuid)


def test_restore_validate_corrupt_network_artifact_rejected():
    """S55 item 3 (T10+T1): flipped artifact byte fails hash/consistency check."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        archive, patient_uuid = _s55s3_setup(
            admin, physician, nonce, "netbad", "0055000304"
        )
        versions = _s55s3_rows(archive, "database/network_versions.json")
        assert versions, "test backup carries no network_versions row to corrupt"
        vid = versions[0].get("id")
        art_path = f"artifacts/networks/{vid}.xml"
        entries = dict(_s55s2_entries(archive))
        assert art_path in entries, f"test backup lacks {art_path}"
        flipped = bytearray(entries[art_path])
        flipped[0] ^= 0x01
        mutant = _s55s2_rebuild(
            [
                (name, bytes(flipped) if name == art_path else payload)
                for name, payload in entries.items()
            ]
        )
        # Hash check fires before row/artifact comparison, so corrupt_hash is
        # expected; artifact_mismatch is accepted if ordering ever changes.
        _assert_s55s3_rejected(
            admin,
            mutant,
            {"corrupt_hash", "artifact_mismatch"},
            SYNTHETIC_XML,
            f"s55s3-netbad-{nonce}",
        )
        _assert_s55s2_live_unchanged(admin, patient_uuid)


def test_restore_validate_unsafe_network_xml_rejected():
    """S55 item 3 (T10+T1): entity-declaring XML fails safety inspection."""
    nonce = uuid.uuid4().hex[:8]
    evil = (
        b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY x "y">]>'
        b'<BIF VERSION="0.3"><NETWORK><NAME>s55</NAME></NETWORK></BIF>'
    )
    with TestClient(app) as admin, TestClient(app) as physician:
        archive, patient_uuid = _s55s3_setup(
            admin, physician, nonce, "netevil", "0055000305"
        )
        versions = _s55s3_rows(archive, "database/network_versions.json")
        assert versions, "test backup carries no network_versions row for XML swap"
        vid = versions[0].get("id")
        art_path = f"artifacts/networks/{vid}.xml"
        entries = dict(_s55s2_entries(archive))
        assert art_path in entries, f"test backup lacks {art_path}"
        versions[0]["sha256"] = hashlib.sha256(evil).hexdigest()
        versions_payload = json.dumps(versions, sort_keys=True).encode("utf-8")
        manifest = _s55s2_manifest(archive)
        # Recompute BOTH manifest entries so the failure must land at XML
        # safety inspection, proving content is inspected, not just hashed.
        _s55s3_rehash(
            manifest,
            "database/network_versions.json",
            versions_payload,
            "network_versions",
            versions,
        )
        _s55s3_rehash(manifest, art_path, evil)
        swaps = {"database/network_versions.json": versions_payload, art_path: evil}
        mutant = _s55s3_rebuild(_s55s2_entries(archive), swaps, manifest)
        _assert_s55s3_rejected(
            admin, mutant, "unsafe_xml", b'<!ENTITY x "y">', f"s55s3-netevil-{nonce}"
        )
        _assert_s55s2_live_unchanged(admin, patient_uuid)


def test_restore_validate_sql_text_never_reaches_live():
    """S55 item 3 (T10+T1): SQL-text payload never executes nor lands live."""
    nonce = uuid.uuid4().hex[:8]
    injected_id = str(uuid.uuid4())
    injected_code = "0055000399"
    probe = b"DROP TABLE patients"
    with TestClient(app) as admin, TestClient(app) as physician:
        archive, patient_uuid = _s55s3_setup(
            admin, physician, nonce, "sql", "0055000306"
        )
        rows = _s55s3_rows(archive, "database/patients.json")
        assert rows, "test backup carries no patient row to clone"
        evil_row = dict(rows[0])
        evil_row["id"] = injected_id
        evil_row["patient_id"] = injected_code
        evil_row["first_name"] = "Robert'); DROP TABLE patients;--"
        evil_row["last_name"] = "s55synthetic"
        grown = rows + [evil_row]
        payload = json.dumps(grown, sort_keys=True).encode("utf-8")
        manifest = _s55s2_manifest(archive)
        _s55s3_rehash(manifest, "database/patients.json", payload, "patients", grown)
        mutant = _s55s3_rebuild(
            _s55s2_entries(archive), {"database/patients.json": payload}, manifest
        )

        before = admin.get("/api/v1/patients", params={"limit": 100})
        assert before.status_code == 200
        before_count = len(
            before.json().get("items", before.json().get("patients", []))
            if isinstance(before.json(), dict)
            else []
        )

        response = validate_archive(admin, mutant, f"s55s3-sql-{nonce}")
        # Extra data rows are not necessarily invalid: either a 422 or a
        # staged-but-not-applied outcome is acceptable, as long as live is
        # untouched. Both branches encode that below.
        assert response.status_code in (200, 202, 422), (
            f"unexpected status {response.status_code}: {response.text[:500]!r}"
        )
        if response.status_code == 422:
            body = response.json()
            assert "archive" in body.get("field_errors", {}), (
                f"missing archive field error: {body!r}"
            )
            assert probe not in response.content, "response echoes SQL payload bytes"
        else:
            assert_staged_contract(response.json())

        live = admin.get("/api/v1/patients", params={"limit": 100})
        assert live.status_code == 200
        assert injected_id not in live.text, "staged payload leaked into live rows"
        assert injected_code not in live.text, "staged payload leaked into live rows"
        after_count = len(
            live.json().get("items", live.json().get("patients", []))
            if isinstance(live.json(), dict)
            else []
        )
        assert after_count == before_count, (
            f"live patient count changed {before_count} -> {after_count}"
        )
        assert patient_uuid in live.text, "synthetic patient vanished after staging"
        with TestClient(app) as admin_again:
            login(admin_again)  # admin login still works; patients table intact


def test_restore_validate_mutant_sweep_leaves_live_unchanged():
    """S55 item 2 (T1): after ALL failed stagings, patient + login survive."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "s55s2sweepdoc", f"s55s2-sweep-phys-{nonce}")
        login(physician, "s55s2sweepdoc", "secret", "physician")
        made = create_patient(physician, "0055000202", f"s55s2-sweep-patient-{nonce}")
        patient_uuid = made["patient"]["id"]

        seed_content_fixture()
        # One backup-download reused for the whole mutant sweep.
        _, valid = build_populated_backup_archive(admin)

        for index, case in enumerate(sorted(_S55S2_MUTANTS)):
            mutant, expected_code, probe, _ = _S55S2_MUTANTS[case](valid)
            key = f"s55s2-sweep-{index}-{case}-{nonce}"
            if case in _S55S2_LIMIT_PATCH_CASES:
                old = restore_ops.MAX_RESTORE_EXPANDED_BYTES
                restore_ops.MAX_RESTORE_EXPANDED_BYTES = 100
                try:
                    _assert_s55s2_rejected(admin, mutant, expected_code, probe, key)
                finally:
                    restore_ops.MAX_RESTORE_EXPANDED_BYTES = old
            else:
                _assert_s55s2_rejected(admin, mutant, expected_code, probe, key)

        _assert_s55s2_live_unchanged(admin, patient_uuid)
        with TestClient(app) as admin_again:
            login(admin_again)
            me = admin_again.get("/api/v1/me")
            assert me.status_code == 200


def test_restore_validate_slice3_sweep_leaves_live_readable():
    """S55 item 3 (T1): after hostile mutants, live stays writable (no locks)."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        archive, patient_uuid = _s55s3_setup(
            admin, physician, nonce, "sweep", "0055000307"
        )

        rows = _s55s3_rows(archive, "database/users.json")
        kept = [row for row in rows if row.get("role") != "admin"]
        users_payload = json.dumps(kept, sort_keys=True).encode("utf-8")
        manifest = _s55s2_manifest(archive)
        _s55s3_rehash(manifest, "database/users.json", users_payload, "users", kept)
        no_admin = _s55s3_rebuild(
            _s55s2_entries(archive), {"database/users.json": users_payload}, manifest
        )
        noadm_probe = (
            str(kept[0].get("id")).encode("utf-8") if kept else b"no-kept-rows"
        )
        _assert_s55s3_rejected(
            admin,
            no_admin,
            "admin_singleton_violation",
            noadm_probe,
            f"s55s3-sweep-noadm-{nonce}",
        )

        encounters = _s55s3_rows(archive, "database/encounters.json")
        assert encounters, "test backup carries no encounter to dangle"
        ghost = str(uuid.uuid4())
        encounters[0]["patient_id"] = ghost
        enc_payload = json.dumps(encounters, sort_keys=True).encode("utf-8")
        manifest = _s55s2_manifest(archive)
        _s55s3_rehash(
            manifest, "database/encounters.json", enc_payload, "encounters", encounters
        )
        dangling = _s55s3_rebuild(
            _s55s2_entries(archive), {"database/encounters.json": enc_payload}, manifest
        )
        _assert_s55s3_rejected(
            admin,
            dangling,
            "dangling_reference",
            ghost.encode("utf-8"),
            f"s55s3-sweep-dang-{nonce}",
        )

        evil = (
            b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY x "y">]>'
            b'<BIF VERSION="0.3"><NETWORK><NAME>s55</NAME></NETWORK></BIF>'
        )
        versions = _s55s3_rows(archive, "database/network_versions.json")
        assert versions, "test backup carries no network_versions row for XML swap"
        vid = versions[0].get("id")
        art_path = f"artifacts/networks/{vid}.xml"
        versions[0]["sha256"] = hashlib.sha256(evil).hexdigest()
        versions_payload = json.dumps(versions, sort_keys=True).encode("utf-8")
        manifest = _s55s2_manifest(archive)
        _s55s3_rehash(
            manifest,
            "database/network_versions.json",
            versions_payload,
            "network_versions",
            versions,
        )
        _s55s3_rehash(manifest, art_path, evil)
        unsafe = _s55s3_rebuild(
            _s55s2_entries(archive),
            {"database/network_versions.json": versions_payload, art_path: evil},
            manifest,
        )
        _assert_s55s3_rejected(
            admin, unsafe, "unsafe_xml", b"<!ENTITY", f"s55s3-sweep-unsafe-{nonce}"
        )

        # Validation never locked/mutated live tables: a fresh patient saves
        # (201) and both logins still work after every hostile mutant above.
        _assert_s55s2_live_unchanged(admin, patient_uuid)
        made = create_patient(physician, "0055000308", f"s55s3-sweep-live-{nonce}")
        assert made["patient"]["id"]
        with TestClient(app) as admin_again:
            login(admin_again)
            me = admin_again.get("/api/v1/me")
            assert me.status_code == 200


# ---------------------------------------------------------------------------
# S55 slice 4: replacement/expiry invalidation, failed-sweep live stability,
# idempotency ordering, no premature commit, auth matrix.
#
# Scope: docs/dev/tasks.md S55 item 4; plan.md 10.3; seams T10 + T1.
# SYNTHETIC VALUES ONLY. Tests only; no backend changes in this cycle.
#
# GET /api/v1/restores/{id} fields confirmed against
# backend/src/x_insight/operations/routes.py (read_restore) and
# operations/restore.py (get_restore): status in ("staged", "failed"),
# confirmation_digest, read-time expired + superseded flags, report, error;
# unknown ids -> 404 "Restore job not found." No commit route exists
# (S56 owns it), so POST /api/v1/restores/commit must 404.
# confirmable-vs-expired is encoded as the expired flag (S56 enforces).
# ---------------------------------------------------------------------------


def _s55s4_build_backup(admin, key):
    """Start (fresh key) + poll + download one backup; return (job_id, bytes).

    Uses a caller-supplied Idempotency-Key so a second backup in the same
    test is genuinely new (different backup_id/content), unlike the fixed
    key in build_populated_backup_archive.
    """
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
    return job_id, downloaded.content


def _s55s4_stage_two(admin, physician, nonce):
    """Stage archive A, add a patient, take backup B, stage B.

    Returns (restore_a, digest_a, restore_b, digest_b).
    """
    login(admin)
    create_physician(admin, "s55s4doc", f"s55s4-phys-{nonce}")
    login(physician, "s55s4doc", "secret", "physician")
    create_patient(physician, "0055000401", f"s55s4-patient-a-{nonce}")
    seed_content_fixture()
    _, archive_a = _s55s4_build_backup(admin, f"s55s4-backup-a-{nonce}")
    first = validate_archive(admin, archive_a, f"s55s4-val-a-{nonce}")
    assert first.status_code in (200, 202)
    rid_a, digest_a, _ = assert_staged_contract(first.json())

    create_patient(physician, "0055000402", f"s55s4-patient-b-{nonce}")
    _, archive_b = _s55s4_build_backup(admin, f"s55s4-backup-b-{nonce}")
    second = validate_archive(admin, archive_b, f"s55s4-val-b-{nonce}")
    assert second.status_code in (200, 202)
    rid_b, digest_b, _ = assert_staged_contract(second.json())
    return rid_a, digest_a, rid_b, digest_b


def test_restore_validate_replacement_supersedes_prior():
    """S55 item 4 (T10): staging B supersedes A; both keep status + digests."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        rid_a, digest_a, rid_b, digest_b = _s55s4_stage_two(admin, physician, nonce)
        assert digest_a != digest_b, "distinct archives must yield distinct digests"

        reread_a = admin.get(f"/api/v1/restores/{rid_a}")
        assert reread_a.status_code == 200
        body_a = reread_a.json()
        assert body_a["status"] == "staged"
        assert body_a.get("confirmation_digest") == digest_a
        assert body_a["superseded"] is True

        reread_b = admin.get(f"/api/v1/restores/{rid_b}")
        assert reread_b.status_code == 200
        body_b = reread_b.json()
        assert body_b["status"] == "staged"
        assert body_b.get("confirmation_digest") == digest_b
        assert body_b["superseded"] is False


def test_restore_validate_expiry_invalidates_confirmation():
    """S55 item 4 (T10): backdated expires_at flips expired on A only."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        rid_a, digest_a, rid_b, digest_b = _s55s4_stage_two(admin, physician, nonce)
        # Fixture setup may touch disposable storage directly.
        with db.transaction() as conn:
            conn.execute(
                text(
                    "UPDATE recovery_jobs SET expires_at = "
                    "now() - interval '1 hour' "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": rid_a},
            )

        stale = admin.get(f"/api/v1/restores/{rid_a}")
        assert stale.status_code == 200
        stale_body = stale.json()
        assert stale_body["expired"] is True
        # First job is both superseded AND expired: assert each flag
        # independently, not mutual exclusion.
        assert stale_body["superseded"] is True
        assert stale_body.get("confirmation_digest") == digest_a

        fresh = admin.get(f"/api/v1/restores/{rid_b}")
        assert fresh.status_code == 200
        fresh_body = fresh.json()
        assert fresh_body["expired"] is False
        assert fresh_body["superseded"] is False
        assert fresh_body.get("confirmation_digest") == digest_b


def test_restore_validate_slice4_failed_sweep_leaves_live_unchanged():
    """S55 item 4 (T1): failing uploads leave directory + backup job identical."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "s55s4sweepdoc", f"s55s4-sweep-phys-{nonce}")
        login(physician, "s55s4sweepdoc", "secret", "physician")
        made = create_patient(physician, "0055000403", f"s55s4-sweep-patient-{nonce}")
        patient_uuid = made["patient"]["id"]
        seed_content_fixture()
        backup_job_id, valid = _s55s4_build_backup(admin, f"s55s4-sweep-backup-{nonce}")

        directory_before = admin.get("/api/v1/patients", params={"limit": 100})
        assert directory_before.status_code == 200
        directory_bytes = directory_before.content
        assert patient_uuid in directory_before.text
        backup_before = admin.get(f"/api/v1/backups/{backup_job_id}")
        assert backup_before.status_code == 200
        backup_body = backup_before.json()

        corrupt, _, corrupt_probe, _ = _mutant_corrupt_hash(valid)
        _assert_s55s2_rejected(
            admin,
            corrupt,
            "corrupt_hash",
            corrupt_probe,
            f"s55s4-sweep-corrupt-{nonce}",
        )
        schema_mutant, _, schema_probe, _ = _mutant_unsupported_schema(valid)
        _assert_s55s3_rejected(
            admin,
            schema_mutant,
            "unsupported_schema",
            schema_probe,
            f"s55s4-sweep-schema-{nonce}",
        )

        directory_after = admin.get("/api/v1/patients", params={"limit": 100})
        assert directory_after.status_code == 200
        assert directory_after.content == directory_bytes
        backup_after = admin.get(f"/api/v1/backups/{backup_job_id}")
        assert backup_after.status_code == 200
        assert backup_after.json() == backup_body

        with TestClient(app) as admin_again:
            login(admin_again)
            me = admin_again.get("/api/v1/me")
            assert me.status_code == 200


def test_restore_validate_idempotency_key_ordering():
    """S55 item 4 (T10): same key+bytes replays; same key+other bytes -> 409."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "s55s4idemdoc", f"s55s4-idem-phys-{nonce}")
        login(physician, "s55s4idemdoc", "secret", "physician")
        create_patient(physician, "0055000404", f"s55s4-idem-patient-{nonce}")
        seed_content_fixture()
        _, valid = _s55s4_build_backup(admin, f"s55s4-idem-backup-{nonce}")

        key = f"s55s4-idem-{nonce}"
        first = validate_archive(admin, valid, key)
        assert first.status_code in (200, 202)
        rid, digest, _ = assert_staged_contract(first.json())

        replay = validate_archive(admin, valid, key)
        assert replay.status_code in (200, 202)
        again = replay.json()
        assert again.get("restore_id", again.get("job_id", again.get("id"))) == rid
        assert again.get("confirmation_digest") == digest

        # Truncated bytes are also invalid, so a 422 here would prove the
        # implementation validates BEFORE checking the idempotency conflict.
        truncated = valid[:64]
        assert truncated != valid
        conflict = validate_archive(admin, truncated, key)
        assert conflict.status_code == 409, (
            "idempotency conflict must be detected BEFORE validation: "
            f"got {conflict.status_code}: {conflict.text[:500]!r}"
        )


def test_restore_validate_no_premature_commit():
    """S55 item 4 (T10): commit route absent (S56); unknown ids 404."""
    nonce = uuid.uuid4().hex[:8]
    with TestClient(app) as admin:
        login(admin)
        commit = admin.post(
            "/api/v1/restores/commit",
            json={},
            headers=admin_headers(admin, f"s55s4-commit-{nonce}"),
        )
        assert commit.status_code in (404, 405)  # no commit route (S56);
        # "commit" path-matches GET /restores/{id}, hence 405 is also safe.

        ghost = admin.get(f"/api/v1/restores/{uuid.uuid4()}")
        assert ghost.status_code == 404

        for method in ("put", "delete"):
            response = getattr(admin, method)(
                "/api/v1/restores/validate",
                headers=admin_headers(admin, f"s55s4-{method}-{nonce}"),
            )
            assert response.status_code in (404, 405), (
                f"{method.upper()} /restores/validate must be absent, "
                f"got {response.status_code}"
            )


def test_restore_validate_auth_matrix():
    """S55 item 4 (T10+T1): anon 401, physician 403 on validate + GET."""
    nonce = uuid.uuid4().hex[:8]
    with (
        TestClient(app) as admin,
        TestClient(app) as physician,
        TestClient(app) as anon,
    ):
        login(admin)
        create_physician(admin, "s55s4authdoc", f"s55s4-auth-phys-{nonce}")
        login(physician, "s55s4authdoc", "secret", "physician")
        create_patient(physician, "0055000405", f"s55s4-auth-patient-{nonce}")
        seed_content_fixture()
        _, valid = _s55s4_build_backup(admin, f"s55s4-auth-backup-{nonce}")
        staged = validate_archive(admin, valid, f"s55s4-auth-val-{nonce}")
        assert staged.status_code in (200, 202)
        restore_id = assert_staged_contract(staged.json())[0]

        anon_post = anon.post(
            "/api/v1/restores/validate",
            files=[("archive", ("backup.zip", io.BytesIO(valid), "application/zip"))],
        )
        assert anon_post.status_code == 401

        phys_post = validate_archive(physician, valid, f"s55s4-auth-phys-{nonce}")
        assert phys_post.status_code == 403

        anon_get = anon.get(f"/api/v1/restores/{restore_id}")
        assert anon_get.status_code == 401

        phys_get = physician.get(f"/api/v1/restores/{restore_id}")
        assert phys_get.status_code == 403
