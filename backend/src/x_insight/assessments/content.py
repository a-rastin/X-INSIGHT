"""Released-only assessment content serving."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from x_insight import db
from x_insight.assessments import load_definition
from x_insight.identity.routes import _require_session

CONTENT_DIR: Path = Path(__file__).resolve().parents[4] / "content" / "assessments"

ALLOWED_TYPES = {"diagnosis", "panss", "cssrs"}

router = APIRouter()


def _load_with_reason(
    assessment_type: str, base_dir: Path | None = None
) -> tuple[dict[str, Any] | None, str]:
    if assessment_type not in ALLOWED_TYPES:
        return None, "not_found"
    if base_dir is None:
        base_dir = CONTENT_DIR
    try:
        raw_text = (base_dir / f"{assessment_type}.json").read_text(encoding="utf-8")
    except OSError:
        return None, "not_found"
    try:
        envelope: Any = json.loads(raw_text)
    except ValueError:
        return None, "not_found"
    if not isinstance(envelope, dict):
        return None, "not_found"
    if envelope.get("review_status") != "released":
        return None, "not_found"
    raw_definition = envelope.get("definition")
    if not isinstance(raw_definition, dict):
        return None, "invalid_released"
    try:
        normalized = load_definition(raw_definition)
    except ValueError:
        return None, "invalid_released"
    return (
        {
            "assessment_type": assessment_type,
            "definition_version": normalized["definition_version"],
            "definition": normalized,
        },
        "ok",
    )


def load_released(
    assessment_type: str, base_dir: Path | None = None
) -> dict[str, Any] | None:
    """Return released content or None; no DB, reads at most one file."""
    payload, _reason = _load_with_reason(assessment_type, base_dir)
    return payload


@router.get("/content/assessments/{assessment_type}")
def get_assessment_content(assessment_type: str, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        denied, _actor = _require_session(request, conn)
        if denied is not None:
            return denied
        payload, reason = _load_with_reason(assessment_type)
        if payload is None:
            if reason == "invalid_released":
                raise HTTPException(500, "Released assessment content is invalid.")
            raise HTTPException(404, "Assessment content not found.")
        return JSONResponse(
            {
                "schema_version": 1,
                "assessment_type": payload["assessment_type"],
                "definition_version": payload["definition_version"],
                "definition": payload["definition"],
            },
            headers={"Cache-Control": "private, no-store"},
        )
