"""Backup + restore-validation HTTP routes (S54 slice 1, S55 slice 1, T10+T1)."""

from __future__ import annotations

import hashlib
import os
import threading
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from x_insight import db
from x_insight.contracts import (
    canonical_json,
    error_body,
    parse_idempotency_key,
)
from x_insight.identity.accounts import require_admin
from x_insight.identity.routes import _request_id
from x_insight.operations import backup, restore

router = APIRouter()

_PRIVATE_NO_STORE = {"Cache-Control": "private, no-store"}


def _build_and_release(job_id: str, staging: str, database_url: str) -> None:
    try:
        backup.build_backup(job_id, staging_dir=staging, database_url=database_url)
    finally:
        backup.release_build_slot()


@router.post("/backups")
def create_backup(request: Request, body: dict[str, Any] | None = None) -> JSONResponse:
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        key = parse_idempotency_key(request.headers)
        if key is None:
            raise HTTPException(422, "A valid Idempotency-Key is required.")
        request_hash = hashlib.sha256(canonical_json(body or {})).hexdigest()
        try:
            result = backup.create_backup_job(
                conn,
                actor_id=str(actor["id"]),
                idempotency_key=key,
                request_hash=request_hash,
                request_id=_request_id(request),
            )
        except backup.BackupConflict as exc:
            raise HTTPException(
                409, "Idempotency key was used for another request."
            ) from exc
        if result["created"] and not backup.try_acquire_build_slot():
            conn.execute(
                text(
                    "UPDATE recovery_jobs SET status = 'failed', "
                    "error = :error, completed_at = now() WHERE id = :id"
                ),
                {
                    "id": result["job_id"],
                    "error": "Admission limit: a backup build is already running.",
                },
            )
            raise HTTPException(429, "A backup build is already running.")
        job_id = str(result["job_id"])
        status = str(result["status"])
        created = bool(result["created"])
    if created:
        staging = backup.staging_dir()
        thread = threading.Thread(
            target=_build_and_release,
            args=(job_id, staging, db.database_url_for("app")),
            daemon=True,
        )
        thread.start()
    return JSONResponse(
        status_code=202,
        content={"schema_version": 1, "job_id": job_id, "status": status},
        headers=_PRIVATE_NO_STORE,
    )


@router.get("/backups/{job_id}")
def read_backup(job_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        require_admin(request, conn)
        job = backup.get_job(conn, str(job_id))
        if job is None:
            raise HTTPException(404, "Backup job not found.")
        return JSONResponse(
            {
                "schema_version": 1,
                "job_id": job["id"],
                "status": job["status"],
                "error": job.get("error"),
                "manifest": job.get("manifest"),
            },
            headers=_PRIVATE_NO_STORE,
        )


@router.get("/backups/{job_id}/download")
def download_backup(job_id: UUID, request: Request) -> FileResponse:
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        job = backup.get_job(conn, str(job_id))
        if job is None:
            raise HTTPException(404, "Backup job not found.")
        path = job.get("archive_path")
        if (
            job["status"] != "succeeded"
            or not isinstance(path, str)
            or not os.path.exists(path)
        ):
            raise HTTPException(409, "Backup is not ready for download.")
        backup.record_download_audit(
            conn,
            actor_id=str(actor["id"]),
            job_id=str(job["id"]),
            request_id=_request_id(request),
        )
        archive_path = path
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"backup-{job_id}.zip",
        headers=_PRIVATE_NO_STORE,
    )


@router.post("/restores/validate")
async def validate_restore(
    request: Request, archive: UploadFile = File(...)
) -> JSONResponse:
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        key = parse_idempotency_key(request.headers)
        if key is None:
            raise HTTPException(422, "A valid Idempotency-Key is required.")
        actor_id = str(actor["id"])
        request_id = _request_id(request)
    upload_bytes = await archive.read()
    request_hash = hashlib.sha256(upload_bytes).hexdigest()
    try:
        result = restore.validate_and_stage(
            upload_bytes=upload_bytes,
            filename=archive.filename or "backup.zip",
            actor_id=actor_id,
            idempotency_key=key,
            request_hash=request_hash,
            request_id=request_id,
            database_url=db.database_url_for("app"),
        )
    except restore.RestoreConflict as exc:
        raise HTTPException(
            409, "Idempotency key was used for another request."
        ) from exc
    if result["status"] != "staged":
        code = str(result.get("code") or "invalid_archive")
        return JSONResponse(
            status_code=422,
            content=error_body(
                "INVALID_CONTENT",
                f"Backup archive failed validation ({code}).",
                request_id,
                field_errors={"archive": code},
            ),
            headers=_PRIVATE_NO_STORE,
        )
    return JSONResponse(
        status_code=200,
        content={
            "schema_version": 1,
            "restore_id": result["restore_id"],
            "status": "staged",
            "confirmation_digest": result["confirmation_digest"],
            "report": result["report"],
        },
        headers=_PRIVATE_NO_STORE,
    )


@router.get("/restores/{restore_id}")
def read_restore(restore_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        require_admin(request, conn)
        row = restore.get_restore(conn, str(restore_id))
        if row is None:
            raise HTTPException(404, "Restore job not found.")
        return JSONResponse(
            {
                "schema_version": 1,
                "restore_id": row["restore_id"],
                "status": row["status"],
                "confirmation_digest": row["confirmation_digest"],
                "expired": row["expired"],
                "superseded": row["superseded"],
                "report": row["report"],
                "error": row["error"],
            },
            headers=_PRIVATE_NO_STORE,
        )
