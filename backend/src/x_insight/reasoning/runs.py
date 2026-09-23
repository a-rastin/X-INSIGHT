"""Frozen run snapshots (S40 slices 1-4: freeze + project + stale + gates)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from x_insight import db
from x_insight.contracts import (
    canonical_json,
    parse_idempotency_key,
    parse_if_match,
    to_utc_z,
)
from x_insight.identity.hashing import hash_password, verify_password
from x_insight.identity.routes import _check_csrf, _request_id, _require_session
from x_insight.operations.audit import record_audit
from x_insight.reasoning.queue import (
    ACTIVE_RUN_STATUSES,
    MAX_QUEUED_RUNS,
    first_eligible_question,
)
from x_insight.reasoning.snapshots import (
    build_projections,
    build_snapshot,
    find_invalid_source_path,
)

router = APIRouter()

_RUN_OPERATION = "run.start"


def _workflow_for(kind: Any) -> str:
    return "followup" if kind == "follow_up" else "registration"


def _projection_applicability(projection: Any, question_key: str) -> tuple[str, str]:
    """Read persisted gate outcome from the projection JSONB payload.

    Gates are evaluated at run start from frozen facts and stored inside
    the run_questions.projection JSONB (no new migration). GET surfaces
    them as sibling keys. Missing values default to ready (pre-gate rows).
    """
    status: Any = None
    reason: Any = None
    if isinstance(projection, dict):
        status = projection.get("applicability")
        reason = projection.get("applicability_reason")
    if status not in ("ready", "not_applicable", "needs_clarification"):
        status = "ready"
    if not isinstance(reason, str) or not reason.strip():
        reason = f"{status} for {question_key}"
    return (str(status), str(reason))


def _active_status_list() -> str:
    return ", ".join(f"'{status}'" for status in sorted(ACTIVE_RUN_STATUSES))


def _run_payload(
    run: Any, projections: list[dict[str, Any]], stale: bool, jobs: list[dict[str, Any]]
) -> dict[str, Any]:
    snapshot = run["snapshot"]
    pinned = snapshot.get("pinned") if isinstance(snapshot, dict) else None
    return {
        "schema_version": 1,
        "run": {
            "id": str(run["id"]),
            "encounter_id": str(run["encounter_id"]),
            "encounter_revision": run["encounter_revision"],
            "workflow": run["workflow"],
            "status": run["status"],
            "revision": run["revision"],
            "created_at": to_utc_z(run["created_at"]),
            "updated_at": to_utc_z(run["updated_at"]),
        },
        "snapshot_hash": run["snapshot_hash"],
        "fingerprint": run["fingerprint"],
        "stale": stale,
        "projections": projections,
        "pinned": dict(pinned) if isinstance(pinned, dict) else {},
        "jobs": jobs,
    }


def _compute_stale(conn: Any, run: Any) -> bool:
    """Recompute the analysis fingerprint from LIVE facts, frozen pins.

    Scope is exactly :func:`build_snapshot` scope (analytical draft
    sections + patients.clinical_status + pinned bundle/history/DDI
    versions). Notes (encounter_notes) and names/ID/phone never enter.
    Uses the run's own pinned bundle_hash/pins so bundle rotation never
    stales old runs. Pure read: frozen rows are never mutated. Equality
    is fingerprint equality, so note-only edits stay fresh even if they
    ever bumped the encounter revision.
    """
    try:
        encounter = (
            conn.execute(
                text("SELECT * FROM encounters WHERE id = :id"),
                {"id": str(run["encounter_id"])},
            )
            .mappings()
            .first()
        )
        if encounter is None:
            return True
        patient_id = run["patient_id"] or encounter["patient_id"]
        patient = (
            conn.execute(
                text("SELECT * FROM patients WHERE id = :id"),
                {"id": str(patient_id)},
            )
            .mappings()
            .first()
        )
        if patient is None:
            return True
        draft = encounter["draft_data"]
        if not isinstance(draft, dict):
            draft = {}
        pins = run["pins"]
        if not isinstance(pins, dict):
            pins = {}
        _snapshot, live_fingerprint, _snapshot_hash = build_snapshot(
            dict(encounter),
            dict(patient),
            draft,
            {"bundle_hash": run["bundle_hash"], "pins": dict(pins)},
        )
        return bool(live_fingerprint != run["fingerprint"])
    except Exception:
        # Conservative: unreadable live facts cannot prove freshness.
        return True


@router.post("/encounters/{encounter_id}/runs")
async def start_run(encounter_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        denied, actor = _require_session(request, conn)
        if denied is not None:
            return denied
        csrf_denied = _check_csrf(request, actor)
        if csrf_denied is not None:
            return csrf_denied
        row = (
            conn.execute(
                text("SELECT * FROM encounters WHERE id = :id FOR UPDATE"),
                {"id": str(encounter_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(404, "Encounter not found.")
        if str(row["author_id"]) != str(actor["user_id"]):
            raise HTTPException(403, "Only the draft author may start a run.")
        if row["state"] != "draft":
            raise HTTPException(409, "Runs start from draft encounters only.")
        patient = (
            conn.execute(
                text("SELECT * FROM patients WHERE id = :id"),
                {"id": str(row["patient_id"])},
            )
            .mappings()
            .first()
        )
        if patient is None:
            raise HTTPException(404, "Encounter not found.")
        if patient["archived"]:
            raise HTTPException(409, "Archived patient drafts are read-only.")
        current_revision = int(row["revision"])
        if parse_if_match(request.headers) != str(current_revision):
            raise HTTPException(
                412, "The draft changed. Reload and reconcile your edits."
            )
        key = parse_idempotency_key(request.headers)
        if key is None:
            raise HTTPException(422, "A valid Idempotency-Key is required.")
        try:
            data = await request.json()
        except Exception as exc:
            raise HTTPException(422, "Invalid request body.") from exc
        if not isinstance(data, dict) or set(data.keys()) != {"encounter_revision"}:
            raise HTTPException(422, "encounter_revision is required.")
        body_revision = data["encounter_revision"]
        if not isinstance(body_revision, int) or isinstance(body_revision, bool):
            raise HTTPException(422, "encounter_revision must be an integer.")
        if int(body_revision) != current_revision:
            raise HTTPException(
                412, "The draft changed. Reload and reconcile your edits."
            )
        workflow = _workflow_for(row["kind"])
        pointer = (
            conn.execute(
                text("SELECT * FROM model_bundle_pointers WHERE workflow = :workflow"),
                {"workflow": workflow},
            )
            .mappings()
            .first()
        )
        if (
            pointer is None
            or not pointer["bundle_hash"]
            or not isinstance(pointer["pins"], dict)
        ):
            raise HTTPException(409, "No active model bundle for this workflow.")
        pins_dict = dict(pointer["pins"])
        if find_invalid_source_path(pins_dict) is not None:
            raise HTTPException(422, "INVALID_CONTENT: disallowed source path.")
        actor_id = str(actor["user_id"])
        draft = row["draft_data"] if isinstance(row["draft_data"], dict) else {}
        snapshot, fingerprint, snapshot_hash = build_snapshot(
            dict(row), dict(patient), draft, dict(pointer)
        )
        pins = dict(pointer["pins"])
        triples = build_projections(snapshot["facts"], pins, current_revision)
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:eid, 0))"),
            {"eid": str(encounter_id)},
        )
        active_sql = _active_status_list()
        existing = (
            conn.execute(
                text(
                    "SELECT * FROM runs WHERE encounter_id = :eid "
                    f"AND fingerprint = :fp AND status IN ({active_sql}) "
                    "ORDER BY created_at, id LIMIT 1"
                ),
                {"eid": str(encounter_id), "fp": fingerprint},
            )
            .mappings()
            .first()
        )
        if existing is not None:
            existing_rows = (
                conn.execute(
                    text(
                        "SELECT question_key FROM run_questions "
                        "WHERE run_id = :rid ORDER BY ordinal, id"
                    ),
                    {"rid": str(existing["id"])},
                )
                .mappings()
                .all()
            )
            reuse_result: dict[str, Any] = {
                "schema_version": 1,
                "run_id": str(existing["id"]),
                "revision": current_revision,
                "status": str(existing["status"]),
                "questions": [item["question_key"] for item in existing_rows],
            }
            return JSONResponse(status_code=202, content=reuse_result)
        active_count = conn.execute(
            text(f"SELECT COUNT(*) FROM runs WHERE status IN ({active_sql})")
        ).scalar()
        if active_count is not None and int(active_count) >= int(MAX_QUEUED_RUNS):
            raise HTTPException(429, "Queue is saturated. Retry later.")
        scope = {
            "actor_id": actor_id,
            "operation": _RUN_OPERATION,
            "idempotency_key": key,
        }
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": canonical_json(scope).decode()},
        )
        fingerprint_body = canonical_json(
            {
                "encounter_id": str(encounter_id),
                "encounter_revision": current_revision,
            }
        ).decode()
        saved = (
            conn.execute(
                text(
                    "SELECT request_hash, result_payload, result_status "
                    "FROM audit_events "
                    "WHERE actor_id = :actor_id AND operation = :operation "
                    "AND idempotency_key = :idempotency_key"
                ),
                scope,
            )
            .mappings()
            .first()
        )
        if saved is not None:
            if not verify_password(fingerprint_body, str(saved["request_hash"])):
                raise HTTPException(
                    409, "Idempotency key was used for another request."
                )
            return JSONResponse(
                status_code=int(saved["result_status"] or 202),
                content=saved["result_payload"],
            )
        conn.execute(
            text(
                "UPDATE runs SET status = 'stale', updated_at = now() "
                "WHERE encounter_id = :eid "
                f"AND status IN ({active_sql}) AND fingerprint != :fp"
            ),
            {"eid": str(encounter_id), "fp": fingerprint},
        )
        created = (
            conn.execute(
                text(
                    "INSERT INTO runs (encounter_id, author_id, patient_id, "
                    " encounter_revision, workflow, snapshot, snapshot_hash, "
                    " fingerprint, bundle_hash, pins) VALUES (:encounter_id, "
                    " :author_id, :patient_id, :encounter_revision, :workflow, "
                    " CAST(:snapshot AS jsonb), :snapshot_hash, :fingerprint, "
                    " :bundle_hash, CAST(:pins AS jsonb)) RETURNING *"
                ),
                {
                    "encounter_id": str(encounter_id),
                    "author_id": actor_id,
                    "patient_id": str(row["patient_id"]),
                    "encounter_revision": current_revision,
                    "workflow": workflow,
                    "snapshot": json.dumps(snapshot),
                    "snapshot_hash": snapshot_hash,
                    "fingerprint": fingerprint,
                    "bundle_hash": str(pointer["bundle_hash"]),
                    "pins": json.dumps(pins),
                },
            )
            .mappings()
            .one()
        )
        run_id = str(created["id"])
        projections: list[dict[str, Any]] = []
        for ordinal, (question_key, projection, projection_hash) in enumerate(triples):
            conn.execute(
                text(
                    "INSERT INTO run_questions (run_id, question_key, ordinal, "
                    " projection, projection_hash) VALUES (:run_id, :question_key, "
                    " :ordinal, CAST(:projection AS jsonb), :projection_hash)"
                ),
                {
                    "run_id": run_id,
                    "question_key": question_key,
                    "ordinal": ordinal,
                    "projection": json.dumps(projection),
                    "projection_hash": projection_hash,
                },
            )
            projections.append(
                {
                    "question_key": question_key,
                    "projection_hash": projection_hash,
                    "projection": projection,
                    "applicability": projection.get("applicability"),
                    "applicability_reason": projection.get("applicability_reason"),
                }
            )
        eligible = first_eligible_question(pins, triples)
        if eligible is not None:
            eligible_key, eligible_ordinal = eligible
            conn.execute(
                text(
                    "INSERT INTO reasoning_jobs (run_id, encounter_id, author_id, "
                    " question_key, ordinal, stage, status) VALUES (:run_id, "
                    " :encounter_id, :author_id, :question_key, :ordinal, "
                    " 'preparing_question', 'queued')"
                ),
                {
                    "run_id": run_id,
                    "encounter_id": str(encounter_id),
                    "author_id": actor_id,
                    "question_key": eligible_key,
                    "ordinal": eligible_ordinal,
                },
            )
        result: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "revision": current_revision,
            "status": str(created["status"]),
            "questions": [item["question_key"] for item in projections],
        }
        record_audit(
            conn,
            operation=_RUN_OPERATION,
            actor_id=actor_id,
            idempotency_key=key,
            request_hash=hash_password(fingerprint_body),
            result_reference=run_id,
            request_id=_request_id(request),
            target_display=str(row["patient_id"]),
            result_payload=result,
            result_status=202,
        )
        return JSONResponse(status_code=202, content=result)


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        denied, actor = _require_session(request, conn)
        if denied is not None:
            return denied
        run = (
            conn.execute(
                text("SELECT * FROM runs WHERE id = :id"),
                {"id": str(run_id)},
            )
            .mappings()
            .first()
        )
        if run is None:
            raise HTTPException(404, "Run not found.")
        if str(run["author_id"]) != str(actor["user_id"]):
            raise HTTPException(403, "Only the run author may read it.")
        rows = (
            conn.execute(
                text(
                    "SELECT question_key, projection, projection_hash "
                    "FROM run_questions WHERE run_id = :run_id ORDER BY ordinal, id"
                ),
                {"run_id": str(run_id)},
            )
            .mappings()
            .all()
        )
        projections = []
        for item in rows:
            status, reason = _projection_applicability(
                item["projection"], str(item["question_key"])
            )
            projections.append(
                {
                    "question_key": item["question_key"],
                    "projection_hash": item["projection_hash"],
                    "projection": item["projection"],
                    "applicability": status,
                    "applicability_reason": reason,
                }
            )
        stale = _compute_stale(conn, run)
        job_rows = (
            conn.execute(
                text(
                    "SELECT question_key, ordinal, stage, status, "
                    "attempt_count, fencing_generation "
                    "FROM reasoning_jobs WHERE run_id = :run_id "
                    "ORDER BY ordinal, id"
                ),
                {"run_id": str(run_id)},
            )
            .mappings()
            .all()
        )
        jobs = [
            {
                "question_key": str(item["question_key"]),
                "ordinal": int(item["ordinal"]),
                "stage": str(item["stage"]),
                "status": str(item["status"]),
                "attempt_count": int(item["attempt_count"] or 0),
                "fencing_generation": int(item["fencing_generation"] or 0),
            }
            for item in job_rows
        ]
        return JSONResponse(
            _run_payload(run, projections, stale, jobs),
            headers={"Cache-Control": "private, no-store"},
        )
