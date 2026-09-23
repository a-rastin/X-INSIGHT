"""Restore validation + isolated staging (S55 slice 1, seams T10+T1).

``validate_and_stage`` checks a backup zip WITHOUT touching live domain
tables, extracts the verified files into an isolated staging directory, and
records one ``kind='restore'`` ``recovery_jobs`` row plus its
``restore.validate`` audit row in a single transaction. Archive content is
never executed as SQL/Python and never echoed into errors or audit rows.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import stat
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from lxml import etree  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.engine import Connection

from x_insight import db
from x_insight.contracts import canonical_json, content_hash, to_utc_z, utc_now
from x_insight.operations.audit import RESTORE_VALIDATE, record_audit
from x_insight.operations.backup import APP_VERSION

MAX_RESTORE_UPLOAD_BYTES = int(
    os.environ.get("X_INSIGHT_RESTORE_MAX_UPLOAD_BYTES", 64 * 1024 * 1024)
)
MAX_RESTORE_EXPANDED_BYTES = int(
    os.environ.get("X_INSIGHT_RESTORE_MAX_EXPANDED_BYTES", 512 * 1024 * 1024)
)
MAX_RESTORE_FILES = int(os.environ.get("X_INSIGHT_RESTORE_MAX_FILES", 5000))

STAGING_TTL_SECONDS = 1800

KEY_REENTRY_NOTE = (
    "Provider credentials are stored as ciphertext only; the "
    "deployment encryption key (X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY) "
    "is never included in a backup archive. Restoring on a "
    "deployment without the original key requires key re-entry; "
    "affected provider revisions stay unreadable until then."
)

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class RestoreRejected(Exception):
    """Archive failed validation; carries the public ``code`` for 422."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class RestoreConflict(Exception):
    """Same Idempotency-Key reused with different bytes (HTTP 409)."""


def staging_dir() -> str:
    """Return the restore staging directory (created on demand)."""
    configured = os.environ.get("X_INSIGHT_RESTORE_DIR")
    if configured:
        return configured
    backend_dir = Path(__file__).resolve().parents[3]
    return str(backend_dir / "var" / "restores")


def _check_entry_name(name: str) -> None:
    if (
        name.startswith("/")
        or name.startswith("\\")
        or _DRIVE_RE.match(name) is not None
    ):
        raise RestoreRejected("unsafe_path", f"absolute entry: {name[:80]}")
    if ".." in name.replace("\\", "/").split("/"):
        raise RestoreRejected("unsafe_path", f"parent reference: {name[:80]}")


def _validate_archive(upload_bytes: bytes) -> dict[str, Any]:
    """Pure archive checks; returns manifest, dumps, and verified bytes."""
    if len(upload_bytes) > MAX_RESTORE_UPLOAD_BYTES:
        raise RestoreRejected(
            "upload_too_large",
            f"archive is {len(upload_bytes)} bytes (limit {MAX_RESTORE_UPLOAD_BYTES})",
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(upload_bytes))
    except zipfile.BadZipFile:
        raise RestoreRejected("not_a_zip", "upload is not a zip archive") from None
    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > MAX_RESTORE_FILES:
            raise RestoreRejected(
                "too_many_files",
                f"archive has {len(infos)} files (limit {MAX_RESTORE_FILES})",
            )
        claimed = 0
        for info in infos:
            _check_entry_name(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise RestoreRejected(
                    "unsafe_path", f"symlink entry: {info.filename[:80]}"
                )
            claimed += info.file_size
            if claimed > MAX_RESTORE_EXPANDED_BYTES:
                raise RestoreRejected(
                    "expansion_too_large",
                    f"archive expands beyond {MAX_RESTORE_EXPANDED_BYTES} bytes",
                )
        names = {info.filename for info in infos}
        if "manifest.json" not in names:
            raise RestoreRejected("malformed_manifest", "manifest.json is absent")
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise RestoreRejected(
                "malformed_manifest", "manifest.json is not valid JSON"
            ) from None
        if not isinstance(manifest, dict):
            raise RestoreRejected("malformed_manifest", "manifest is not an object")
        if manifest.get("schema_version") != 1:
            raise RestoreRejected(
                "unsupported_format",
                f"schema_version {manifest.get('schema_version')!r} is not 1",
            )
        for field in ("backup_id", "tables", "files"):
            if field not in manifest:
                raise RestoreRejected("malformed_manifest", f"manifest lacks {field!r}")
        if "timestamp" not in manifest and "created_at" not in manifest:
            raise RestoreRejected(
                "malformed_manifest", "manifest lacks a backup timestamp"
            )
        if not isinstance(manifest["tables"], dict) or not isinstance(
            manifest["files"], list
        ):
            raise RestoreRejected("malformed_manifest", "tables/files are misshapen")
        if manifest.get("db_schema_revision") != db.EXPECTED_SCHEMA_REVISION:
            raise RestoreRejected(
                "unsupported_schema",
                f"archive schema {manifest.get('db_schema_revision')!r} "
                f"does not match live {db.EXPECTED_SCHEMA_REVISION!r}",
            )
        verified: dict[str, bytes] = {}
        for entry in manifest["files"]:
            if not isinstance(entry, dict):
                raise RestoreRejected("malformed_manifest", "file entry is misshapen")
            path = entry.get("path")
            if not isinstance(path, str) or path not in names:
                raise RestoreRejected("missing_artifact", f"{path!r} is not archived")
            try:
                payload = archive.read(path)
            except KeyError:
                raise RestoreRejected(
                    "missing_artifact", f"{path!r} is not archived"
                ) from None
            if hashlib.sha256(payload).hexdigest() != entry.get("sha256") or len(
                payload
            ) != entry.get("bytes"):
                raise RestoreRejected("corrupt_hash", f"{path!r} failed its checksum")
            verified[path] = payload
        if sum(len(item) for item in verified.values()) > MAX_RESTORE_EXPANDED_BYTES:
            raise RestoreRejected(
                "expansion_too_large",
                f"archive expands beyond {MAX_RESTORE_EXPANDED_BYTES} bytes",
            )
        tables: dict[str, list[dict[str, Any]]] = {}
        for table in manifest["tables"]:
            path = f"database/{table}.json"
            if path not in names:
                raise RestoreRejected("missing_artifact", f"{path!r} is not archived")
            try:
                rows = json.loads(archive.read(path).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise RestoreRejected(
                    "malformed_database_content", f"{path!r} is not valid JSON"
                ) from None
            if not isinstance(rows, list):
                raise RestoreRejected(
                    "malformed_database_content", f"{path!r} is not a row list"
                )
            tables[table] = rows
        users = tables.get("users", [])
        admins = sum(1 for row in users if row.get("role") == "admin")
        if admins != 1:
            raise RestoreRejected(
                "admin_singleton_violation",
                f"staged users carry {admins} admin rows (need exactly 1)",
            )
        patients = tables.get("patients")
        encounters = tables.get("encounters")
        if patients and encounters:
            patient_ids = {row.get("id") for row in patients}
            for row in encounters:
                pid = row.get("patient_id")
                if pid is not None and pid not in patient_ids:
                    raise RestoreRejected(
                        "dangling_reference", "an encounter names an unknown patient"
                    )
        notes = tables.get("encounter_notes")
        if encounters and notes:
            encounter_ids = {row.get("id") for row in encounters}
            for row in notes:
                eid = row.get("encounter_id")
                if eid is not None and eid not in encounter_ids:
                    raise RestoreRejected(
                        "dangling_reference", "a note names an unknown encounter"
                    )
        for row in tables.get("network_versions", []):
            vid = row.get("id")
            path = f"artifacts/networks/{vid}.xml"
            staged_xml = verified.get(path)
            if staged_xml is None:
                raise RestoreRejected("artifact_mismatch", f"{path!r} is not archived")
            if hashlib.sha256(staged_xml).hexdigest() != row.get("sha256"):
                raise RestoreRejected("artifact_mismatch", f"{path!r} checksum differs")
            _check_xml(staged_xml, path)
        for row in tables.get("run_question_artifacts", []):
            effective = row.get("effective_xml")
            if isinstance(effective, str) and effective:
                path = f"artifacts/effective/{row.get('id')}.xml"
                if verified.get(path) != effective.encode("utf-8"):
                    raise RestoreRejected(
                        "artifact_mismatch", f"{path!r} differs from its row"
                    )
    return {"manifest": manifest, "tables": tables, "verified": verified}


def _check_xml(payload: bytes, path: str) -> None:
    lowered = payload.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise RestoreRejected("unsafe_xml", f"{path!r} declares entities")
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, huge_tree=False, recover=False
    )
    try:
        etree.fromstring(payload, parser=parser)
    except etree.XMLSyntaxError:
        raise RestoreRejected("malformed_xml", f"{path!r} is not well-formed") from None


def _read_live_counts(database_url: str) -> dict[str, int]:
    """Count live rows in a READ ONLY transaction; no writes permitted."""
    engine = db.get_engine(database_url)
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            counts = {
                table: int(
                    conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
                )
                for table in ("patients", "encounters", "users")
            }
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise
    return counts


def _write_staging(staging_path: str, verified: dict[str, bytes]) -> None:
    base = Path(staging_path)
    resolved_base = base.resolve()
    base.mkdir(parents=True, exist_ok=True)
    for path, payload in verified.items():
        target = (base / Path(*path.replace("\\", "/").split("/"))).resolve()
        if target != resolved_base and resolved_base not in target.parents:
            raise RestoreRejected("unsafe_path", f"staging escape: {path[:80]}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def _digest_input(report: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in report.items() if k not in ("staged_at", "expires_at")}


def _stored_status(row_status: str) -> str:
    return "staged" if row_status == "succeeded" else "failed"


def _row_to_result(row: Any, *, created: bool) -> dict[str, Any]:
    manifest = row["manifest"]
    if isinstance(manifest, str):
        manifest = json.loads(manifest)
    error = row["error"]
    code = error.split(":", 1)[0] if error else None
    return {
        "restore_id": str(row["id"]),
        "status": _stored_status(str(row["status"])),
        "confirmation_digest": row["confirmation_digest"],
        "report": manifest,
        "error": error,
        "code": code,
        "created": created,
    }


def _record_failure(
    *,
    database_url: str,
    actor_id: str,
    idempotency_key: str,
    request_hash: str,
    request_id: str,
    code: str,
    detail: str,
) -> dict[str, Any]:
    error = f"{code}: {detail}"[:1000] if detail else code
    with db.transaction(database_url) as conn:
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {
                "scope": canonical_json(
                    {
                        "actor_id": actor_id,
                        "operation": RESTORE_VALIDATE,
                        "idempotency_key": idempotency_key,
                    }
                ).decode()
            },
        )
        existing = (
            conn.execute(
                text(
                    "SELECT id, status, request_hash, manifest, error, "
                    "confirmation_digest FROM recovery_jobs "
                    "WHERE kind = 'restore' "
                    "AND created_by = CAST(:actor AS uuid) "
                    "AND idempotency_key = :key"
                ),
                {"actor": actor_id, "key": idempotency_key},
            )
            .mappings()
            .first()
        )
        if existing is not None:
            if str(existing["request_hash"]) != request_hash:
                raise RestoreConflict("Idempotency key was used for another request.")
            return _row_to_result(existing, created=False)
        row = (
            conn.execute(
                text(
                    "INSERT INTO recovery_jobs "
                    "(kind, status, idempotency_key, request_hash, error, "
                    " created_by) "
                    "VALUES ('restore', 'failed', :key, :hash, :error, "
                    " CAST(:actor AS uuid)) "
                    "RETURNING id, status, manifest, error, confirmation_digest"
                ),
                {
                    "key": idempotency_key,
                    "hash": request_hash,
                    "error": error,
                    "actor": actor_id,
                },
            )
            .mappings()
            .one()
        )
        restore_id = str(row["id"])
        record_audit(
            conn,
            operation=RESTORE_VALIDATE,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            result_reference=restore_id,
            request_id=request_id,
            result_payload={
                "schema_version": 1,
                "restore_id": restore_id,
                "status": "failed",
            },
            result_status=422,
        )
    return _row_to_result(row, created=True)


def validate_and_stage(
    *,
    upload_bytes: bytes,
    filename: str,
    actor_id: str,
    idempotency_key: str,
    request_hash: str,
    request_id: str,
    database_url: str,
) -> dict[str, Any]:
    """Validate an archive, stage it, and record the restore job + audit.

    Returns ``{restore_id, status ("staged"/"failed"), confirmation_digest,
    report, error, code, created}``. Validation failures are recorded as
    ``failed`` rows (never raised); only idempotency conflicts raise.
    """
    del filename
    try:
        checked = _validate_archive(upload_bytes)
    except RestoreRejected as exc:
        return _record_failure(
            database_url=database_url,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            request_id=request_id,
            code=exc.code,
            detail=str(exc),
        )
    manifest = checked["manifest"]
    tables = checked["tables"]
    verified = checked["verified"]
    live = _read_live_counts(database_url)
    staged_at = to_utc_z(utc_now())
    expires_at = to_utc_z(utc_now() + timedelta(seconds=STAGING_TTL_SECONDS))
    report: dict[str, Any] = {
        "schema_version": 1,
        "backup_id": manifest["backup_id"],
        "backup_timestamp": manifest.get("timestamp") or manifest.get("created_at"),
        "db_schema_revision": manifest["db_schema_revision"],
        "app_version": manifest.get("app_version", APP_VERSION),
        "archive_sha256": hashlib.sha256(upload_bytes).hexdigest(),
        "tables": {
            table: info["rows"] if isinstance(info, dict) else info
            for table, info in manifest["tables"].items()
        },
        "files": [
            {"path": e["path"], "sha256": e["sha256"], "bytes": e["bytes"]}
            for e in manifest["files"]
        ],
        "impact": {
            "live": live,
            "staged": {
                "patients": len(tables.get("patients", [])),
                "encounters": len(tables.get("encounters", [])),
                "users": len(tables.get("users", [])),
            },
        },
        "key_reentry_note": manifest.get("key_reentry_note") or KEY_REENTRY_NOTE,
        "staged_at": staged_at,
        "expires_at": expires_at,
    }
    if manifest.get("coverage") is not None:
        report["coverage"] = manifest["coverage"]
    digest = content_hash(_digest_input(report))

    restore_id = str(uuid.uuid4())
    staging_path = os.path.join(staging_dir(), f"restore-{restore_id}")
    try:
        _write_staging(staging_path, verified)
    except RestoreRejected as exc:
        shutil.rmtree(staging_path, ignore_errors=True)
        return _record_failure(
            database_url=database_url,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            request_id=request_id,
            code=exc.code,
            detail=str(exc),
        )
    with db.transaction(database_url) as conn:
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {
                "scope": canonical_json(
                    {
                        "actor_id": actor_id,
                        "operation": RESTORE_VALIDATE,
                        "idempotency_key": idempotency_key,
                    }
                ).decode()
            },
        )
        existing = (
            conn.execute(
                text(
                    "SELECT id, status, request_hash, manifest, error, "
                    "confirmation_digest FROM recovery_jobs "
                    "WHERE kind = 'restore' "
                    "AND created_by = CAST(:actor AS uuid) "
                    "AND idempotency_key = :key"
                ),
                {"actor": actor_id, "key": idempotency_key},
            )
            .mappings()
            .first()
        )
        if existing is not None:
            if str(existing["request_hash"]) != request_hash:
                shutil.rmtree(staging_path, ignore_errors=True)
                raise RestoreConflict("Idempotency key was used for another request.")
            shutil.rmtree(staging_path, ignore_errors=True)
            return _row_to_result(existing, created=False)
        conn.execute(
            text(
                "INSERT INTO recovery_jobs "
                "(id, kind, status, idempotency_key, request_hash, staging_path, "
                " confirmation_digest, expires_at, manifest, created_by, "
                " completed_at) "
                "VALUES (CAST(:id AS uuid), 'restore', 'succeeded', :key, :hash, "
                " :staging, :digest, CAST(:expires AS timestamptz), "
                " CAST(:manifest AS jsonb), CAST(:actor AS uuid), now())"
            ),
            {
                "id": restore_id,
                "key": idempotency_key,
                "hash": request_hash,
                "staging": staging_path,
                "digest": digest,
                "expires": expires_at,
                "manifest": json.dumps(report, sort_keys=True),
                "actor": actor_id,
            },
        )
        record_audit(
            conn,
            operation=RESTORE_VALIDATE,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            result_reference=restore_id,
            request_id=request_id,
            result_payload={
                "schema_version": 1,
                "restore_id": restore_id,
                "status": "staged",
                "confirmation_digest": digest,
            },
            result_status=200,
        )
    return {
        "restore_id": restore_id,
        "status": "staged",
        "confirmation_digest": digest,
        "report": report,
        "error": None,
        "code": None,
        "created": True,
    }


def get_restore(conn: Connection, restore_id: str) -> dict[str, Any] | None:
    """Return a restore row with read-time expired/superseded flags."""
    row = (
        conn.execute(
            text(
                "SELECT id, status, manifest, error, confirmation_digest, "
                "expires_at, created_at FROM recovery_jobs "
                "WHERE kind = 'restore' AND id = CAST(:id AS uuid)"
            ),
            {"id": restore_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    expires_at = row["expires_at"]
    expired = bool(expires_at is not None and expires_at <= utc_now())
    superseded = bool(
        conn.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM recovery_jobs "
                "WHERE kind = 'restore' AND status = 'succeeded' "
                "AND created_at > :created)"
            ),
            {"created": row["created_at"]},
        ).scalar()
    )
    manifest = row["manifest"]
    if isinstance(manifest, str):
        manifest = json.loads(manifest)
    return {
        "restore_id": str(row["id"]),
        "status": _stored_status(str(row["status"])),
        "confirmation_digest": row["confirmation_digest"],
        "expired": expired,
        "superseded": superseded,
        "report": manifest,
        "error": row["error"],
    }
