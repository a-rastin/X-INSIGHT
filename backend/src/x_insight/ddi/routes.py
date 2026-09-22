"""S19 slice 4 DDI HTTP surface: pinned check + catalog search.

POST /ddi/check is session-required, read-only (no CSRF, no mutation):
permissive body delegates discriminator/excluded-field validation to the
checker (ValueError -> 422, unknown dataset LookupError -> 404, malformed
release LookupError -> 503 distinct from valid limited coverage).
GET /drugs searches distinct normalized concept IDs from the latest release
by created_at (evidence pair_key constituents; canonical_name equals
concept_id since evidence carries no names); catalog_version uses the same
rule as the checker (terminology_version else ddi-terminology-1).
Limits: default 25, bounded 1..100 by capping. Private no-store.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from x_insight import db
from x_insight.ddi import checker
from x_insight.ddi.terminology import normalize

router = APIRouter()


class CheckRequest(BaseModel):
    dataset_version: str
    medications: list[dict[str, Any]]


def _catalog_version(provenance: Any) -> str:
    return checker.catalog_version_for(provenance)


@router.post("/ddi/check")
def post_ddi_check(body: CheckRequest, request: Request) -> JSONResponse:
    with db.transaction() as conn:
        from x_insight.identity.routes import _require_session

        denied, _actor = _require_session(request, conn)
        if denied is not None:
            return denied
    try:
        report = checker.check(body.medications, body.dataset_version)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except LookupError as exc:
        message = str(exc).lower()
        if "unknown" in message:
            raise HTTPException(404, str(exc)) from None
        raise HTTPException(503, str(exc)) from None
    return JSONResponse(report, headers={"Cache-Control": "private, no-store"})


@router.get("/ddi/current")
def get_ddi_current(request: Request) -> JSONResponse:
    with db.transaction() as conn:
        from x_insight.identity.routes import _require_session

        denied, _actor = _require_session(request, conn)
        if denied is not None:
            return denied
        row = (
            conn.execute(
                text(
                    "SELECT version, dataset_hash, terminology_provenance "
                    "FROM ddi_dataset_releases "
                    "ORDER BY created_at DESC, version DESC LIMIT 1"
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(404, "No DDI dataset release available.")
    catalog_version = checker.catalog_version_for(row["terminology_provenance"])
    return JSONResponse(
        {
            "dataset_version": row["version"],
            "catalog_version": catalog_version,
            "dataset_hash": row["dataset_hash"],
        },
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/drugs")
def list_drugs(request: Request, query: str = "", limit: int = 25) -> JSONResponse:
    bounded = max(1, min(limit, 100))
    with db.transaction() as conn:
        from x_insight.identity.routes import _require_session

        denied, _actor = _require_session(request, conn)
        if denied is not None:
            return denied
        row = (
            conn.execute(
                text(
                    "SELECT evidence, terminology_provenance "
                    "FROM ddi_dataset_releases "
                    "ORDER BY created_at DESC, version DESC LIMIT 1"
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(404, "Drug catalog is not available.")
    evidence = row["evidence"]
    if not isinstance(evidence, list):
        raise HTTPException(503, "Drug catalog is invalid.")
    catalog_version = _catalog_version(row["terminology_provenance"])
    concepts: set[str] = set()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        pair_key = item.get("pair_key")
        if not isinstance(pair_key, str) or ":" not in pair_key:
            continue
        parts = pair_key.split(":")
        if len(parts) != 2 or not all(part for part in parts):
            continue
        concepts.add(parts[0])
        concepts.add(parts[1])
    needle = normalize(query) if query else ""
    if needle:
        matched = sorted(cid for cid in concepts if needle in cid)
    else:
        matched = sorted(concepts)
    results = [{"concept_id": cid, "canonical_name": cid} for cid in matched[:bounded]]
    return JSONResponse(
        {"catalog_version": catalog_version, "query": query, "results": results},
        headers={"Cache-Control": "private, no-store"},
    )
