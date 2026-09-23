"""Ordered proposal assembly with pinned DDI (S46 slice 3).

Synthetic only; no clinical content. Assembles the final proposal only
after every applicable (ready) question has a succeeded artifact and a
valid pinned DDI report. Uses frozen snapshot medications/dataset
version, never live chart values. Never issues an LLM proposal request:
only per-question provider calls exist. A succeeded proposal is
immutable: never overwritten; new bundles use new runs only.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from x_insight import db


def _applicability(projection: Any, question_key: str) -> tuple[str, str]:
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


def try_assemble_proposal(
    run_id: str, database_url: str | None = None
) -> dict[str, Any] | None:
    """Attempt terminal proposal assembly for one run.

    Returns the succeeded proposal dict when complete, else None.
    Side effects (idempotent):
    - pending needs_clarification -> run needs_clarification, no proposal.
    - pending ready work -> no state change, no proposal (still in progress).
    - all applicable done + valid pinned DDI -> insert/update run_proposals
      (immutable once succeeded) and mark run succeeded.
    - all applicable done + invalid/unknown DDI -> mark run failed with
      a machine-readable code (distinct from limited coverage, which
      still succeeds), no succeeded proposal.
    """
    with db.transaction(database_url) as conn:
        run = (
            conn.execute(
                text("SELECT * FROM runs WHERE id = :id"),
                {"id": str(run_id)},
            )
            .mappings()
            .first()
        )
        if run is None:
            return None
        # Immutable once succeeded: never mutate a succeeded proposal.
        try:
            existing = (
                conn.execute(
                    text(
                        "SELECT status, proposal FROM run_proposals "
                        "WHERE run_id = :run_id"
                    ),
                    {"run_id": str(run_id)},
                )
                .mappings()
                .first()
            )
        except Exception:
            existing = None
        if existing is not None and str(existing["status"]) == "succeeded":
            stored = existing["proposal"]
            if isinstance(stored, dict):
                return dict(stored)
            return None

        q_rows = (
            conn.execute(
                text(
                    "SELECT question_key, ordinal, projection FROM run_questions "
                    "WHERE run_id = :run_id ORDER BY ordinal, id"
                ),
                {"run_id": str(run_id)},
            )
            .mappings()
            .all()
        )
        art_rows = (
            conn.execute(
                text(
                    "SELECT question_key FROM run_question_artifacts "
                    "WHERE run_id = :run_id AND status = 'succeeded'"
                ),
                {"run_id": str(run_id)},
            )
            .mappings()
            .all()
        )
        succeeded = {str(item["question_key"]) for item in art_rows}

        ordered_keys: list[str] = []
        skipped: list[dict[str, str]] = []
        pending_ready = False
        pending_clarification = False
        for item in q_rows:
            key = str(item["question_key"])
            status, reason = _applicability(item["projection"], key)
            ordered_keys.append(key)
            if status == "not_applicable":
                skipped.append({"question_key": key, "reason": reason})
            elif status == "needs_clarification":
                if key not in succeeded:
                    pending_clarification = True
            else:  # ready
                if key not in succeeded:
                    pending_ready = True

        if pending_clarification:
            conn.execute(
                text(
                    "UPDATE runs SET status = 'needs_clarification', "
                    "updated_at = now() WHERE id = :id AND status NOT IN "
                    "('succeeded', 'failed', 'needs_clarification', "
                    "'stale', 'cancelled')"
                ),
                {"id": str(run_id)},
            )
            return None
        if pending_ready:
            return None

        # All applicable done: require a valid pinned DDI report.
        snapshot = run["snapshot"]
        facts: dict[str, Any] = {}
        if isinstance(snapshot, dict) and isinstance(snapshot.get("facts"), dict):
            facts = dict(snapshot["facts"])
        medications = facts.get("medications")
        ddi_ref = facts.get("ddi_report")
        dataset_version: Any = None
        if isinstance(ddi_ref, dict):
            dataset_version = ddi_ref.get("dataset_version")
        if not isinstance(medications, list) or not isinstance(dataset_version, str):
            conn.execute(
                text(
                    "UPDATE runs SET status = 'failed', updated_at = now() "
                    "WHERE id = :id AND status NOT IN ('succeeded', "
                    "'failed', 'needs_clarification', 'stale', 'cancelled')"
                ),
                {"id": str(run_id)},
            )
            return None
        try:
            from x_insight.ddi.checker import check as ddi_check

            ddi_report = ddi_check(
                [dict(m) for m in medications if isinstance(m, dict)],
                dataset_version,
                database_url=database_url,
            )
        except (LookupError, ValueError) as exc:
            code = "ddi_unavailable" if isinstance(exc, LookupError) else "ddi_invalid"
            conn.execute(
                text(
                    "UPDATE runs SET status = 'failed', updated_at = now() "
                    "WHERE id = :id AND status NOT IN ('succeeded', "
                    "'failed', 'needs_clarification', 'stale', 'cancelled')"
                ),
                {"id": str(run_id)},
            )
            # Surface a machine-readable code on the latest job without
            # clobbering its terminal state (GET exposes run failed).
            try:
                conn.execute(
                    text(
                        "UPDATE reasoning_jobs SET failure_details = "
                        "CAST(:details AS jsonb), updated_at = now() "
                        "WHERE id = (SELECT id FROM reasoning_jobs "
                        "WHERE run_id = :run_id ORDER BY ordinal DESC, "
                        "id DESC LIMIT 1)"
                    ),
                    {
                        "details": json.dumps(
                            {"code": code, "error": "failed"}, sort_keys=True
                        ),
                        "run_id": str(run_id),
                    },
                )
            except Exception:
                pass
            return None
        except Exception:
            conn.execute(
                text(
                    "UPDATE runs SET status = 'failed', updated_at = now() "
                    "WHERE id = :id AND status NOT IN ('succeeded', "
                    "'failed', 'needs_clarification', 'stale', 'cancelled')"
                ),
                {"id": str(run_id)},
            )
            return None

        # Ordered sections mirror persisted successes in bundle order.
        by_ordinal = sorted(
            [(int(item["ordinal"]), str(item["question_key"])) for item in q_rows]
        )
        sections = [key for _, key in by_ordinal if key in succeeded]
        # Only applicable (ready) questions contribute sections; skipped
        # rows never have artifacts by construction.
        assembled: dict[str, Any] = {
            "status": "succeeded",
            "sections": sections,
            "skipped": skipped,
            "ddi_report": dict(ddi_report),
        }
        try:
            conn.execute(
                text(
                    "INSERT INTO run_proposals (run_id, status, proposal, "
                    "ddi_report) VALUES (:run_id, 'succeeded', "
                    "CAST(:proposal AS jsonb), CAST(:ddi AS jsonb)) "
                    "ON CONFLICT (run_id) DO UPDATE SET status = 'succeeded', "
                    "proposal = CAST(:proposal AS jsonb), "
                    "ddi_report = CAST(:ddi AS jsonb), updated_at = now() "
                    "WHERE run_proposals.status != 'succeeded'"
                ),
                {
                    "run_id": str(run_id),
                    "proposal": json.dumps(assembled),
                    "ddi": json.dumps(dict(ddi_report)),
                },
            )
        except Exception:
            return None
        conn.execute(
            text(
                "UPDATE runs SET status = 'succeeded', updated_at = now() "
                "WHERE id = :id"
            ),
            {"id": str(run_id)},
        )
        return dict(assembled)
