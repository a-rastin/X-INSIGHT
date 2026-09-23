"""Authorized CSV exports + printable patient report (S53, plan §10.1)."""

from __future__ import annotations

import csv
import html
import io
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import text

from x_insight import db
from x_insight.identity.routes import _request_id, _require_session
from x_insight.operations.audit import record_audit

router = APIRouter()

RESEARCH_NOTICE = (
    "This is a research app and is not intended to be used as the sole basis "
    "for treating patients."
)

_FORMULA_LEADS = ("=", "+", "-", "@")


def _neutralize(value: str) -> str:
    """Spreadsheet-formula neutralization for free-text CSV cells only."""
    if value.lstrip(" \t")[:1] in _FORMULA_LEADS:
        return "'" + value
    return value


def _csv_response(
    filename: str, headers: list[str], rows: list[list[Any]]
) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


def _require_admin(request: Request, conn: Any) -> tuple[Response | None, Any]:
    denied, actor = _require_session(request, conn)
    if denied is not None:
        return denied, None
    if actor["role"] != "admin":
        raise HTTPException(403, "Administrator access required.")
    return None, actor


@router.get("/exports/patients.csv")
def export_patients_csv(request: Request) -> Response:
    with db.transaction() as conn:
        denied, actor = _require_admin(request, conn)
        if denied is not None:
            return denied
        rows = (
            conn.execute(
                text(
                    "SELECT patient_id_text, first_name, last_name, sex, age, "
                    "clinical_status, phone, archived FROM patients "
                    "ORDER BY patient_id_text, id"
                )
            )
            .mappings()
            .all()
        )
        headers = [
            "patient_id",
            "first_name",
            "last_name",
            "sex",
            "age",
            "clinical_status",
            "phone",
            "archived",
        ]
        data = [
            [
                row["patient_id_text"],
                _neutralize(str(row["first_name"])),
                _neutralize(str(row["last_name"])),
                str(row["sex"]),
                int(row["age"]),
                str(row["clinical_status"]),
                _neutralize(str(row["phone"]))
                if row["phone"] is not None
                else "",
                "true" if row["archived"] else "false",
            ]
            for row in rows
        ]
        record_audit(
            conn,
            operation="exports.patients_csv",
            actor_id=str(actor["id"]),
            request_id=_request_id(request),
            target_display="patients.csv",
            result_status=200,
        )
        return _csv_response("patients.csv", headers, data)


@router.get("/exports/physicians.csv")
def export_physicians_csv(request: Request) -> Response:
    with db.transaction() as conn:
        denied, actor = _require_admin(request, conn)
        if denied is not None:
            return denied
        rows = (
            conn.execute(
                text(
                    "SELECT id, username, role, active FROM users "
                    "WHERE role = 'physician' ORDER BY username, id"
                )
            )
            .mappings()
            .all()
        )
        headers = ["id", "username", "role", "active"]
        data = [
            [
                str(row["id"]),
                _neutralize(str(row["username"])),
                str(row["role"]),
                "true" if row["active"] else "false",
            ]
            for row in rows
        ]
        record_audit(
            conn,
            operation="exports.physicians_csv",
            actor_id=str(actor["id"]),
            request_id=_request_id(request),
            target_display="physicians.csv",
            result_status=200,
        )
        return _csv_response("physicians.csv", headers, data)


def _esc(value: Any) -> str:
    if value is None:
        return "unavailable"
    return html.escape(str(value), quote=True)


def _section(title: str, body: str) -> str:
    return f"<section><h2>{html.escape(title)}</h2>{body}</section>"


def _unavailable(label: str) -> str:
    return f"<p>{html.escape(label)}: unavailable</p>"


@router.get("/patients/{patient_id}/report")
def patient_report(patient_id: UUID, request: Request) -> Response:
    with db.transaction() as conn:
        denied, actor = _require_session(request, conn)
        if denied is not None:
            return denied
        if actor["role"] not in ("admin", "physician"):
            raise HTTPException(403, "Access denied.")
        patient = (
            conn.execute(
                text("SELECT * FROM patients WHERE id = :id"),
                {"id": str(patient_id)},
            )
            .mappings()
            .first()
        )
        if patient is None:
            raise HTTPException(404, "Patient not found.")

        try:
            encounters = (
                conn.execute(
                    text(
                        "SELECT id, kind, state, revision, created_at "
                        "FROM encounters WHERE patient_id = :pid "
                        "ORDER BY created_at, id"
                    ),
                    {"pid": str(patient_id)},
                )
                .mappings()
                .all()
            )
        except Exception:
            encounters = []

        encounter_ids = [str(e["id"]) for e in encounters]
        notes: Sequence[Any] = []
        plans: Sequence[Any] = []
        snapshots: Sequence[Any] = []
        addenda: Sequence[Any] = []
        try:
            if encounter_ids:
                notes = (
                    conn.execute(
                        text(
                            "SELECT encounter_id, page, text, author_display, "
                            "created_at FROM encounter_notes "
                            "WHERE encounter_id = ANY(:eids) "
                            "ORDER BY created_at, id"
                        ),
                        {"eids": encounter_ids},
                    )
                    .mappings()
                    .all()
                )
        except Exception:
            notes = []
        try:
            if encounter_ids:
                plans = (
                    conn.execute(
                        text(
                            "SELECT encounter_id, revision, text, created_at "
                            "FROM secondary_plan_revisions "
                            "WHERE encounter_id = ANY(:eids) "
                            "ORDER BY created_at, id"
                        ),
                        {"eids": encounter_ids},
                    )
                    .mappings()
                    .all()
                )
        except Exception:
            plans = []
        try:
            if encounter_ids:
                snapshots = (
                    conn.execute(
                        text(
                            "SELECT encounter_id, snapshot_hash, signer_id, "
                            "signed_at, encounter_revision FROM signed_snapshots "
                            "WHERE encounter_id = ANY(:eids) "
                            "ORDER BY signed_at, id"
                        ),
                        {"eids": encounter_ids},
                    )
                    .mappings()
                    .all()
                )
        except Exception:
            snapshots = []
        try:
            if encounter_ids:
                addenda = (
                    conn.execute(
                        text(
                            "SELECT encounter_id, reason, correction_text, "
                            "created_at FROM encounter_addenda "
                            "WHERE encounter_id = ANY(:eids) "
                            "ORDER BY created_at, id"
                        ),
                        {"eids": encounter_ids},
                    )
                    .mappings()
                    .all()
                )
        except Exception:
            addenda = []

        parts: list[str] = [
            f"<p><strong>Research notice:</strong> "
            f"{html.escape(RESEARCH_NOTICE)}</p>"
        ]
        parts.append(
            _section(
                "Current demographics",
                "<dl>"
                + "".join(
                    f"<dt>{key}</dt><dd>{_esc(patient[key])}</dd>"
                    for key in (
                        "patient_id_text",
                        "first_name",
                        "last_name",
                        "sex",
                        "age",
                        "clinical_status",
                        "phone",
                        "archived",
                        "revision",
                    )
                )
                + "</dl>",
            )
        )

        if encounters:
            items = "".join(
                f"<li>{_esc(e['kind'])} encounter "
                f"({_esc(e['state'])}, revision {_esc(e['revision'])}, "
                f"{_esc(e['created_at'])})</li>"
                for e in encounters
            )
            states = {str(e["state"]) for e in encounters}
            state_labels = (
                "<p>States present: " + _esc(", ".join(sorted(states))) + "</p>"
                if states
                else ""
            )
            parts.append(
                _section(
                    "Encounter chronology (draft and signed)",
                    f"<ul>{items}</ul>{state_labels}",
                )
            )
        else:
            parts.append(
                _section(
                    "Encounter chronology (draft and signed)",
                    _unavailable("No encounters recorded"),
                )
            )

        parts.append(
            _section(
                "Assessment completeness",
                _unavailable("Assessment results")
                if not encounters
                else "<p>Draft encounters are shown above; "
                "historical signed results are preserved in signed "
                "snapshots below.</p>",
            )
        )
        parts.append(
            _section("History", _unavailable("Structured history coverage"))
        )
        parts.append(
            _section(
                "Medications and DDI coverage",
                _unavailable("Medication and DDI coverage"),
            )
        )

        if plans:
            plan_items = "".join(
                f"<li>Secondary plan revision {_esc(p['revision'])}: "
                f"{_esc(p['text'])}</li>"
                for p in plans
            )
            initial = (
                "<p>Initial proposal: see signed snapshot below; "
                "no separate initial plan recorded.</p>"
            )
            parts.append(
                _section(
                    "Initial and secondary plans (current)",
                    f"{initial}<ul>{plan_items}</ul>",
                )
            )
        else:
            parts.append(
                _section(
                    "Initial and secondary plans (current)",
                    _unavailable("Initial and secondary plans"),
                )
            )

        if snapshots:
            sig_items = "".join(
                f"<li>Signed encounter {_esc(s['encounter_id'])} by "
                f"{_esc(s['signer_id'])} at {_esc(s['signed_at'])} "
                f"(hash {_esc(s['snapshot_hash'])})</li>"
                for s in snapshots
            )
            parts.append(
                _section(
                    "Signatures (historical signed snapshots)",
                    f"<ul>{sig_items}</ul>",
                )
            )
        else:
            parts.append(
                _section(
                    "Signatures (historical signed snapshots)",
                    _unavailable("Signatures"),
                )
            )

        note_items = "".join(
            f"<li>{_esc(n['page'])} by {_esc(n['author_display'])}: "
            f"{_esc(n['text'])}</li>"
            for n in notes
        )
        addenda_items = "".join(
            f"<li>Correction: {_esc(a['reason'])} — "
            f"{_esc(a['correction_text'])}</li>"
            for a in addenda
        )
        if note_items or addenda_items:
            parts.append(
                _section(
                    "Notes and addenda",
                    f"<ul>{note_items}{addenda_items}</ul>",
                )
            )
        else:
            parts.append(
                _section("Notes and addenda", _unavailable("Notes and addenda"))
            )

        body = (
            "<!DOCTYPE html><html lang=\"en\"><head>"
            "<meta charset=\"utf-8\">"
            f"<title>Patient report {_esc(patient['patient_id_text'])}</title>"
            "</head><body><h1>Patient report</h1>"
            + "".join(parts)
            + "</body></html>"
        )
        record_audit(
            conn,
            operation="report.export",
            actor_id=str(actor["id"]),
            request_id=_request_id(request),
            result_reference=str(patient_id),
            target_display=str(patient["patient_id_text"]),
            result_status=200,
        )
        return Response(
            content=body.encode("utf-8"),
            media_type="text/html",
            headers={"Cache-Control": "private, no-store"},
        )
