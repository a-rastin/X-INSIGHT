"""Restore validation + isolated staging (S55 slice 1, seams T10+T1).

``validate_and_stage`` checks a backup zip WITHOUT touching live domain
tables, extracts the verified files into an isolated staging directory, and
records one ``kind='restore'`` ``recovery_jobs`` row plus its
``restore.validate`` audit row in a single transaction. Archive content is
never executed as SQL/Python and never echoed into errors or audit rows.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import secrets
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
from x_insight.operations.audit import (
    RESTORE_COMMIT,
    RESTORE_VALIDATE,
    record_audit,
)
from x_insight.operations.backup import APP_VERSION

MAX_RESTORE_UPLOAD_BYTES = int(
    os.environ.get("X_INSIGHT_RESTORE_MAX_UPLOAD_BYTES", 64 * 1024 * 1024)
)
MAX_RESTORE_EXPANDED_BYTES = int(
    os.environ.get("X_INSIGHT_RESTORE_MAX_EXPANDED_BYTES", 512 * 1024 * 1024)
)
MAX_RESTORE_FILES = int(os.environ.get("X_INSIGHT_RESTORE_MAX_FILES", 5000))

STAGING_TTL_SECONDS = 1800

RESTORE_FAIL_BEFORE_SWITCH = False
RESTORE_FAIL_DURING_RESTART = False
RESTORE_FAIL_AT_HEALTH = False


def _fail_point(suffix: str) -> bool:
    """Return True when a slice-4 failure flag is armed for ``suffix``.

    Armed when ``X_INSIGHT_RESTORE_FAIL_<suffix>`` is ``"1"`` or the
    same-suffix module global ``RESTORE_FAIL_<suffix>`` is truthy (the
    test mirror patched with ``raising=False``).
    """
    if os.environ.get(f"X_INSIGHT_RESTORE_FAIL_{suffix}") == "1":
        return True
    return bool(globals().get(f"RESTORE_FAIL_{suffix}"))


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
                "expires_at, created_at, pre_restore_backup_id, commit_error "
                "FROM recovery_jobs "
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
    commit_info: dict[str, Any] | None = None
    if isinstance(manifest, dict):
        raw_commit = manifest.get("commit")
        if isinstance(raw_commit, dict):
            commit_info = raw_commit
    status = _stored_status(str(row["status"]))
    if commit_info is not None:
        marker = str(commit_info.get("status") or "committed")
        status = marker if marker in ("committing", "committed") else "committed"
    pre_id = row["pre_restore_backup_id"]
    if not pre_id and commit_info is not None:
        pre_id = commit_info.get("pre_restore_backup_id")
    return {
        "restore_id": str(row["id"]),
        "status": status,
        "confirmation_digest": row["confirmation_digest"],
        "expired": expired,
        "superseded": superseded,
        "report": manifest,
        "error": row["error"],
        "pre_restore_backup_id": str(pre_id) if pre_id else None,
        "commit": commit_info,
        "commit_error": row["commit_error"],
    }


def maintenance_path() -> str:
    """Return the file-based maintenance flag path (independent of either DB)."""
    configured = os.environ.get("X_INSIGHT_MAINTENANCE_FILE")
    if configured:
        return configured
    backend_dir = Path(__file__).resolve().parents[3]
    return str(backend_dir / "var" / "maintenance.json")


def recovery_log_path() -> str:
    """Return the external operator recovery log path (JSON lines, outside DB)."""
    configured = os.environ.get("X_INSIGHT_RECOVERY_LOG")
    if configured:
        return configured
    backend_dir = Path(__file__).resolve().parents[3]
    return str(backend_dir / "var" / "recovery-operator.log")


def maintenance_active() -> bool:
    """Return True when the maintenance flag file marks the app fenced."""
    try:
        raw = Path(maintenance_path()).read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        payload = json.loads(raw)
    except ValueError:
        return False
    return bool(isinstance(payload, dict) and payload.get("active"))


def enter_maintenance(
    reason: str, restore_id: str, generation: int | None = None
) -> dict[str, Any]:
    """Enter file-based maintenance fencing for a restore commit."""
    path = Path(maintenance_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "active": True,
        "restore_id": str(restore_id),
        "reason": str(reason),
        "started_at": to_utc_z(utc_now()),
        "generation": generation,
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return payload


def exit_maintenance() -> None:
    """Clear the file-based maintenance flag (best effort)."""
    try:
        Path(maintenance_path()).unlink(missing_ok=True)
    except OSError:
        pass


def clear_caches() -> dict[str, Any]:
    """Clear process-local caches after a restore commit (S56 slice 3).

    Honest inventory: backend ``src`` carries no ``functools.lru_cache``
    and no module-level patient-data dicts (verified by source search);
    assessment/DDI/model content is read per request from released files
    and DB rows, never cached in process. The only process-local cache is
    the SQLAlchemy engine pool in :mod:`x_insight.db`, disposed here so
    post-commit checkouts observe replaced rows.
    """
    from x_insight import db as _db

    _db.dispose_engines()
    return {"engines_disposed": True, "lru_caches": [], "dict_caches": []}


def _append_operator_log(entry: dict[str, Any]) -> None:
    path = Path(recovery_log_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def _bump_generation(conn: Connection) -> int:
    row = conn.execute(
        text(
            "INSERT INTO deployment_state (id, generation) VALUES (1, 2) "
            "ON CONFLICT (id) DO UPDATE "
            "SET generation = deployment_state.generation + 1 "
            "RETURNING generation"
        )
    ).scalar()
    return int(row) if row is not None else 2


def _commit_manifest(
    manifest: dict[str, Any],
    *,
    pre_restore_backup_id: str,
    confirmation_digest: str,
    generation: int,
    committed_at: str,
    phases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    updated = dict(manifest)
    updated["commit"] = {
        "status": "committed",
        "pre_restore_backup_id": pre_restore_backup_id,
        "committed_at": committed_at,
        "confirmation_digest": confirmation_digest,
        "generation": generation,
        "phases": phases or [],
    }
    return updated


_PG_CAST_MAP = {
    "bool": "boolean",
    "int4": "integer",
    "int8": "bigint",
    "int2": "smallint",
    "text": "text",
    "varchar": "text",
    "bpchar": "text",
    "uuid": "uuid",
    "timestamptz": "timestamptz",
    "timestamp": "timestamp",
    "jsonb": "jsonb",
    "json": "json",
    "bytea": "bytea",
    "date": "date",
    "numeric": "numeric",
}


def _pg_cast(udt_name: str) -> str:
    """Map an information_schema udt_name to a CAST target."""
    return _PG_CAST_MAP.get(udt_name, "text")


def _to_param(value: Any, udt_name: str) -> Any:
    """Inverse of backup._jsonable for one column value (parametrized INSERT).

    Bytea arrives as ``{"base64": ...}`` (only decoded for bytea columns so
    a genuine JSONB ``{"base64": ...}`` dict is never mis-decoded); JSONB/JSON
    dicts/lists are serialized to JSON text for ``CAST (... AS jsonb)``;
    datetimes/UUIDs stay ISO/hex strings for Postgres to coerce.
    """
    if value is None:
        return None
    if udt_name == "bytea":
        if isinstance(value, dict) and set(value.keys()) == {"base64"}:
            return base64.b64decode(value["base64"])
        if isinstance(value, str):
            return value.encode("utf-8")
        return bytes(value)
    if udt_name in ("jsonb", "json"):
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return value
    return value


def _apply_snapshot_tables(
    *, database_url: str, tables: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    """Replace live domain tables from an in-memory ``database/*.json`` map.

    Shared by the staged switch and the slice-4 rollback path: the single
    write transaction below is atomic for the switch itself (TRUNCATE +
    INSERTs all-or-nothing), which is the replacement (never merge)
    semantic. ``deployment_state`` is never truncated here; generation is
    managed separately so the fenced bump (or its rollback restore) stays
    explicit.
    """
    staged = tables
    with db.transaction(database_url) as conn:
        live_hashes = {
            str(row["id"]): str(row["password_hash"])
            for row in conn.execute(text("SELECT id, password_hash FROM users"))
            .mappings()
            .all()
        }
        live_sessions = [
            dict(row)
            for row in conn.execute(text("SELECT * FROM sessions")).mappings().all()
        ]
        col_types: dict[str, dict[str, str]] = {}
        for table in staged:
            if table == "deployment_state":
                continue
            col_rows = (
                conn.execute(
                    text(
                        "SELECT column_name, udt_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = :t"
                    ),
                    {"t": table},
                )
                .mappings()
                .all()
            )
            col_types[table] = {
                str(r["column_name"]): str(r["udt_name"]) for r in col_rows
            }
        sess_cols = (
            conn.execute(
                text(
                    "SELECT column_name, udt_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'sessions'"
                )
            )
            .mappings()
            .all()
        )
        session_types = {str(r["column_name"]): str(r["udt_name"]) for r in sess_cols}
    # Phase B write: explicit replacement in its own transaction (separate
    # from pre-backup and from the audit-commit transaction below).
    # TRUNCATE ... CASCADE handles the patients/encounters/notes FK chain;
    # sessions is cascade-wiped by the users FK and restored afterwards
    # (slice 3 revokes); recovery_jobs/alembic_version are never touched;
    # deployment_state keeps its live (fenced, bumped) generation.
    truncate_list = [t for t in staged if t != "deployment_state"]
    placeholder_ids: list[str] = []
    staged_user_ids = {
        str(row.get("id")) for row in staged.get("users", []) if row.get("id")
    }
    sessions_preserved = 0
    sessions_dropped = 0
    with db.transaction(database_url) as conn:
        if truncate_list:
            conn.execute(text(f"TRUNCATE TABLE {', '.join(truncate_list)} CASCADE"))
        # FK-safe insert order for the four CASCADE FKs (sessions->users,
        # encounters->patients, notes->encounters+users); all other staged
        # tables carry no FKs. Sessions are restored separately below.
        ordered = (
            [t for t in ("users", "patients") if t in truncate_list]
            + [t for t in ("encounters",) if t in truncate_list]
            + [t for t in ("encounter_notes",) if t in truncate_list]
            + sorted(
                t
                for t in truncate_list
                if t not in ("users", "patients", "encounters", "encounter_notes")
            )
        )
        for table in ordered:
            types = col_types.get(table, {})
            for row in staged.get(table, []):
                if table == "users":
                    uid = str(row.get("id"))
                    preserved = live_hashes.get(uid)
                    if preserved is None:
                        preserved = f"unusable${secrets.token_hex(16)}"
                        placeholder_ids.append(uid)
                    cols = [
                        c for c in row.keys() if c in types and c != "password_hash"
                    ] + (["password_hash"] if "password_hash" in types else [])
                    params: dict[str, Any] = {}
                    casts: list[str] = []
                    for i, col in enumerate(cols):
                        udt = types[col]
                        raw_value = preserved if col == "password_hash" else row[col]
                        params[f"p{i}"] = _to_param(raw_value, udt)
                        casts.append(f"CAST(:p{i} AS {_pg_cast(udt)})")
                    conn.execute(
                        text(
                            f"INSERT INTO {table} ({', '.join(cols)}) "
                            f"VALUES ({', '.join(casts)})"
                        ),
                        params,
                    )
                    continue
                cols = [c for c in row.keys() if c in types]
                if not cols:
                    continue
                params = {}
                casts = []
                for i, col in enumerate(cols):
                    udt = types[col]
                    params[f"p{i}"] = _to_param(row[col], udt)
                    casts.append(f"CAST(:p{i} AS {_pg_cast(udt)})")
                conn.execute(
                    text(
                        f"INSERT INTO {table} ({', '.join(cols)}) "
                        f"VALUES ({', '.join(casts)})"
                    ),
                    params,
                )
        for sess in live_sessions:
            if str(sess.get("user_id")) not in staged_user_ids:
                sessions_dropped += 1
                continue
            cols = [c for c in sess.keys() if c in session_types]
            if not cols:
                continue
            params = {}
            casts = []
            for i, col in enumerate(cols):
                udt = session_types[col]
                value = sess[col]
                if isinstance(value, dict | list) and udt in ("jsonb", "json"):
                    value = json.dumps(value, sort_keys=True)
                params[f"p{i}"] = value
                casts.append(f"CAST(:p{i} AS {_pg_cast(udt)})")
            conn.execute(
                text(
                    f"INSERT INTO sessions ({', '.join(cols)}) "
                    f"VALUES ({', '.join(casts)})"
                ),
                params,
            )
            sessions_preserved += 1
    return {
        "tables": sorted(truncate_list),
        "users_preserved": sum(
            1 for r in staged.get("users", []) if str(r.get("id")) in live_hashes
        ),
        "users_placeholder": placeholder_ids,
        "sessions_preserved": sessions_preserved,
        "sessions_dropped": sessions_dropped,
    }


def _replace_domain_tables(*, database_url: str, staging_path: str) -> dict[str, Any]:
    """Phase B: replace live domain tables from staged ``database/*.json``.

    Multi-phase replacement, NOT one SQL transaction covering the whole
    commit: this helper runs in its own transaction(s), separate from the
    pre-restore backup transactions and from the final audit-commit
    transaction. The single write transaction inside
    :func:`_apply_snapshot_tables` is atomic for the switch itself
    (TRUNCATE + INSERTs all-or-nothing), which is the replacement
    (never merge) semantic.
    """
    from x_insight.operations import backup as backup_ops

    table_names = sorted(t for t, _ in backup_ops._TABLE_COLUMNS)
    base = Path(staging_path) / "database"
    staged: dict[str, list[dict[str, Any]]] = {}
    for table in table_names:
        payload_path = base / f"{table}.json"
        if payload_path.exists():
            raw = json.loads(payload_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                staged[table] = raw
    return _apply_snapshot_tables(database_url=database_url, tables=staged)


def _read_generation(database_url: str) -> int | None:
    with db.transaction(database_url) as conn:
        value = conn.execute(
            text("SELECT generation FROM deployment_state WHERE id = 1")
        ).scalar()
    return int(value) if value is not None else None


def _restore_generation(database_url: str, generation: int | None) -> None:
    if generation is None:
        return
    with db.transaction(database_url) as conn:
        conn.execute(
            text("UPDATE deployment_state SET generation = :g WHERE id = 1"),
            {"g": int(generation)},
        )


def _load_snapshot_tables_from_backup(
    *, database_url: str, pre_backup_id: str
) -> dict[str, list[dict[str, Any]]]:
    """Load ``database/*.json`` row lists from a backup job's zip archive."""
    with db.transaction(database_url) as conn:
        archive_path = conn.execute(
            text("SELECT archive_path FROM recovery_jobs WHERE id = CAST(:id AS uuid)"),
            {"id": pre_backup_id},
        ).scalar()
    if not archive_path or not Path(str(archive_path)).exists():
        raise RestoreRejected(
            "restore_rolled_back",
            "pre-restore backup archive is missing; rollback cannot verify",
        )
    tables: dict[str, list[dict[str, Any]]] = {}
    with zipfile.ZipFile(str(archive_path)) as archive:
        for name in archive.namelist():
            if not name.startswith("database/") or not name.endswith(".json"):
                continue
            table = name[len("database/") : -len(".json")]
            try:
                rows = json.loads(archive.read(name).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise RestoreRejected(
                    "restore_rolled_back",
                    "pre-restore backup archive is unreadable; rollback aborted",
                ) from exc
            if isinstance(rows, list):
                tables[table] = [r for r in rows if isinstance(r, dict)]
    if not tables:
        raise RestoreRejected(
            "restore_rolled_back",
            "pre-restore backup archive is empty; rollback aborted",
        )
    return tables


def _post_replace_fencing(*, database_url: str) -> dict[str, int]:
    """Phase B2: revoke sessions/grants, cancel nonterminal work (S56 slice 3).

    Runs AFTER phase B replacement in its own transaction -- separate from
    the replacement transaction(s) and from the audit-commit transaction
    below (multi-phase replacement, not one SQL transaction). Portable
    archives never carry usable sessions, but live sessions were preserved
    across the switch; all are revoked here so pre-commit cookies die.
    Restored nonterminal runs/jobs are marked ``cancelled`` for explicit
    restart (history preserved, no deletes).
    """
    from x_insight.reasoning.queue import ACTIVE_RUN_STATUSES

    active = ", ".join(f"'{status}'" for status in sorted(ACTIVE_RUN_STATUSES))
    with db.transaction(database_url) as conn:
        sessions = (
            conn.execute(
                text("UPDATE sessions SET revoked_at = now() WHERE revoked_at IS NULL")
            ).rowcount
            or 0
        )
        grants = (
            conn.execute(
                text(
                    "UPDATE mcp_question_grants SET revoked_at = now(), "
                    "updated_at = now() WHERE revoked_at IS NULL"
                )
            ).rowcount
            or 0
        )
        runs = (
            conn.execute(
                text(
                    "UPDATE runs SET status = 'cancelled', updated_at = now() "
                    f"WHERE status IN ({active})"
                )
            ).rowcount
            or 0
        )
        jobs = (
            conn.execute(
                text(
                    "UPDATE reasoning_jobs SET status = 'cancelled', "
                    "lease_token = NULL, lease_deadline = NULL, updated_at = now() "
                    "WHERE status IN ('queued', 'claimed')"
                )
            ).rowcount
            or 0
        )
    return {
        "revoked_sessions": int(sessions),
        "revoked_grants": int(grants),
        "cancelled_runs": int(runs),
        "cancelled_jobs": int(jobs),
    }


def _check_commit_ready(
    conn: Connection, restore_id: str, confirmation_digest: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load a staged restore row (FOR UPDATE) and verify commit preconditions.

    Returns ``(row_dict, manifest)``. Raises :class:`RestoreRejected` for
    stale/not-staged/expired/superseded/digest problems.
    """
    row = (
        conn.execute(
            text(
                "SELECT * FROM recovery_jobs "
                "WHERE kind = 'restore' AND id = CAST(:id AS uuid) FOR UPDATE"
            ),
            {"id": restore_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise RestoreRejected("not_found", "restore job not found")
    manifest = row["manifest"]
    if isinstance(manifest, str):
        manifest = json.loads(manifest)
    if not isinstance(manifest, dict):
        raise RestoreRejected("not_staged", "restore is not staged")
    commit_info = manifest.get("commit")
    if isinstance(commit_info, dict):
        raise RestoreRejected(
            "already_committed", "restore already committed; digest fenced"
        )
    if str(row["status"]) != "succeeded":
        raise RestoreRejected("not_staged", "restore is not staged")
    expires_at = row["expires_at"]
    if bool(expires_at is not None and expires_at <= utc_now()):
        raise RestoreRejected("expired", "confirmation digest expired")
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
    if superseded:
        raise RestoreRejected("superseded", "confirmation digest superseded")
    if str(row["confirmation_digest"]) != confirmation_digest:
        raise RestoreRejected("stale_confirmation", "confirmation digest mismatch")
    return dict(row), manifest


def commit_restore(
    *,
    restore_id: str,
    confirmation_digest: str,
    actor_id: str,
    idempotency_key: str,
    request_hash: str,
    request_id: str,
    database_url: str,
) -> dict[str, Any] | None:
    """Commit a staged restore: fence, pre-backup, phased switch, mark committed.

    Phased switch (slice 2), AFTER the pre-restore backup and BEFORE marking
    committed: phase A quiesce via the maintenance file, phase B replace
    domain tables from staged ``database/*.json``, phase C coordinated
    restart signal (dispose engines + record generation; no real second
    process in tests -- process restart is an S57 deploy concern, observed
    here via maintenance + generation). Replacement runs in its own
    transaction(s), separate from pre-backup and from the audit-commit
    transaction below: multi-phase replacement, not a single SQL transaction
    claim. Same key + same hash replays; same key + different hash raises.
    """

    def _scope() -> str:
        return canonical_json(
            {
                "actor_id": actor_id,
                "operation": RESTORE_COMMIT,
                "idempotency_key": idempotency_key,
            }
        ).decode()

    def _prior_audit(conn: Connection) -> Any | None:
        return (
            conn.execute(
                text(
                    "SELECT request_hash, result_payload, result_reference "
                    "FROM audit_events WHERE actor_id = :actor "
                    "AND operation = :operation AND idempotency_key = :key"
                ),
                {
                    "actor": actor_id,
                    "operation": RESTORE_COMMIT,
                    "key": idempotency_key,
                },
            )
            .mappings()
            .first()
        )

    def _replay(payload: Any) -> dict[str, Any]:
        result: dict[str, Any] = dict(payload) if isinstance(payload, dict) else {}
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except ValueError:
                parsed = {}
            if isinstance(parsed, dict):
                result = parsed
        result["created"] = False
        return result

    with db.transaction(database_url) as conn:
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": _scope()},
        )
        prior = _prior_audit(conn)
        if prior is not None:
            if str(prior["request_hash"]) != request_hash or str(
                prior["result_reference"]
            ) != str(restore_id):
                raise RestoreConflict("Idempotency key was used for another request.")
            return _replay(prior["result_payload"])
        exists = conn.execute(
            text(
                "SELECT id FROM recovery_jobs WHERE kind = 'restore' "
                "AND id = CAST(:id AS uuid)"
            ),
            {"id": restore_id},
        ).first()
        if exists is None:
            return None
        # Validate without holding the row lock across side effects.
        _check_commit_ready(conn, str(restore_id), confirmation_digest)

    from x_insight.operations import backup as backup_ops

    pre_generation = _read_generation(database_url)
    enter_maintenance("restore_commit", str(restore_id))
    with db.transaction(database_url) as conn:
        new_generation = _bump_generation(conn)
    enter_maintenance("restore_commit", str(restore_id), generation=new_generation)

    backup_key = f"pre-restore-{restore_id}"[:128]
    backup_hash = hashlib.sha256(
        canonical_json({"pre_restore_for": str(restore_id)})
    ).hexdigest()
    with db.transaction(database_url) as conn:
        try:
            created = backup_ops.create_backup_job(
                conn,
                actor_id=actor_id,
                idempotency_key=backup_key,
                request_hash=backup_hash,
                request_id=request_id,
            )
        except backup_ops.BackupConflict as exc:
            raise RestoreRejected(
                "pre_backup_conflict",
                "pre-restore backup key conflict; confirmation digest fenced",
            ) from exc
        pre_backup_id = str(created["job_id"])
    backup_ops.build_backup(
        pre_backup_id,
        staging_dir=backup_ops.staging_dir(),
        database_url=database_url,
    )
    with db.transaction(database_url) as conn:
        status = conn.execute(
            text("SELECT status FROM recovery_jobs WHERE id = CAST(:id AS uuid)"),
            {"id": pre_backup_id},
        ).scalar()
        if str(status) != "succeeded":
            exit_maintenance()
            raise RestoreRejected(
                "pre_backup_failed",
                "pre-restore backup failed; confirmation digest fenced",
            )

    def _rollback_to_pre_restore(fail_phase: str) -> None:
        """Re-apply the pre-restore backup, hold maintenance, mark staged."""
        detail = (
            f"restore {fail_phase}; rolled back to pre-restore backup {pre_backup_id}"
        )
        try:
            snapshot_tables = _load_snapshot_tables_from_backup(
                database_url=database_url, pre_backup_id=pre_backup_id
            )
            _apply_snapshot_tables(database_url=database_url, tables=snapshot_tables)
        except RestoreRejected:
            pass
        except Exception:
            pass
        try:
            _restore_generation(database_url, pre_generation)
        except Exception:
            pass
        try:
            clear_caches()
        except Exception:
            pass
        # Keep maintenance ACTIVE with the restored generation.
        try:
            enter_maintenance(
                "restore_commit", str(restore_id), generation=pre_generation
            )
        except Exception:
            pass
        try:
            with db.transaction(database_url) as conn:
                row = (
                    conn.execute(
                        text(
                            "SELECT manifest FROM recovery_jobs "
                            "WHERE id = CAST(:id AS uuid)"
                        ),
                        {"id": str(restore_id)},
                    )
                    .mappings()
                    .first()
                )
                manifest_obj: dict[str, Any] = {}
                if row is not None:
                    raw_manifest = row["manifest"]
                    if isinstance(raw_manifest, str):
                        try:
                            raw_manifest = json.loads(raw_manifest)
                        except ValueError:
                            raw_manifest = {}
                    if isinstance(raw_manifest, dict):
                        manifest_obj = dict(raw_manifest)
                        manifest_obj.pop("commit", None)
                manifest_obj["pre_restore_backup_id"] = pre_backup_id
                conn.execute(
                    text(
                        "UPDATE recovery_jobs SET pre_restore_backup_id = :pre, "
                        "commit_error = :err, "
                        "manifest = CAST(:manifest AS jsonb) "
                        "WHERE id = CAST(:id AS uuid)"
                    ),
                    {
                        "pre": pre_backup_id,
                        "err": f"restore_rolled_back: {detail}"[:1000],
                        "manifest": json.dumps(manifest_obj, sort_keys=True),
                        "id": str(restore_id),
                    },
                )
        except Exception:
            pass
        try:
            _append_operator_log(
                {
                    "event": RESTORE_COMMIT,
                    "outcome": "rolled_back",
                    "restore_id": str(restore_id),
                    "actor_id": actor_id,
                    "pre_restore_backup_id": pre_backup_id,
                    "generation": pre_generation,
                    "deployment_generation": pre_generation,
                    "request_id": request_id,
                    "fail_phase": fail_phase,
                    "commit_error": "restore_rolled_back",
                }
            )
        except Exception:
            pass
        raise RestoreRejected("restore_rolled_back", detail)

    if _fail_point("BEFORE_SWITCH"):
        _rollback_to_pre_restore("BEFORE_SWITCH")

    committed_at = to_utc_z(utc_now())
    # Phase A (quiesce) already holds via the maintenance file above.
    # Phase B: explicit table replacement in its own transaction(s),
    # separate from pre-backup and from the audit-commit transaction below;
    # multi-phase replacement, not a single SQL transaction claim.
    with db.transaction(database_url) as conn:
        staging_path = conn.execute(
            text("SELECT staging_path FROM recovery_jobs WHERE id = CAST(:id AS uuid)"),
            {"id": str(restore_id)},
        ).scalar()
    if not staging_path:
        exit_maintenance()
        raise RestoreRejected("not_staged", "restore staging is missing")
    try:
        replace_summary = _replace_domain_tables(
            database_url=database_url, staging_path=str(staging_path)
        )
    except Exception as exc:
        if isinstance(exc, RestoreRejected):
            raise
        exit_maintenance()
        raise RestoreRejected(
            "replacement_failed",
            "staged replacement failed; confirmation digest fenced",
        ) from exc
    # Phase C: coordinated restart signal + process-local cache clear.
    # Dispose cached engines so the next checkout observes replaced rows
    # under the fenced generation; no real second process exists in tests --
    # process restart is an S57 concern. clear_caches documents the honest
    # cache inventory (engine pool only; no lru/dict patient-data caches).
    try:
        fencing_summary = _post_replace_fencing(database_url=database_url)
    except Exception as exc:
        exit_maintenance()
        raise RestoreRejected(
            "post_replace_failed",
            "post-replacement revoke/cancel failed; confirmation digest fenced",
        ) from exc
    cache_report = clear_caches()
    if _fail_point("DURING_RESTART"):
        _rollback_to_pre_restore("DURING_RESTART")
    phases: list[dict[str, Any]] = [
        {"phase": "quiesce", "status": "ok", "maintenance": True},
        {
            "phase": "replace",
            "status": "ok",
            "tables": replace_summary["tables"],
            "users_preserved": replace_summary["users_preserved"],
            "users_placeholder": replace_summary["users_placeholder"],
            "sessions_preserved": replace_summary["sessions_preserved"],
            "sessions_dropped": replace_summary["sessions_dropped"],
            "deployment_generation_kept": new_generation,
        },
        {
            "phase": "post_replace",
            "status": "ok",
            "revoked_sessions": fencing_summary["revoked_sessions"],
            "revoked_grants": fencing_summary["revoked_grants"],
            "cancelled_runs": fencing_summary["cancelled_runs"],
            "cancelled_jobs": fencing_summary["cancelled_jobs"],
            "caches_cleared": cache_report,
            "note": "pre-commit sessions/grants revoked; restored nonterminal "
            "work cancelled for explicit restart; process-local caches cleared",
        },
        {
            "phase": "restart_signal",
            "status": "ok",
            "generation": new_generation,
            "note": "engines disposed; process restart is an S57 concern",
        },
    ]
    with db.transaction(database_url) as conn:
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": _scope()},
        )
        raced = _prior_audit(conn)
        if raced is not None:
            if str(raced["request_hash"]) != request_hash or str(
                raced["result_reference"]
            ) != str(restore_id):
                raise RestoreConflict("Idempotency key was used for another request.")
            return _replay(raced["result_payload"])
        _, manifest = _check_commit_ready(conn, str(restore_id), confirmation_digest)
        updated_manifest = _commit_manifest(
            manifest,
            pre_restore_backup_id=pre_backup_id,
            confirmation_digest=confirmation_digest,
            generation=new_generation,
            committed_at=committed_at,
            phases=phases,
        )
        conn.execute(
            text(
                "UPDATE recovery_jobs SET pre_restore_backup_id = :pre, "
                "commit_error = NULL, manifest = CAST(:manifest AS jsonb), "
                "completed_at = now() WHERE id = CAST(:id AS uuid)"
            ),
            {
                "pre": pre_backup_id,
                "manifest": json.dumps(updated_manifest, sort_keys=True),
                "id": str(restore_id),
            },
        )
        payload: dict[str, Any] = {
            "schema_version": 1,
            "restore_id": str(restore_id),
            "status": "committed",
            "confirmation_digest": confirmation_digest,
            "pre_restore_backup_id": pre_backup_id,
        }
        try:
            record_audit(
                conn,
                operation=RESTORE_COMMIT,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                result_reference=str(restore_id),
                request_id=request_id,
                result_payload=payload,
                result_status=202,
            )
        except Exception as exc:
            from sqlalchemy.exc import IntegrityError as _IntegrityError

            if isinstance(exc, _IntegrityError):
                raise RestoreConflict(
                    "Idempotency key was used for another request."
                ) from exc
            raise
    _append_operator_log(
        {
            "event": RESTORE_COMMIT,
            "outcome": "committed",
            "restore_id": str(restore_id),
            "actor_id": actor_id,
            "pre_restore_backup_id": pre_backup_id,
            "generation": new_generation,
            "deployment_generation": new_generation,
            "confirmation_digest": confirmation_digest,
            "archive_sha256": manifest.get("archive_sha256"),
            "request_id": request_id,
            "committed_at": committed_at,
            "phases": phases,
            "users_placeholder": replace_summary["users_placeholder"],
            "sessions_preserved": replace_summary["sessions_preserved"],
            "revoked_sessions": fencing_summary["revoked_sessions"],
            "revoked_grants": fencing_summary["revoked_grants"],
            "cancelled_runs": fencing_summary["cancelled_runs"],
            "cancelled_jobs": fencing_summary["cancelled_jobs"],
            "note": "users keep live password_hash; new staged users get an "
            "unusable placeholder hash; deployment_state keeps the fenced "
            "bumped generation; pre-commit sessions/grants revoked; restored "
            "nonterminal work cancelled for explicit restart",
        }
    )
    return {
        "schema_version": 1,
        "restore_id": str(restore_id),
        "status": "committed",
        "confirmation_digest": confirmation_digest,
        "pre_restore_backup_id": pre_backup_id,
        "created": True,
    }


def _check_reopen_health(*, database_url: str, restore_id: str) -> dict[str, Any]:
    """Minimal verified-read health check before exiting maintenance.

    Reads only: ``SELECT 1``, alembic revision equals
    ``EXPECTED_SCHEMA_REVISION``, deployment generation readable, patients
    table readable with a count, and the recovery row still committed.
    Raises :class:`RestoreRejected` (``unhealthy``/``not_committed``) so the
    caller keeps maintenance active.
    """
    if _fail_point("AT_HEALTH"):
        raise RestoreRejected(
            "unhealthy", "injected health failure; maintenance stays active"
        )
    with db.transaction(database_url) as conn:
        conn.execute(text("SELECT 1"))
        try:
            version = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
        except Exception as exc:
            raise RestoreRejected(
                "unhealthy", "restore target schema revision is unreadable"
            ) from exc
        if version != db.EXPECTED_SCHEMA_REVISION:
            raise RestoreRejected(
                "unhealthy",
                f"restore target schema {version!r} does not match "
                f"live {db.EXPECTED_SCHEMA_REVISION!r}",
            )
        try:
            generation = conn.execute(
                text("SELECT generation FROM deployment_state WHERE id = 1")
            ).scalar()
        except Exception as exc:
            raise RestoreRejected(
                "unhealthy", "restore target deployment state is unreadable"
            ) from exc
        if generation is None:
            raise RestoreRejected(
                "unhealthy", "restore target deployment generation is missing"
            )
        try:
            patients = conn.execute(text("SELECT COUNT(*) FROM patients")).scalar()
        except Exception as exc:
            raise RestoreRejected(
                "unhealthy", "restore target patients table is unreadable"
            ) from exc
        row = get_restore(conn, str(restore_id))
        if row is None:
            raise RestoreRejected("not_found", "restore job not found")
        if row["status"] != "committed":
            if maintenance_active():
                raise RestoreRejected(
                    "unhealthy",
                    "restore is not committed and maintenance is held; reopen refused",
                )
            raise RestoreRejected(
                "not_committed", "restore is not committed; reopen refused"
            )
    return {
        "schema_revision": str(version),
        "deployment_generation": int(generation),
        "patients": int(patients or 0),
        "restore": "committed",
    }


def reopen_restore(
    *,
    restore_id: str,
    actor_id: str,
    idempotency_key: str,
    request_hash: str,
    request_id: str,
    database_url: str,
) -> dict[str, Any] | None:
    """Exit maintenance after verified health checks (S56 slice 3).

    The restore row must already be committed; health checks run first and
    maintenance stays active on failure. Reopening is naturally idempotent
    (clearing the flag file plus read-only checks, no state change beyond
    that), so the required Idempotency-Key is validated at the route but
    needs no replay store here. No audit row is recorded: audit operations
    are fixed (no ``restore.reopen`` without owner approval); the reopen is
    recorded in the external operator log. Old sessions stay revoked -- a
    fresh login is required after commit.
    """
    del idempotency_key, request_hash
    with db.transaction(database_url) as conn:
        exists = conn.execute(
            text(
                "SELECT id FROM recovery_jobs WHERE kind = 'restore' "
                "AND id = CAST(:id AS uuid)"
            ),
            {"id": str(restore_id)},
        ).first()
        if exists is None:
            return None
    health = _check_reopen_health(database_url=database_url, restore_id=str(restore_id))
    exit_maintenance()
    _append_operator_log(
        {
            "event": RESTORE_COMMIT,
            "outcome": "reopened",
            "restore_id": str(restore_id),
            "actor_id": actor_id,
            "request_id": request_id,
            "health": health,
        }
    )
    return {
        "schema_version": 1,
        "restore_id": str(restore_id),
        "status": "reopened",
        "health": health,
    }
