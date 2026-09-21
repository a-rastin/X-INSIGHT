"""Released-only structured-history content serving (S12 slice 4).

Mirrors the S08 assessments content contract: anonymous -> 401,
draft/unreleased -> 404, released -> 200 with definition_version and
``Cache-Control: private, no-store``. Honors X_INSIGHT_HISTORY_CONTENT_DIR
at request time. The awaiting_review draft under content/history/ is never
served as released.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from x_insight import db
from x_insight.identity.routes import _require_session

router = APIRouter()

DEFAULT_CONTENT_DIR: Path = Path(__file__).resolve().parents[4] / "content" / "history"


def _content_dir() -> Path:
    configured = os.environ.get("X_INSIGHT_HISTORY_CONTENT_DIR")
    return Path(configured) if configured else DEFAULT_CONTENT_DIR


def _load_released() -> dict[str, Any] | None:
    try:
        raw: Any = json.loads(
            (_content_dir() / "history.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("review_status") != "released":
        return None
    if raw.get("content_type") != "history":
        return None
    definition = raw.get("definition")
    if not isinstance(definition, dict):
        return None
    version = definition.get("definition_version")
    if (
        not isinstance(version, str)
        or not version
        or raw.get("content_version") != version
    ):
        return None
    return {
        "definition_version": version,
        "definition": definition,
    }


@router.get("/content/history")
def get_history_content(request: Request) -> JSONResponse:
    with db.transaction() as conn:
        denied, _actor = _require_session(request, conn)
        if denied is not None:
            return denied
        payload = _load_released()
        if payload is None:
            raise HTTPException(404, "History content not found.")
        return JSONResponse(
            {
                "schema_version": 1,
                "definition_version": payload["definition_version"],
                "definition": payload["definition"],
            },
            headers={"Cache-Control": "private, no-store"},
        )
