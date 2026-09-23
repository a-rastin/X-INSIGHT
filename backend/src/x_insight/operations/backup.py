"""Consistent full-backup job lifecycle + archive builder (S54 slice 1, T10).

A backup is one ``recovery_jobs`` row plus a zip archive staged on local
disk. Creation (with idempotent replay) and its ``backup.create`` audit row
commit atomically in the caller's transaction; the archive itself is built
by a daemon thread in ``build_backup`` from a single ``REPEATABLE READ``
snapshot so concurrent chart work cannot produce a mixed archive.

Portable archives never contain usable sessions (the ``sessions`` table is
excluded and sessions are revoked on restore regardless) or the deployment
encryption key (only provider key *ciphertext* is included; the manifest
explains re-entry). No secrets or password hashes are logged or returned.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import threading
from datetime import date, datetime
from decimal import Decimal
from importlib import metadata as _metadata
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from x_insight import db
from x_insight.contracts import canonical_json, to_utc_z, utc_now
from x_insight.operations.audit import BACKUP_CREATE, BACKUP_DOWNLOAD, record_audit

try:
    APP_VERSION = _metadata.version("x-insight")
except _metadata.PackageNotFoundError:
    APP_VERSION = "0.1.0"

# Archive bound (contracts.MAX_BODY_BYTES style constant): downloads are
# authenticated admin-only, private/no-store, and served from local staging.
MAX_BACKUP_ARCHIVE_BYTES = 512 * 1024 * 1024

# Single concurrent build; extra creates fail admission with 429 (S54).
_BUILD_SEMAPHORE = threading.Semaphore(1)


class BackupConflict(Exception):
    """Same Idempotency-Key reused with a different request body (HTTP 409)."""


class _ArchiveTooLarge(Exception):
    """Built archive exceeds MAX_BACKUP_ARCHIVE_BYTES."""


# Every portable domain table. ``sessions`` is deliberately absent (plan
# 10.2: excluded from portable recovery). ``users`` carries an explicit
# safe column list: no password hash or session secret ever enters an
# archive. ``network_versions.xml`` bytea is exported twice: base64 inside
# the JSON row dump plus exact original bytes under artifacts/networks/.
_TABLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("audit_events", "*"),
    ("ddi_dataset_releases", "*"),
    ("deployment_state", "*"),
    ("encounter_addenda", "*"),
    ("encounter_notes", "*"),
    ("encounters", "*"),
    ("mcp_question_grants", "*"),
    ("model_bundle_events", "*"),
    ("model_bundle_pointers", "*"),
    ("network_versions", "*"),
    ("networks", "*"),
    ("patients", "*"),
    ("provider_config_pointer", "*"),
    ("provider_configs", "*"),
    ("queue_fairness", "*"),
    ("reasoning_attempts", "*"),
    ("reasoning_jobs", "*"),
    ("run_proposals", "*"),
    ("run_question_artifacts", "*"),
    ("run_questions", "*"),
    ("runs", "*"),
    ("secondary_plan_revisions", "*"),
    ("signed_snapshots", "*"),
    (
        "users",
        "id, username, role, active, theme, credential_revision",
    ),
)

_SAFE_USER_COLUMNS = frozenset(
    {"id", "username", "role", "active", "theme", "credential_revision"}
)


def staging_dir() -> str:
    """Return the backup staging directory (created on demand by builds)."""
    configured = os.environ.get("X_INSIGHT_BACKUP_DIR")
    if configured:
        return configured
    backend_dir = Path(__file__).resolve().parents[3]
    return str(backend_dir / "var" / "backups")


def try_acquire_build_slot() -> bool:
    """Non-blocking single-build admission check (False means HTTP 429)."""
    return _BUILD_SEMAPHORE.acquire(blocking=False)


def release_build_slot() -> None:
    """Release a previously acquired build slot."""
    _BUILD_SEMAPHORE.release()


def _deployment_generation(conn: Connection) -> int | None:
    try:
        value = conn.execute(
            text("SELECT generation FROM deployment_state WHERE id = 1")
        ).scalar()
    except Exception:
        return None
    return int(value) if value is not None else None


def create_backup_job(
    conn: Connection,
    *,
    actor_id: str,
    idempotency_key: str,
    request_hash: str,
    request_id: str,
) -> dict[str, Any]:
    """Insert a queued backup job, or replay the original same-key request.

    Same key + same hash returns ``{"job_id", "status", "created": False}``;
    same key + changed hash raises :class:`BackupConflict` (caller maps to
    409). The ``backup.create`` audit row commits in the same transaction.
    """
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {
            "scope": canonical_json(
                {
                    "actor_id": actor_id,
                    "operation": BACKUP_CREATE,
                    "idempotency_key": idempotency_key,
                }
            ).decode()
        },
    )
    existing = (
        conn.execute(
            text(
                "SELECT id, status, request_hash FROM recovery_jobs "
                "WHERE created_by = CAST(:actor AS uuid) "
                "AND idempotency_key = :key"
            ),
            {"actor": actor_id, "key": idempotency_key},
        )
        .mappings()
        .first()
    )
    if existing is not None:
        if str(existing["request_hash"]) != request_hash:
            raise BackupConflict("Idempotency key was used for another request.")
        return {
            "job_id": str(existing["id"]),
            "status": str(existing["status"]),
            "created": False,
        }
    try:
        row = (
            conn.execute(
                text(
                    "INSERT INTO recovery_jobs "
                    "(kind, status, idempotency_key, request_hash, "
                    " created_by, deployment_generation) "
                    "VALUES ('backup', 'queued', :key, :hash, "
                    " CAST(:actor AS uuid), :generation) "
                    "RETURNING id, status"
                ),
                {
                    "key": idempotency_key,
                    "hash": request_hash,
                    "actor": actor_id,
                    "generation": _deployment_generation(conn),
                },
            )
            .mappings()
            .one()
        )
    except IntegrityError:
        raced = (
            conn.execute(
                text(
                    "SELECT id, status, request_hash FROM recovery_jobs "
                    "WHERE created_by = CAST(:actor AS uuid) "
                    "AND idempotency_key = :key"
                ),
                {"actor": actor_id, "key": idempotency_key},
            )
            .mappings()
            .first()
        )
        if raced is None or str(raced["request_hash"]) != request_hash:
            raise BackupConflict(
                "Idempotency key was used for another request."
            ) from None
        return {
            "job_id": str(raced["id"]),
            "status": str(raced["status"]),
            "created": False,
        }
    job_id = str(row["id"])
    record_audit(
        conn,
        operation=BACKUP_CREATE,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        result_reference=job_id,
        request_id=request_id,
        result_payload={"schema_version": 1, "job_id": job_id, "status": "queued"},
        result_status=202,
    )
    return {"job_id": job_id, "status": str(row["status"]), "created": True}


def get_job(conn: Connection, job_id: str) -> dict[str, Any] | None:
    """Return the backup job row as a plain dict, or None when missing."""
    row = (
        conn.execute(
            text("SELECT * FROM recovery_jobs WHERE id = CAST(:id AS uuid)"),
            {"id": job_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    item = dict(row)
    item["id"] = str(item["id"])
    if item.get("created_by") is not None:
        item["created_by"] = str(item["created_by"])
    return item


def record_download_audit(
    conn: Connection, *, actor_id: str, job_id: str, request_id: str
) -> str:
    """Append the ``backup.download`` audit event in the ambient transaction."""
    return record_audit(
        conn,
        operation=BACKUP_DOWNLOAD,
        actor_id=actor_id,
        result_reference=job_id,
        request_id=request_id,
        result_payload={"schema_version": 1, "job_id": job_id},
        result_status=200,
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite numeric value in backup snapshot.")
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"base64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, datetime):
        return to_utc_z(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def _read_snapshot(database_url: str) -> dict[str, Any]:
    """Read every portable table inside one REPEATABLE READ transaction."""
    engine = db.get_engine(database_url)
    conn = engine.connect()
    try:
        conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        tables: dict[str, list[dict[str, Any]]] = {}
        for table, columns in _TABLE_COLUMNS:
            rows = conn.execute(text(f"SELECT {columns} FROM {table}")).mappings().all()
            dumped = []
            for raw in rows:
                item = {key: _jsonable(val) for key, val in dict(raw).items()}
                if table == "users":
                    item = {
                        key: val
                        for key, val in item.items()
                        if key in _SAFE_USER_COLUMNS
                    }
                dumped.append(item)
            tables[table] = dumped
        revision = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        generation = conn.execute(
            text("SELECT generation FROM deployment_state WHERE id = 1")
        ).scalar()
        return {
            "tables": tables,
            "db_schema_revision": str(revision),
            "deployment_generation": int(generation)
            if generation is not None
            else None,
        }
    finally:
        conn.close()


def _write_archive(
    partial_path: str, job_id: str, snapshot: dict[str, Any]
) -> dict[str, Any]:
    """Write the zip to ``*.partial``; return the manifest (sans self-hash)."""
    import zipfile

    tables: dict[str, list[dict[str, Any]]] = snapshot["tables"]
    created = to_utc_z(utc_now())
    files: list[dict[str, Any]] = []
    table_inventory: dict[str, dict[str, Any]] = {}

    def _add(path: str, payload: bytes) -> None:
        archive.writestr(path, payload)
        files.append(
            {
                "path": path,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        )

    with zipfile.ZipFile(partial_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for table in sorted(tables):
            payload = json.dumps(tables[table], sort_keys=True).encode("utf-8")
            _add(f"database/{table}.json", payload)
            table_inventory[table] = {
                "rows": len(tables[table]),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        for version in tables.get("network_versions", []):
            raw = version.get("xml")
            if isinstance(raw, dict) and "base64" in raw:
                _add(
                    f"artifacts/networks/{version.get('id')}.xml",
                    base64.b64decode(raw["base64"]),
                )
        for artifact in tables.get("run_question_artifacts", []):
            effective = artifact.get("effective_xml")
            if isinstance(effective, str) and effective:
                _add(
                    f"artifacts/effective/{artifact.get('id')}.xml",
                    effective.encode("utf-8"),
                )
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "backup_id": job_id,
            "timestamp": created,
            "created_at": created,
            "app_version": APP_VERSION,
            "db_schema_revision": snapshot["db_schema_revision"],
            "deployment_generation": snapshot["deployment_generation"],
            "tables": table_inventory,
            "files": files,
            "coverage": {
                "patient_ids": [row.get("id") for row in tables.get("patients", [])],
                "encounter_ids": [
                    row.get("id") for row in tables.get("encounters", [])
                ],
                "network_version_sha256": [
                    row.get("sha256") for row in tables.get("network_versions", [])
                ],
                "ddi_versions": [
                    row.get("version") for row in tables.get("ddi_dataset_releases", [])
                ],
                "provider_revisions": [
                    row.get("revision") for row in tables.get("provider_configs", [])
                ],
            },
            "excludes": ["sessions", "deployment_encryption_key"],
            "key_reentry_note": (
                "Provider credentials are stored as ciphertext only; the "
                "deployment encryption key (X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY) "
                "is never included in a backup archive. Restoring on a "
                "deployment without the original key requires key re-entry; "
                "affected provider revisions stay unreadable until then."
            ),
        }
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
    return manifest


def _mark_running(database_url: str, job_id: str) -> None:
    with db.transaction(database_url) as conn:
        conn.execute(
            text("UPDATE recovery_jobs SET status = 'running' WHERE id = :id"),
            {"id": job_id},
        )


def _mark_succeeded(
    database_url: str, job_id: str, archive_path: str, manifest: dict[str, Any]
) -> None:
    with db.transaction(database_url) as conn:
        conn.execute(
            text(
                "UPDATE recovery_jobs SET status = 'succeeded', "
                "archive_path = :path, manifest = CAST(:manifest AS jsonb), "
                "completed_at = now() WHERE id = :id"
            ),
            {
                "id": job_id,
                "path": archive_path,
                "manifest": json.dumps(manifest, sort_keys=True),
            },
        )


def _mark_failed(database_url: str, job_id: str, error: str) -> None:
    try:
        with db.transaction(database_url) as conn:
            conn.execute(
                text(
                    "UPDATE recovery_jobs SET status = 'failed', error = :error, "
                    "completed_at = now() WHERE id = :id"
                ),
                {"id": job_id, "error": error[:1000]},
            )
    except Exception:
        pass


def build_backup(job_id: str, *, staging_dir: str, database_url: str) -> None:
    """Build the archive for a queued job; never raises to the spawner.

    On success the row becomes ``succeeded`` with manifest + archive path.
    On any exception the row becomes ``failed`` with error text and no
    complete downloadable archive is left behind.
    """
    partial = os.path.join(staging_dir, f"backup-{job_id}.zip.partial")
    final = os.path.join(staging_dir, f"backup-{job_id}.zip")
    try:
        os.makedirs(staging_dir, exist_ok=True)
        _mark_running(database_url, job_id)
        snapshot = _read_snapshot(database_url)
        manifest = _write_archive(partial, job_id, snapshot)
        if os.path.getsize(partial) > MAX_BACKUP_ARCHIVE_BYTES:
            raise _ArchiveTooLarge(
                f"Backup archive exceeds {MAX_BACKUP_ARCHIVE_BYTES} bytes."
            )
        os.rename(partial, final)
        _mark_succeeded(database_url, job_id, final, manifest)
    except Exception as exc:
        for stale in (partial, final):
            try:
                if os.path.exists(stale):
                    os.remove(stale)
            except OSError:
                pass
        _mark_failed(database_url, job_id, f"{type(exc).__name__}: {exc}")
