"""Backup + restore-validation + ops-metrics HTTP routes (S54/S55/S58, T10+T1)."""

from __future__ import annotations

import hashlib
import os
import threading
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from x_insight import db
from x_insight.contracts import (
    canonical_json,
    error_body,
    parse_idempotency_key,
)
from x_insight.identity.accounts import require_admin
from x_insight.identity.routes import _request_id
from x_insight.operations import backup, metrics, restore

router = APIRouter()

_PRIVATE_NO_STORE = {"Cache-Control": "private, no-store"}


@router.get("/ops-metrics")
def read_ops_metrics(request: Request) -> JSONResponse:
    """Admin-only safe operational metrics (S58 item 3, T1)."""
    with db.transaction() as conn:
        require_admin(request, conn)
        payload = metrics.collect_metrics(conn)
        return JSONResponse(payload, headers=_PRIVATE_NO_STORE)


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
                "pre_restore_backup_id": row.get("pre_restore_backup_id"),
                "commit": row.get("commit"),
            },
            headers=_PRIVATE_NO_STORE,
        )


class RestoreCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    restore_id: UUID = Field()
    confirmation_digest: str = Field(min_length=1)


@router.post("/restores/commit")
def commit_restore_route(request: Request, body: RestoreCommitRequest) -> JSONResponse:
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        key = parse_idempotency_key(request.headers)
        if key is None:
            raise HTTPException(422, "A valid Idempotency-Key is required.")
        actor_id = str(actor["id"])
        request_id = _request_id(request)
    restore_id = str(body.restore_id)
    digest = body.confirmation_digest
    request_hash = hashlib.sha256(
        canonical_json({"confirmation_digest": digest, "restore_id": restore_id})
    ).hexdigest()
    try:
        result = restore.commit_restore(
            restore_id=restore_id,
            confirmation_digest=digest,
            actor_id=actor_id,
            idempotency_key=key,
            request_hash=request_hash,
            request_id=request_id,
            database_url=db.database_url_for("app"),
        )
    except restore.RestoreConflict:
        return JSONResponse(
            status_code=409,
            content=error_body(
                "CONFLICT",
                "Idempotency key was used for another request.",
                request_id,
                field_errors={"idempotency_key": "conflict"},
            ),
            headers=_PRIVATE_NO_STORE,
        )
    except restore.RestoreRejected as exc:
        code = exc.code or "stale_confirmation"
        if code == "not_found":
            raise HTTPException(404, "Restore job not found.") from exc
        if code == "restore_rolled_back":
            return JSONResponse(
                status_code=503,
                content=error_body(
                    "UNAVAILABLE",
                    f"Restore commit failed ({code}): rolled back to "
                    "pre-restore backup. Maintenance stays active.",
                    request_id,
                    field_errors={"restore": code},
                    retryable=True,
                ),
                headers=_PRIVATE_NO_STORE,
            )
        return JSONResponse(
            status_code=409,
            content=error_body(
                "CONFLICT",
                f"Restore commit rejected ({code}): confirmation digest is stale.",
                request_id,
                field_errors={"confirmation_digest": code},
            ),
            headers=_PRIVATE_NO_STORE,
        )
    if result is None:
        raise HTTPException(404, "Restore job not found.")
    return JSONResponse(
        status_code=202,
        content={
            "schema_version": 1,
            "restore_id": str(result["restore_id"]),
            "status": str(result["status"]),
            "confirmation_digest": result["confirmation_digest"],
            "pre_restore_backup_id": result.get("pre_restore_backup_id"),
        },
        headers=_PRIVATE_NO_STORE,
    )


@router.post("/restores/{restore_id}/reopen")
def reopen_restore_route(restore_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        actor = require_admin(request, conn)
        key = parse_idempotency_key(request.headers)
        if key is None:
            raise HTTPException(422, "A valid Idempotency-Key is required.")
        actor_id = str(actor["id"])
        request_id = _request_id(request)
    request_hash = hashlib.sha256(
        canonical_json({"restore_id": str(restore_id)})
    ).hexdigest()
    try:
        result = restore.reopen_restore(
            restore_id=str(restore_id),
            actor_id=actor_id,
            idempotency_key=key,
            request_hash=request_hash,
            request_id=request_id,
            database_url=db.database_url_for("app"),
        )
    except restore.RestoreRejected as exc:
        code = exc.code or "reopen_refused"
        if code == "not_found":
            raise HTTPException(404, "Restore job not found.") from exc
        if code == "unhealthy":
            return JSONResponse(
                status_code=503,
                content=error_body(
                    "UNAVAILABLE",
                    f"Restore target failed health checks ({code}). "
                    "Maintenance stays active.",
                    request_id,
                    retryable=True,
                ),
                headers=_PRIVATE_NO_STORE,
            )
        return JSONResponse(
            status_code=409,
            content=error_body(
                "CONFLICT",
                f"Restore reopen refused ({code}).",
                request_id,
                field_errors={"restore_id": code},
            ),
            headers=_PRIVATE_NO_STORE,
        )
    if result is None:
        raise HTTPException(404, "Restore job not found.")
    return JSONResponse(
        status_code=200,
        content={
            "schema_version": 1,
            "restore_id": str(result["restore_id"]),
            "status": str(result["status"]),
        },
        headers=_PRIVATE_NO_STORE,
    )
