"""S18 slice 1 DDI publication gates: reject invalid releases, atomic import.

Gates G1-G5 (see tests/ddi/test_publish.py docstring): counts, resolution,
provenance, review, atomicity. No LLM/network at publish time; original
sources are only read, never modified. Synthetic test manifests stay
test-only and are never released defaults.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from x_insight import db
from x_insight.ddi.ingestion import PARSER_VERSION, build
from x_insight.ddi.terminology import canonical_pair_key

_REVIEWED_CATEGORIES = frozenset({"contraindicated", "serious"})
_COVERAGE_SCOPES = frozenset({"complete", "limited"})


class PublishRejectedError(ValueError):
    """Publication gate failure; nothing is imported."""


def _manifest_path(value: Any) -> Path | None:
    if value is None:
        return None
    return Path(str(value))


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PublishRejectedError(f"unreadable {label}: {path}") from exc


def _check_source_inventory(
    manifest: dict[str, Any], sources_dir: Path
) -> list[dict[str, Any]]:
    inventory = manifest.get("source_inventory")
    if not isinstance(inventory, list):
        raise PublishRejectedError("absent source inventory")
    indexed: dict[str, Any] = {}
    for item in inventory:
        if isinstance(item, dict) and isinstance(item.get("relative_path"), str):
            indexed[item["relative_path"]] = item
    try:
        discovered = sorted(
            path.relative_to(sources_dir).as_posix()
            for path in sources_dir.rglob("*.txt")
            if path.is_file()
        )
    except OSError as exc:
        raise PublishRejectedError(f"unreadable sources dir: {sources_dir}") from exc
    for relative_path in discovered:
        item = indexed.get(relative_path)
        data = _read_bytes(sources_dir / relative_path, "source file")
        if (
            not isinstance(item, dict)
            or item.get("sha256") != hashlib.sha256(data).hexdigest()
            or item.get("byte_count") != len(data)
        ):
            raise PublishRejectedError(f"source inventory mismatch: {relative_path}")
    return [item for item in inventory if isinstance(item, dict)]


def _check_terminology_provenance(
    manifest: dict[str, Any], terminology: Path | None
) -> dict[str, Any] | None:
    if terminology is None:
        raw = manifest.get("terminology_provenance")
        return raw if isinstance(raw, dict) else None
    provenance = manifest.get("terminology_provenance")
    if not isinstance(provenance, dict):
        raise PublishRejectedError("absent terminology provenance")
    expected = provenance.get("sha256")
    actual = hashlib.sha256(_read_bytes(terminology, "terminology")).hexdigest()
    if not isinstance(expected, str) or expected != actual:
        raise PublishRejectedError("terminology provenance mismatch")
    return provenance


def _check_counts(report: dict[str, Any]) -> None:
    for document in report.get("documents", []):
        if not isinstance(document, dict):
            raise PublishRejectedError("invalid build report")
        for check in document.get("count_checks", []):
            if not isinstance(check, dict) or check.get("ok") is not True:
                raise PublishRejectedError(
                    "count mismatch: "
                    f"{document.get('relative_path', '?')} "
                    f"{(check.get('category') if isinstance(check, dict) else '?')}"
                )
    if report.get("ok") is not True:
        raise PublishRejectedError("build report not ok")


def _coverage_gaps(report: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (unresolved_names, failed_document_paths) for coverage gating."""
    terminology_report = report.get("terminology")
    if not isinstance(terminology_report, dict):
        raise PublishRejectedError("unresolvable terminology")
    unresolved = terminology_report.get("unresolved_names", [])
    if not isinstance(unresolved, list):
        raise PublishRejectedError("invalid terminology report")
    documents = report.get("documents", [])
    if not isinstance(documents, list):
        raise PublishRejectedError("invalid build report")
    failed = [
        doc.get("relative_path", "?")
        for doc in documents
        if not isinstance(doc, dict) or doc.get("ok") is not True
    ]
    names = [name for name in unresolved if isinstance(name, str)]
    paths = [path for path in failed if isinstance(path, str)]
    return names, paths


def _approved_exclusion_names(exclusions: list[Any]) -> set[str]:
    return {
        item["name"]
        for item in exclusions
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and item.get("decision") == "approved"
    }


def _merged_exclusions(manifest: dict[str, Any]) -> list[Any]:
    """Legacy ``coverage_exclusions`` plus governing ``coverage.exclusions``."""
    legacy = manifest.get("coverage_exclusions", [])
    coverage = manifest.get("coverage")
    scoped: Any = []
    if isinstance(coverage, dict):
        scoped = coverage.get("exclusions", [])
    if not isinstance(legacy, list) or not isinstance(scoped, list):
        raise PublishRejectedError("invalid coverage exclusions")
    return list(legacy) + list(scoped)


def _check_resolution(report: dict[str, Any], exclusions: list[Any]) -> None:
    unresolved, _ = _coverage_gaps(report)
    if not isinstance(exclusions, list):
        raise PublishRejectedError("invalid coverage exclusions")
    covered = _approved_exclusion_names(exclusions)
    missing = [name for name in unresolved if name not in covered]
    if missing:
        raise PublishRejectedError(f"unresolved entities: {sorted(missing)[:5]}")


def _check_corrections(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the management-overlay correction records (S18 slice 3).

    Only ``decision == "approved"`` records with a non-empty reviewer apply;
    anything else (unapproved, anonymous, or missing a corrected value) is
    malformed and rejects. Overlays never touch source files.
    """
    raw = manifest.get("corrections", [])
    if not isinstance(raw, list):
        raise PublishRejectedError("invalid corrections")
    checked: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise PublishRejectedError("invalid correction record")
        management = item.get("corrected_management")
        severity = item.get("corrected_severity")
        if (
            not isinstance(item.get("relative_path"), str)
            or not item["relative_path"]
            or not isinstance(item.get("category"), str)
            or not item["category"]
            or not isinstance(item.get("entry_name"), str)
            or not item["entry_name"]
            or not isinstance(item.get("span"), dict)
            or not isinstance(item.get("reviewer"), str)
            or not item["reviewer"]
            or item.get("decision") != "approved"
            or not (
                (isinstance(management, str) and management)
                or (isinstance(severity, str) and severity)
            )
        ):
            raise PublishRejectedError(
                f"unapproved or malformed correction: {item.get('entry_name')!r}"
            )
        checked.append(dict(item))
    return checked


def _check_coverage(manifest: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Validate the explicit coverage record; return it normalized for storage.

    ``scope`` missing or outside {complete, limited} rejects. ``complete``
    rejects whenever any unresolved name or failed document exists, even with
    exclusions. ``limited`` publishes only when every gap carries an approved
    exclusion (failed documents match by relative_path).
    """
    coverage = manifest.get("coverage")
    if not isinstance(coverage, dict):
        raise PublishRejectedError("coverage record required")
    scope = coverage.get("scope")
    if scope not in _COVERAGE_SCOPES:
        raise PublishRejectedError("coverage scope must be complete or limited")
    exclusions = _merged_exclusions(manifest)
    unresolved, failed = _coverage_gaps(report)
    if scope == "complete" and (unresolved or failed):
        raise PublishRejectedError("incomplete corpus cannot publish as complete")
    _check_resolution(report, exclusions)
    covered = _approved_exclusion_names(exclusions)
    uncovered_failed = [path for path in failed if path not in covered]
    if uncovered_failed:
        raise PublishRejectedError(
            f"uncovered failed documents: {sorted(uncovered_failed)[:5]}"
        )
    scoped = coverage.get("exclusions", [])
    stored_exclusions = (
        [dict(item) for item in scoped if isinstance(item, dict)]
        if isinstance(scoped, list)
        else []
    )
    return {"scope": scope, "exclusions": stored_exclusions}


def _check_review(
    manifest: dict[str, Any], candidates: dict[str, Any]
) -> dict[str, Any]:
    reviewer = manifest.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer:
        raise PublishRejectedError("reviewer required")
    if manifest.get("decision") != "approved":
        raise PublishRejectedError("approved decision required")
    approvals = manifest.get("approvals", [])
    if not isinstance(approvals, list):
        raise PublishRejectedError("invalid approvals")
    approved = {
        (item.get("category"), item.get("entry_name"))
        for item in approvals
        if isinstance(item, dict)
        and item.get("decision") == "approved"
        and isinstance(item.get("reviewer"), str)
        and item["reviewer"]
    }
    for document in candidates.get("documents", []):
        if not isinstance(document, dict):
            raise PublishRejectedError("invalid build candidates")
        for category in document.get("categories", []):
            if not isinstance(category, dict):
                raise PublishRejectedError("invalid build candidates")
            if category.get("category") not in _REVIEWED_CATEGORIES:
                continue
            for entry in category.get("entries", []):
                if not isinstance(entry, dict):
                    raise PublishRejectedError("invalid build candidates")
                key = (category["category"], entry.get("name_text"))
                if key not in approved:
                    raise PublishRejectedError(
                        f"unreviewed evidence: {key[0]}/{key[1]}"
                    )
    exclusions = manifest.get("coverage_exclusions", [])
    if not isinstance(exclusions, list):
        raise PublishRejectedError("invalid coverage exclusions")
    return {
        "reviewer": reviewer,
        "decision": "approved",
        "approvals": approvals,
        "coverage_exclusions": exclusions,
    }


def build_corpus_report(
    candidates: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    """Pure summary over ingestion build output for owner review (S18 slice 2)."""
    candidate_docs = candidates.get("documents", [])
    if not isinstance(candidate_docs, list):
        candidate_docs = []
    report_docs = report.get("documents", [])
    if not isinstance(report_docs, list):
        report_docs = []

    discovered = len(report_docs)
    processed = len(report_docs)
    passed = sum(
        1 for doc in report_docs if isinstance(doc, dict) and doc.get("ok") is True
    )
    failed = processed - passed

    severity_counts: dict[str, int] = {
        "contraindicated": 0,
        "serious": 0,
        "monitor_closely": 0,
        "minor": 0,
    }
    total_entries = 0
    groups: dict[str, dict[str, Any]] = {}
    high_risk: list[dict[str, Any]] = []
    document_hashes: list[dict[str, Any]] = []

    for doc in candidate_docs:
        if not isinstance(doc, dict):
            continue
        relative_path = doc.get("relative_path")
        if not isinstance(relative_path, str):
            continue
        document_hashes.append(
            {"relative_path": relative_path, "sha256": doc.get("sha256")}
        )
        subject = Path(relative_path).stem
        categories = doc.get("categories", [])
        if not isinstance(categories, list):
            continue
        for category in categories:
            if not isinstance(category, dict):
                continue
            category_key = category.get("category")
            entries = category.get("entries", [])
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name_text = entry.get("name_text")
                if not isinstance(name_text, str):
                    continue
                total_entries += 1
                if isinstance(category_key, str) and category_key in severity_counts:
                    severity_counts[category_key] += 1
                pair_key = canonical_pair_key(subject, name_text)
                span = entry.get("span")
                span_copy = dict(span) if isinstance(span, dict) else span
                raw_text = entry.get("raw_text")
                if not isinstance(raw_text, str):
                    raw_text = ""
                group = groups.setdefault(
                    pair_key, {"severities": set(), "sources": [], "raw_texts": []}
                )
                if isinstance(category_key, str):
                    group["severities"].add(category_key)
                group["sources"].append(
                    {
                        "relative_path": relative_path,
                        "category": category_key,
                        "entry_name": name_text,
                        "span": span_copy,
                    }
                )
                group["raw_texts"].append(raw_text)
                if category_key in _REVIEWED_CATEGORIES:
                    high_risk.append(
                        {
                            "kind": "high_risk",
                            "source_path": relative_path,
                            "span": span_copy,
                            "raw_text": raw_text,
                            "severity": category_key,
                            "entry_name": name_text,
                        }
                    )

    unique_pairs = len(groups)
    conflicts: list[dict[str, Any]] = []
    conflict_records: list[dict[str, Any]] = []
    for pair_key in sorted(groups):
        group = groups[pair_key]
        severities = sorted(group["severities"])
        if len(severities) <= 1:
            continue
        sources = group["sources"]
        conflicts.append(
            {"pair_key": pair_key, "severities": severities, "sources": sources}
        )
        first = sources[0]
        raw_texts = [text for text in group["raw_texts"] if text.strip() != ""]
        conflict_records.append(
            {
                "kind": "conflict",
                "pair_key": pair_key,
                "severities": severities,
                "source_path": first["relative_path"],
                "span": dict(first["span"])
                if isinstance(first["span"], dict)
                else first["span"],
                "raw_text": "\n---\n".join(raw_texts),
                "sources": sources,
            }
        )

    terminology = report.get("terminology")
    if isinstance(terminology, dict) and isinstance(
        terminology.get("unresolved_names"), list
    ):
        unknown_names = list(terminology["unresolved_names"])
    else:
        unknown_names = []

    anomaly_records: list[dict[str, Any]] = []
    for doc in report_docs:
        if not isinstance(doc, dict):
            continue
        source_path = doc.get("relative_path")
        anomalies = doc.get("anomalies", [])
        if not isinstance(anomalies, list):
            continue
        for anomaly in anomalies:
            if not isinstance(anomaly, dict):
                continue
            span = anomaly.get("span")
            record: dict[str, Any] = {
                "kind": "anomaly",
                "source_path": source_path,
                "span": dict(span) if isinstance(span, dict) else span,
                "raw_text": anomaly.get("message")
                if isinstance(anomaly.get("message"), str)
                else "",
                "code": anomaly.get("code"),
                "message": anomaly.get("message"),
            }
            for key in ("category", "declared_count", "parsed_count"):
                if key in anomaly:
                    record[key] = anomaly[key]
            anomaly_records.append(record)

    return {
        "discovered": discovered,
        "processed": processed,
        "passed": passed,
        "failed": failed,
        "severity_counts": severity_counts,
        "total_entries": total_entries,
        "unique_pairs": unique_pairs,
        "duplicate_evidence_count": total_entries - unique_pairs,
        "conflicts": conflicts,
        "unknown_names": unknown_names,
        "document_hashes": document_hashes,
        "parser_version": PARSER_VERSION,
        "review_records": high_risk + conflict_records + anomaly_records,
    }


def _build_evidence(
    candidates: dict[str, Any], corrections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """One row per parsed entry; duplicates kept, severity kept separate.

    ``management`` carries the approved ``corrected_management`` overlay when
    a correction targets exactly this (source path, category, entry name)
    evidence, else None. ``direction`` is the entry's first paragraph
    direction, else None.
    """
    overlay = {
        (
            str(item["relative_path"]),
            str(item["category"]),
            str(item["entry_name"]),
        ): item
        for item in corrections
        if isinstance(item.get("corrected_management"), str)
        and item["corrected_management"]
    }
    documents = candidates.get("documents", [])
    if not isinstance(documents, list):
        raise PublishRejectedError("invalid build candidates")
    rows: list[dict[str, Any]] = []
    for document in documents:
        if not isinstance(document, dict):
            raise PublishRejectedError("invalid build candidates")
        relative_path = document.get("relative_path")
        if not isinstance(relative_path, str):
            raise PublishRejectedError("invalid build candidates")
        subject = Path(relative_path).stem
        categories = document.get("categories", [])
        if not isinstance(categories, list):
            raise PublishRejectedError("invalid build candidates")
        for category in categories:
            if not isinstance(category, dict):
                raise PublishRejectedError("invalid build candidates")
            category_key = category.get("category")
            entries = category.get("entries", [])
            if not isinstance(category_key, str) or not isinstance(entries, list):
                raise PublishRejectedError("invalid build candidates")
            for entry in entries:
                if not isinstance(entry, dict):
                    raise PublishRejectedError("invalid build candidates")
                name_text = entry.get("name_text")
                if not isinstance(name_text, str):
                    raise PublishRejectedError("invalid build candidates")
                direction: dict[str, Any] | None = None
                paragraphs = entry.get("paragraphs", [])
                if isinstance(paragraphs, list) and paragraphs:
                    first = paragraphs[0]
                    if isinstance(first, dict) and isinstance(
                        first.get("direction"), dict
                    ):
                        direction = dict(first["direction"])
                correction = overlay.get((relative_path, category_key, name_text))
                span = entry.get("span")
                raw_text = entry.get("raw_text")
                rows.append(
                    {
                        "pair_key": canonical_pair_key(subject, name_text),
                        "source_severity": category_key,
                        "management": correction["corrected_management"]
                        if correction is not None
                        else None,
                        "direction": direction,
                        "source_path": relative_path,
                        "span": dict(span) if isinstance(span, dict) else span,
                        "raw_text": raw_text if isinstance(raw_text, str) else "",
                    }
                )
    return rows


def publish_release(
    manifest: dict[str, Any], *, database_url: str | None = None
) -> dict[str, Any]:
    """Validate gates G1-G4 plus corrections/coverage, then import atomically.

    Any gate failure raises PublishRejectedError and imports nothing (G5).
    """
    if not isinstance(manifest, dict):
        raise PublishRejectedError("manifest must be a dict")
    sources_value = manifest.get("sources_dir")
    if not isinstance(sources_value, str) or not sources_value:
        raise PublishRejectedError("sources dir required")
    sources_dir = Path(sources_value)
    if not sources_dir.is_dir():
        raise PublishRejectedError(f"unreadable sources dir: {sources_dir}")
    terminology = _manifest_path(manifest.get("terminology"))
    if terminology is not None and not terminology.is_file():
        raise PublishRejectedError(f"unreadable terminology: {terminology}")

    inventory = _check_source_inventory(manifest, sources_dir)
    terminology_provenance = _check_terminology_provenance(manifest, terminology)

    built = build(sources_dir, terminology)
    report = built["report"]
    candidates = built["candidates"]
    _check_counts(report)
    corrections = _check_corrections(manifest)
    coverage = _check_coverage(manifest, report)
    review_record = _check_review(manifest, candidates)
    evidence = _build_evidence(candidates, corrections)

    dataset_hash = hashlib.sha256(
        json.dumps(
            {
                "source_inventory": inventory,
                "terminology_provenance": terminology_provenance,
                "corrections": corrections,
                "coverage": coverage,
                "evidence": evidence,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        version = f"ddi-{dataset_hash[:16]}"

    with db.transaction(database_url) as conn:
        existing = (
            conn.execute(
                text(
                    "SELECT id, dataset_hash, source_inventory, "
                    "terminology_provenance, review_record, corrections, "
                    "coverage, evidence, created_at "
                    "FROM ddi_dataset_releases "
                    "WHERE version = :version"
                ),
                {"version": version},
            )
            .mappings()
            .first()
        )
        if existing is not None:
            # Idempotent republish (S18 slice 4): byte-identical content
            # returns the original record. The lookup is version-keyed with
            # full-content equality: an identical dataset_hash under a
            # distinct explicit version still inserts a new row (both
            # releases coexist), so the hash is never a cross-version
            # dedup key. A default version (ddi-<hash16>) collides exactly
            # when the content hash collides, so it stays idempotent.
            if (
                existing["dataset_hash"] == dataset_hash
                and existing["source_inventory"] == inventory
                and existing["terminology_provenance"] == terminology_provenance
                and existing["review_record"] == review_record
                and existing["corrections"] == corrections
                and existing["coverage"] == coverage
                and existing["evidence"] == evidence
            ):
                created_at = existing["created_at"]
                return {
                    "id": str(existing["id"]),
                    "version": version,
                    "dataset_hash": existing["dataset_hash"],
                    "source_inventory": existing["source_inventory"],
                    "terminology_provenance": existing["terminology_provenance"],
                    "review_record": existing["review_record"],
                    "corrections": existing["corrections"],
                    "coverage": existing["coverage"],
                    "evidence": existing["evidence"],
                    "created_at": created_at.isoformat(),
                }
            raise PublishRejectedError(
                f"version conflict: {version} already published with different content"
            )
        row = (
            conn.execute(
                text(
                    "INSERT INTO ddi_dataset_releases "
                    "(version, dataset_hash, source_inventory, "
                    "terminology_provenance, review_record, corrections, "
                    "coverage, evidence) "
                    "VALUES (:version, :dataset_hash, "
                    "CAST(:source_inventory AS JSONB), "
                    "CAST(:terminology_provenance AS JSONB), "
                    "CAST(:review_record AS JSONB), "
                    "CAST(:corrections AS JSONB), "
                    "CAST(:coverage AS JSONB), "
                    "CAST(:evidence AS JSONB)) "
                    "RETURNING id, created_at"
                ),
                {
                    "version": version,
                    "dataset_hash": dataset_hash,
                    "source_inventory": json.dumps(inventory, sort_keys=True),
                    "terminology_provenance": json.dumps(terminology_provenance),
                    "review_record": json.dumps(review_record, sort_keys=True),
                    "corrections": json.dumps(corrections, sort_keys=True),
                    "coverage": json.dumps(coverage, sort_keys=True),
                    "evidence": json.dumps(evidence, sort_keys=True),
                },
            )
            .mappings()
            .first()
        )
    if row is None:
        raise PublishRejectedError("release insert failed")
    created_at = row["created_at"]
    return {
        "id": str(row["id"]),
        "version": version,
        "dataset_hash": dataset_hash,
        "source_inventory": inventory,
        "terminology_provenance": terminology_provenance,
        "review_record": review_record,
        "corrections": corrections,
        "coverage": coverage,
        "evidence": evidence,
        "created_at": created_at.isoformat(),
    }


def get_release(version: str, *, database_url: str | None = None) -> dict[str, Any]:
    """Return the stored release record for ``version`` (S18 slice 3 read).

    Raises PublishRejectedError when the version is unknown.
    """
    with db.transaction(database_url) as conn:
        row = (
            conn.execute(
                text(
                    "SELECT id, version, dataset_hash, source_inventory, "
                    "terminology_provenance, review_record, corrections, "
                    "coverage, evidence, created_at "
                    "FROM ddi_dataset_releases "
                    "WHERE version = :version"
                ),
                {"version": version},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise PublishRejectedError(f"unknown release version: {version}")
    created_at = row["created_at"]
    return {
        "id": str(row["id"]),
        "version": row["version"],
        "dataset_hash": row["dataset_hash"],
        "source_inventory": row["source_inventory"],
        "terminology_provenance": row["terminology_provenance"],
        "review_record": row["review_record"],
        "corrections": row["corrections"],
        "coverage": row["coverage"],
        "evidence": row["evidence"],
        "created_at": created_at.isoformat(),
    }


def list_releases(*, database_url: str | None = None) -> list[dict[str, Any]]:
    """Return release records oldest-first through the public read seam."""
    with db.transaction(database_url) as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT id, version, dataset_hash, source_inventory, "
                    "terminology_provenance, review_record, created_at "
                    "FROM ddi_dataset_releases "
                    "ORDER BY created_at, version"
                )
            )
            .mappings()
            .all()
        )
    releases: list[dict[str, Any]] = [
        {
            "id": str(row["id"]),
            "version": row["version"],
            "dataset_hash": row["dataset_hash"],
            "source_inventory": row["source_inventory"],
            "terminology_provenance": row["terminology_provenance"],
            "review_record": row["review_record"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
    return releases
