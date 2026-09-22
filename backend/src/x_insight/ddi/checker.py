"""S19 slice 4 DDI checker: pinned dataset/catalog/fingerprint + refusals.

Catalog rule: ``catalog_version`` is the release
``terminology_provenance.terminology_version`` when it is a non-empty
string, else ``TERMINOLOGY_VERSION`` (``ddi-terminology-1``).
Fingerprint: ``content_hash({"resolved": sorted_ids,
"unresolved": sorted_unknown_norms})`` over normalized sorted lists, so
reordered/alias-case inputs share a fingerprint and different meds differ.
Single batched SELECT fetches evidence + coverage + dataset_hash +
terminology_provenance; no network access (no socket imports).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from x_insight import db
from x_insight.cases.history import MEDICATION_REGIMEN_EXCLUDED_FIELDS
from x_insight.contracts import content_hash, to_utc_z, utc_now
from x_insight.ddi.terminology import (
    TERMINOLOGY_VERSION,
    canonical_pair_key,
    normalize,
)

_EVIDENCE_SQL = (
    "SELECT evidence, coverage, dataset_hash, terminology_provenance "
    "FROM ddi_dataset_releases WHERE version = :version"
)

# Display priority: contraindicated > serious > monitor_closely > minor.
# "unknown" (and any unrecognized severity) is never highest; it only sets
# the has_unknown_severity flag so it stays visible, not reassuring.
_SEVERITY_RANK = {
    "contraindicated": 4,
    "serious": 3,
    "monitor_closely": 2,
    "minor": 1,
}


def _summarize(matched: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize one pair's assertion rows (every row retained verbatim).

    Callers only invoke this when ``matched`` is non-empty (interaction
    found). Empty-evidence coverage (covered vs unavailable) is decided in
    ``check`` from the release coverage scope, never here.
    """
    if not matched:
        raise ValueError("no evidence to summarize")
    known: list[str] = []
    for item in matched:
        sev = item.get("source_severity")
        if isinstance(sev, str) and sev in _SEVERITY_RANK:
            known.append(sev)
    highest = max(known, key=lambda sev: _SEVERITY_RANK[sev]) if known else None
    has_unknown = any(
        not isinstance(item, dict) or item.get("source_severity") not in _SEVERITY_RANK
        for item in matched
    )
    seen: dict[str, str] = {}
    for item in matched:
        sev = item.get("source_severity")
        if isinstance(sev, str) and sev in _SEVERITY_RANK and sev not in seen:
            path = item.get("source_path")
            seen[sev] = path if isinstance(path, str) else ""
    conflicts = [{"source_severity": sev, "source_path": seen[sev]} for sev in seen]
    return {
        "status": "interaction_found",
        "highest_known_severity": highest,
        "has_unknown_severity": has_unknown,
        "conflicts": conflicts,
    }


def _coverage_scope(coverage: Any) -> str | None:
    """Return the release coverage scope string when explicitly stored."""
    if isinstance(coverage, dict):
        scope = coverage.get("scope")
        if isinstance(scope, str):
            return scope
    return None


def catalog_version_for(provenance: Any) -> str:
    """Catalog pin per module docstring (explicit fallback, never empty)."""
    if isinstance(provenance, dict):
        version = provenance.get("terminology_version")
        if isinstance(version, str) and version:
            return version
    return TERMINOLOGY_VERSION


def _catalog_version(provenance: Any) -> str:
    """Private alias kept for backward compatibility; use catalog_version_for."""
    return catalog_version_for(provenance)


def check(
    medications: list[dict[str, Any]],
    dataset_version: str,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Check unordered medication pairs against one release's evidence.

    Single DB round trip: one SELECT of the release evidence + coverage
    JSONB, then all pair matching in Python. Resolution is exact normalized
    only. Each entry carries exactly one of ``catalog_drug_id`` (resolved,
    deduplicated) or ``unknown_label`` (always unresolved). Pairs are
    generated over all unique inputs; any pair involving an unknown label
    is coverage_unavailable. Recognized pairs with no evidence are
    covered_no_listed_interaction only under explicit complete scope,
    otherwise coverage_unavailable. Never says safe/no interaction.
    """
    resolved_seen: dict[str, dict[str, Any]] = {}
    unresolved_seen: dict[str, dict[str, Any]] = {}
    for entry in medications:
        if not isinstance(entry, dict):
            raise ValueError(f"medication entry must be a dict: {entry!r}")
        if MEDICATION_REGIMEN_EXCLUDED_FIELDS & set(entry):
            raise ValueError(f"excluded medication regimen field: {entry!r}")
        has_catalog = "catalog_drug_id" in entry
        has_unknown = "unknown_label" in entry
        if has_catalog == has_unknown:
            raise ValueError(
                f"exactly one of catalog_drug_id|unknown_label required: {entry!r}"
            )
        if has_catalog:
            raw = entry["catalog_drug_id"]
            if not isinstance(raw, str):
                raise ValueError(f"catalog_drug_id must be str: {entry!r}")
            concept_id = normalize(raw)
            if not concept_id:
                raise ValueError(f"empty medication id: {entry!r}")
            if concept_id not in resolved_seen:
                resolved_seen[concept_id] = {"concept_id": concept_id}
        else:
            raw = entry["unknown_label"]
            if not isinstance(raw, str):
                raise ValueError(f"unknown_label must be str: {entry!r}")
            norm = normalize(raw)
            if not norm:
                raise ValueError(f"empty unknown label: {entry!r}")
            if norm not in unresolved_seen:
                unresolved_seen[norm] = {"unknown_label": raw}
    unique_ids = sorted(resolved_seen)
    unresolved_norms = sorted(unresolved_seen)

    with db.transaction(database_url) as conn:
        row = (
            conn.execute(
                text(_EVIDENCE_SQL),
                {"version": dataset_version},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise LookupError(f"unknown DDI dataset version: {dataset_version}")
    evidence_rows = row["evidence"]
    if not isinstance(evidence_rows, list):
        raise LookupError(f"invalid evidence for version: {dataset_version}")
    scope = _coverage_scope(row["coverage"])

    pairs: list[dict[str, Any]] = []

    def _empty_resolved_pair(pair_key: str) -> tuple[str, str]:
        if scope == "complete":
            return (
                "covered_no_listed_interaction",
                f"dataset scope complete: no listed interaction for "
                f"{pair_key} in this dataset",
            )
        if scope == "limited":
            return (
                "coverage_unavailable",
                f"dataset scope limited: no evidence for {pair_key}",
            )
        return (
            "coverage_unavailable",
            f"dataset coverage unavailable: no evidence for {pair_key}",
        )

    for i in range(len(unique_ids)):
        for j in range(i + 1, len(unique_ids)):
            pair_key = canonical_pair_key(unique_ids[i], unique_ids[j])
            drug_a, drug_b = sorted((unique_ids[i], unique_ids[j]))
            matched = [
                dict(item)
                for item in evidence_rows
                if isinstance(item, dict) and item.get("pair_key") == pair_key
            ]
            if matched:
                summary = _summarize(matched)
                pairs.append(
                    {
                        "pair_key": pair_key,
                        "drug_a": drug_a,
                        "drug_b": drug_b,
                        "evidence": matched,
                        "status": summary["status"],
                        "highest_known_severity": summary["highest_known_severity"],
                        "has_unknown_severity": summary["has_unknown_severity"],
                        "conflicts": summary["conflicts"],
                        "coverage_basis": (
                            f"interaction evidence for {pair_key} "
                            f"in dataset {dataset_version}"
                        ),
                    }
                )
            else:
                status, basis = _empty_resolved_pair(pair_key)
                pairs.append(
                    {
                        "pair_key": pair_key,
                        "drug_a": drug_a,
                        "drug_b": drug_b,
                        "evidence": [],
                        "status": status,
                        "highest_known_severity": None,
                        "has_unknown_severity": False,
                        "conflicts": [],
                        "coverage_basis": basis,
                    }
                )

    for rid in unique_ids:
        for unk_norm in unresolved_norms:
            unk_label = unresolved_seen[unk_norm]["unknown_label"]
            assert isinstance(unk_label, str)
            pair_key = canonical_pair_key(rid, unk_norm)
            drug_a, drug_b = sorted((rid, unk_norm))
            pairs.append(
                {
                    "pair_key": pair_key,
                    "drug_a": drug_a,
                    "drug_b": drug_b,
                    "evidence": [],
                    "status": "coverage_unavailable",
                    "highest_known_severity": None,
                    "has_unknown_severity": False,
                    "conflicts": [],
                    "coverage_basis": (
                        "coverage unavailable: unknown medication "
                        f"{unk_label} for {pair_key}"
                    ),
                }
            )

    for i in range(len(unresolved_norms)):
        for j in range(i + 1, len(unresolved_norms)):
            label_i = unresolved_seen[unresolved_norms[i]]["unknown_label"]
            label_j = unresolved_seen[unresolved_norms[j]]["unknown_label"]
            assert isinstance(label_i, str)
            assert isinstance(label_j, str)
            pair_key = canonical_pair_key(unresolved_norms[i], unresolved_norms[j])
            drug_a, drug_b = sorted((unresolved_norms[i], unresolved_norms[j]))
            pairs.append(
                {
                    "pair_key": pair_key,
                    "drug_a": drug_a,
                    "drug_b": drug_b,
                    "evidence": [],
                    "status": "coverage_unavailable",
                    "highest_known_severity": None,
                    "has_unknown_severity": False,
                    "conflicts": [],
                    "coverage_basis": (
                        "coverage unavailable: unknown medications "
                        f"{label_i}, {label_j} for {pair_key}"
                    ),
                }
            )

    resolved_medications = [resolved_seen[c] for c in unique_ids]
    unresolved_medications = [unresolved_seen[n] for n in unresolved_norms]
    limitations: list[str] = []
    if unresolved_medications:
        labels = ", ".join(
            str(entry["unknown_label"]) for entry in unresolved_medications
        )
        limitations.append(
            f"unresolved medications present: {labels}; "
            "pairs involving them have coverage_unavailable"
        )
    fingerprint = content_hash({"resolved": unique_ids, "unresolved": unresolved_norms})
    return {
        "dataset_version": dataset_version,
        "catalog_version": catalog_version_for(row["terminology_provenance"]),
        "dataset_hash": row["dataset_hash"],
        "medication_fingerprint": fingerprint,
        "generated_at": to_utc_z(utc_now()),
        "resolved_medications": resolved_medications,
        "unresolved_medications": unresolved_medications,
        "pairs": pairs,
        "limitations": limitations,
    }
