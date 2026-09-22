"""Frozen analysis snapshots (S40 slices 1-4).

Pure helpers only: freeze the analytical facts allowed into model-facing
projections, plus every pinned version reference. Shared notes, patient
names/ID/phone, secondary plans, and UI state are never read here, so they
cannot leak into the snapshot, fingerprint, or per-question projections.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from x_insight.contracts import content_hash

_ALLOWED_SOURCE_PREFIXES: tuple[str, ...] = (
    "encounters.draft_data.diagnosis",
    "encounters.draft_data.history",
    "encounters.draft_data.effects",
    "encounters.draft_data.medications",
    "encounters.draft_data.ddi_report",
    "encounters.draft_data.panss",
    "encounters.draft_data.cssrs",
    "encounters.draft_data.synthetic_conflict",
    "encounter.draft_data.diagnosis",
    "encounter.draft_data.history",
    "encounter.draft_data.effects",
    "encounter.draft_data.medications",
    "encounter.draft_data.ddi_report",
    "encounter.draft_data.panss",
    "encounter.draft_data.cssrs",
    "encounter.draft_data.synthetic_conflict",
    "encounters.kind",
    "encounter.kind",
    "patients.clinical_status",
    "encounters.clinical_status",
    "encounter.clinical_status",
)


def _as_dict(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


_APPLICABILITY_STATUSES: tuple[str, ...] = (
    "ready",
    "not_applicable",
    "needs_clarification",
)

_APPLICABILITY_UNKNOWN_POLICY = "needs_clarification"


def _contains_questions_ref(value: Any) -> bool:
    """True if any nested string contains a cross-question ``questions.`` ref."""
    if isinstance(value, str):
        return "questions." in value
    if isinstance(value, Mapping):
        return any(_contains_questions_ref(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_questions_ref(item) for item in value)
    return False


def _first_questions_ref(value: Any) -> str | None:
    """Return the first nested string containing ``questions.``, else None."""
    if isinstance(value, str):
        return value if "questions." in value else None
    if isinstance(value, Mapping):
        for item in value.values():
            found = _first_questions_ref(item)
            if found is not None:
                return found
        return None
    if isinstance(value, list):
        for item in value:
            found = _first_questions_ref(item)
            if found is not None:
                return found
        return None
    return None


def _parse_gate_expression(expression: Any) -> tuple[str, bool] | None:
    """Parse ``<path> == true|false``; return (lhs, expected) else None."""
    if not isinstance(expression, str):
        return None
    parts = expression.split("==")
    if len(parts) != 2:
        return None
    lhs = parts[0].strip()
    rhs = parts[1].strip()
    if not lhs:
        return None
    if rhs == "true":
        return (lhs, True)
    if rhs == "false":
        return (lhs, False)
    return None


def _find_invalid_applicability(entry: Mapping[str, Any]) -> str | None:
    """Validate the test-only ``applicability`` gate carrier, else None.

    Valid shape is exactly one ``== true`` / ``== false`` comparison whose
    left side equals one entry of ``required_fields``; every path must be an
    allowlisted patient-fact path and ``unknown_policy`` must be
    ``needs_clarification``. Any ``questions.`` reference is invalid.
    Absent (or None) gates are allowed: slices 1-3 bundles carry no gate.
    """
    if "applicability" not in entry:
        return None
    gate = entry.get("applicability")
    if gate is None:
        return None
    if not isinstance(gate, dict):
        return "<non-dict-applicability>"
    expression = gate.get("expression")
    required = gate.get("required_fields")
    policy = gate.get("unknown_policy")
    if _contains_questions_ref(expression) or _contains_questions_ref(required):
        found = _first_questions_ref([expression, required])
        return found or "<questions-ref>"
    if not isinstance(required, list) or not required:
        return "<invalid-required-fields>"
    for field in required:
        if not isinstance(field, str) or not field:
            return "<non-string-required-field>"
        if not is_allowed_source_path(field):
            return field
    parsed = _parse_gate_expression(expression)
    if parsed is None:
        return expression if isinstance(expression, str) else "<invalid-expression>"
    lhs, _expected = parsed
    if lhs not in required:
        return expression if isinstance(expression, str) else "<invalid-expression>"
    if not is_allowed_source_path(lhs):
        return lhs
    if policy != _APPLICABILITY_UNKNOWN_POLICY:
        return "<invalid-unknown-policy>"
    return None


def is_allowed_source_path(path: str) -> bool:
    """Allowlist: analysis-visible facts only; notes/PII never allowed."""
    if "notes" in path.lower():
        return False
    return path.startswith(_ALLOWED_SOURCE_PREFIXES)


def find_invalid_source_path(pins: Mapping[str, Any]) -> str | None:
    """Return the first disallowed content reference, else None.

    Test-only carrier lives under pins.questions[].patient_mappings.
    Slice-4 gate carrier lives under pins.questions[].applicability, and
    any evidence/query mapping under a questions[] entry is also scanned.
    Prompt text never authorizes extra sources and is never scanned.
    Any ``questions.`` substring in a scanned mapping is INVALID_CONTENT.
    """
    questions = pins.get("questions")
    if not isinstance(questions, list):
        return None
    for entry in questions:
        if not isinstance(entry, dict):
            continue
        mappings = entry.get("patient_mappings")
        if mappings is None:
            pass
        elif not isinstance(mappings, list):
            pass
        else:
            for mapping in mappings:
                if not isinstance(mapping, dict):
                    continue
                paths = mapping.get("allowed_source_paths")
                if not isinstance(paths, list):
                    continue
                for item in paths:
                    if not isinstance(item, str) or not item:
                        return "<non-string>"
                    if "questions." in item:
                        return item
                    if not is_allowed_source_path(item):
                        return item
        gate_invalid = _find_invalid_applicability(entry)
        if gate_invalid is not None:
            return gate_invalid
        for key, value in entry.items():
            if key in (
                "question_key",
                "version",
                "network_hash",
                "patient_mappings",
                "applicability",
                "prompt",
            ):
                continue
            lowered = key.lower()
            if "evidence" not in lowered and "query" not in lowered:
                continue
            found = _first_questions_ref(value)
            if found is not None:
                return found
    return None


def evaluate_applicability(
    facts: Mapping[str, Any], applicability: dict[str, Any] | None
) -> tuple[str, str]:
    """Evaluate a gate against FROZEN facts.

    Any required field resolving to unknown/missing/not_assessed/conflict
    yields needs_clarification; otherwise the single ``==`` comparison
    yields ready (true) or not_applicable (false). Unknown is never false.
    Reasons are non-empty and name the deciding field.
    """
    if applicability is None:
        return ("ready", "no applicability gate pinned; ready by default")
    required = applicability.get("required_fields")
    expression = applicability.get("expression")
    parsed = _parse_gate_expression(expression)
    if not isinstance(required, list) or not required or parsed is None:
        return (
            "needs_clarification",
            "invalid applicability gate; needs clarification",
        )
    lhs, expected = parsed
    for field in required:
        if not isinstance(field, str) or not field:
            return (
                "needs_clarification",
                "invalid applicability gate; needs clarification",
            )
        status, _value = _resolve_status_value(facts, field)
        if status != "observed":
            return (
                "needs_clarification",
                f"{field} is {status}; needs clarification before executing",
            )
    _lhs_status, lhs_value = _resolve_status_value(facts, lhs)
    rhs_token = "true" if expected else "false"
    if lhs_value == expected:
        return (
            "ready",
            f"{lhs} == {rhs_token} holds (value {lhs_value!r}); ready",
        )
    return (
        "not_applicable",
        f"{lhs} == {rhs_token} is false (value {lhs_value!r}); not applicable",
    )


def _resolve_status_value(
    facts: Mapping[str, Any], source_path: str
) -> tuple[str, Any]:
    """Map frozen source dict {status, value} to (status, value)."""
    prefix = "encounters.draft_data."
    alt = "encounter.draft_data."
    if source_path.startswith(prefix):
        rel = source_path[len(prefix) :]
    elif source_path.startswith(alt):
        rel = source_path[len(alt) :]
    else:
        return ("missing", None)
    current: Any = facts
    for part in rel.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return ("missing", None)
    if isinstance(current, dict):
        status = current.get("status")
        value = current.get("value")
        if status == "known":
            return ("observed", value)
        if status == "unknown":
            return ("missing", None)
        if status == "not_assessed":
            return ("not_assessed", None)
        if status == "conflict":
            return ("conflict", None)
        return ("missing", None)
    return ("missing", None)


def build_snapshot(
    encounter_row: Mapping[str, Any],
    patient_row: Mapping[str, Any],
    draft_data: Mapping[str, Any],
    bundle_pointer: Mapping[str, Any],
) -> tuple[dict[str, Any], str, str]:
    """Freeze analytical facts + pins; return (snapshot, fingerprint, hash).

    ``snapshot_hash`` covers the full frozen snapshot (facts + pins +
    encounter revision). ``fingerprint`` is the analysis fingerprint
    (analytical facts + pinned content only), driving later
    staleness/signing checks.
    """
    draft = dict(draft_data) if isinstance(draft_data, dict) else {}
    history = _as_dict(draft.get("history")) or {}
    effects = _as_dict(draft.get("effects")) or {}
    ddi_report = _as_dict(draft.get("ddi_report")) or {}
    pins = _as_dict(bundle_pointer.get("pins")) or {}
    baseline = encounter_row.get("baseline_encounter_id")

    history_version = history.get("definition_version")
    if not isinstance(history_version, str):
        effects_version = effects.get("definition_version")
        history_version = effects_version if isinstance(effects_version, str) else None
    ddi_version = ddi_report.get("dataset_version")
    if not isinstance(ddi_version, str):
        ddi_version = None

    facts: dict[str, Any] = {
        "kind": encounter_row.get("kind"),
        "baseline_encounter_id": str(baseline) if baseline else None,
        "clinical_status": patient_row.get("clinical_status"),
        "diagnosis": draft.get("diagnosis"),
        "panss": draft.get("panss"),
        "cssrs": draft.get("cssrs"),
        "history": draft.get("history"),
        "effects": draft.get("effects"),
        "medications": draft.get("medications"),
        "ddi_report": draft.get("ddi_report"),
    }
    synthetic_conflict = draft.get("synthetic_conflict")
    if isinstance(synthetic_conflict, dict):
        facts["synthetic_conflict"] = synthetic_conflict
    pinned: dict[str, Any] = {
        "bundle_hash": bundle_pointer.get("bundle_hash"),
        "pins": pins,
        "history_definition_version": history_version,
        "ddi_dataset_version": ddi_version,
        "provider_revision": None,
        "engine_pin": None,
    }
    snapshot: dict[str, Any] = {
        "encounter_revision": encounter_row.get("revision"),
        "facts": facts,
        "pinned": pinned,
    }
    fingerprint = content_hash({"facts": facts, "pinned": pinned})
    snapshot_hash = content_hash(snapshot)
    return snapshot, fingerprint, snapshot_hash


def build_projections(
    facts: Mapping[str, Any],
    pins: Mapping[str, Any],
    encounter_revision: int,
) -> list[tuple[str, dict[str, Any], str]]:
    """Build one typed projection per pinned question.

    Each projection carries only frozen facts (never patient rows or notes)
    plus a ``variables`` list with exactly
    {node_id, patient_type, status, value, source_path, source_revision}.
    Only declared mapped nodes appear. Each projection also persists its
    slice-4 applicability gate outcome (``applicability`` plus
    ``applicability_reason``) inside the same JSONB payload so no new
    migration is needed. Returns triples.
    """
    questions = pins.get("questions")
    if not isinstance(questions, list):
        return []
    triples: list[tuple[str, dict[str, Any], str]] = []
    for entry in questions:
        if not isinstance(entry, dict):
            continue
        key = entry.get("question_key")
        if not isinstance(key, str) or not key:
            continue
        raw_mappings = entry.get("patient_mappings")
        mappings: list[Any] = raw_mappings if isinstance(raw_mappings, list) else []
        variables: list[dict[str, Any]] = []
        for item in mappings:
            if not isinstance(item, dict):
                continue
            node_id = item.get("node_id")
            paths = item.get("allowed_source_paths")
            typed = item.get("typed_transform")
            if not isinstance(node_id, str) or not node_id:
                continue
            if not isinstance(paths, list) or not paths:
                continue
            source_path: str | None = None
            for candidate in paths:
                if isinstance(candidate, str) and candidate:
                    source_path = candidate
                    break
            if source_path is None:
                continue
            if not isinstance(typed, str) or not typed:
                continue
            status, value = _resolve_status_value(facts, source_path)
            if status != "observed":
                value = None
            variables.append(
                {
                    "node_id": node_id,
                    "patient_type": typed,
                    "status": status,
                    "value": value,
                    "source_path": source_path,
                    "source_revision": encounter_revision,
                }
            )
        projection: dict[str, Any] = {
            "question_key": key,
            "question_version": entry.get("version"),
            "network_hash": entry.get("network_hash"),
            "facts": dict(facts),
            "variables": variables,
        }
        gate = entry.get("applicability")
        gate_dict = gate if isinstance(gate, dict) else None
        status, reason = evaluate_applicability(facts, gate_dict)
        if status not in _APPLICABILITY_STATUSES:
            status = "needs_clarification"
        if not isinstance(reason, str) or not reason.strip():
            reason = f"{status} for {key}"
        projection["applicability"] = status
        projection["applicability_reason"] = reason
        triples.append((key, projection, content_hash(projection)))
    return triples
