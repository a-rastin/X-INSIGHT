"""S25 slice 1: workflow bundle completeness/review gate (T5 bundle gate only).
S25 slice 2 adds wrong_order and content_mismatch checks.

This is the T5 bundle gate only; registry persistence/activation events
and HTTP routes belong to S24 and are NOT implemented here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from x_insight.contracts import canonical_json
from x_insight.models.semantics import check_admission, decide_activation

REGISTRATION_ORDER: list[str] = [
    "hospitalization",
    "pharmacotherapy",
    "involuntary_care",
    "high_suicide_clozapine",
    "lai_indication_choice",
    "aggression_clozapine",
    "established_case_clozapine",
]

FOLLOWUP_ORDER: list[str] = [
    "tardive_dyskinesia",
    "akathisia",
    "parkinsonism",
    "acute_dystonia",
    "no_improvement_clozapine",
    "continue_or_adjust",
]

_WORKFLOWS: dict[str, list[str]] = {
    "registration": REGISTRATION_ORDER,
    "followup": FOLLOWUP_ORDER,
}


def _err(code: str, message: str, question: str | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message[:500]}
    if question is not None:
        error["question"] = question
    return error


def validate_bundle(
    bundle: dict[str, Any],
    load: Callable[[str], tuple[Any, Any]],
) -> dict[str, Any]:
    """Gate a workflow bundle on completeness and per-question activation.

    Conservative v1 substring guard for plan §7.1 "no implicit result chaining".
    """
    workflow = bundle.get("workflow")
    expected = _WORKFLOWS.get(workflow) if isinstance(workflow, str) else None
    if expected is None:
        return {
            "activatable": False,
            "errors": [_err("unknown_workflow", f"unknown workflow: {workflow!r}")],
            "bundle_hash": None,
            "questions": [],
            "admission": {},
        }

    raw_entries = bundle.get("questions")
    if not isinstance(raw_entries, list):
        return {
            "activatable": False,
            "errors": [_err("malformed_entry", "bundle questions must be a list")],
            "bundle_hash": None,
            "questions": [],
            "admission": {},
        }

    keys: list[str] = []
    malformed = False
    for entry in raw_entries:
        key_ok = isinstance(entry, dict) and isinstance(entry.get("question_key"), str)
        if not key_ok:
            malformed = True
        else:
            keys.append(str(entry.get("question_key")))

    errors: list[dict[str, Any]] = []
    bundle_hash: str | None = None
    if malformed:
        errors.append(_err("malformed_entry", "entry missing string question_key"))
    else:
        payload = {
            "workflow": workflow,
            "questions": [
                {
                    "question_key": entry.get("question_key"),
                    "version": entry.get("version"),
                    "network_hash": entry.get("network_hash"),
                }
                for entry in raw_entries
                if isinstance(entry, dict)
            ],
        }
        bundle_hash = "sha256:" + hashlib.sha256(canonical_json(payload)).hexdigest()

    expected_set = set(expected)
    counts: dict[str, int] = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    for key in expected:
        if key not in counts:
            errors.append(
                _err("missing_question", f"bundle missing question: {key}", key)
            )
    for key in counts:
        if key not in expected_set:
            errors.append(
                _err(
                    "unexpected_question",
                    f"bundle has unexpected question: {key}",
                    key,
                )
            )
        elif counts[key] > 1:
            errors.append(
                _err("duplicate_question", f"bundle duplicates question: {key}", key)
            )

    if not errors and not malformed and keys != expected:
        errors.append(_err("wrong_order", "bundle questions out of workflow order"))

    admission: dict[str, dict[str, Any]] = {}
    if not malformed:
        entry_by_key: dict[str, dict[str, Any]] = {}
        for entry in raw_entries:
            if isinstance(entry, dict):
                qk = entry.get("question_key")
                if isinstance(qk, str) and qk not in entry_by_key:
                    entry_by_key[qk] = entry
        for key in expected:
            if counts.get(key) != 1:
                continue
            try:
                validated, package = load(key)
            except Exception as exc:
                errors.append(_err("load_failed", f"load failed for {key}: {exc}", key))
                continue
            try:
                admission_report = (
                    check_admission(validated) if isinstance(validated, dict) else {}
                )
            except Exception:
                admission_report = {}
            if isinstance(admission_report, dict):
                admitted = admission_report.get("admitted") is True
                raw_meas = admission_report.get("measurements")
                meas: dict[str, Any] = raw_meas if isinstance(raw_meas, dict) else {}
            else:
                admitted = False
                meas = {}
            xml_bytes = meas.get("xml_bytes")
            node_count = meas.get("node_count")
            cpt_cells = meas.get("cpt_cells")
            admission[key] = {
                "admitted": admitted,
                "xml_bytes": xml_bytes if isinstance(xml_bytes, int) else 0,
                "node_count": node_count if isinstance(node_count, int) else 0,
                "cpt_cells": cpt_cells if isinstance(cpt_cells, int) else 0,
            }
            mappings = package.get("mappings") if isinstance(package, dict) else None
            if isinstance(mappings, list):
                for mapping in mappings:
                    if not isinstance(mapping, dict):
                        continue
                    paths = mapping.get("allowed_source_paths")
                    if not isinstance(paths, list):
                        continue
                    for path in paths:
                        if not isinstance(path, str):
                            continue
                        lowered = path.lower()
                        if (
                            lowered.startswith("questions.")
                            or lowered.startswith("questions/")
                            or "posterior" in lowered
                        ):
                            errors.append(
                                _err(
                                    "chained_result",
                                    f"chained result reference disallowed: {path!r}: "
                                    "one question's posterior/outputs must never "
                                    "feed another question's inputs",
                                    key,
                                )
                            )
            provided = entry_by_key.get(key, {}).get("network_hash")
            if provided is not None and provided != "":
                sha: Any = None
                if isinstance(validated, dict):
                    sha = validated.get("source_sha256")
                want = "sha256:" + sha if isinstance(sha, str) else None
                if want is None or provided != want:
                    errors.append(
                        _err("content_mismatch", f"content mismatch for {key}", key)
                    )
            report = decide_activation(validated, package)
            raw = report.get("errors")
            items = raw if isinstance(raw, list) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                code = item.get("code")
                message = item.get("message")
                errors.append(
                    _err(
                        str(code) if isinstance(code, str) else "invalid_report",
                        str(message) if isinstance(message, str) else "invalid report",
                        key,
                    )
                )

    errors.sort(key=lambda e: (str(e.get("code", "")), str(e.get("question") or "")))
    return {
        "activatable": errors == [],
        "errors": errors,
        "bundle_hash": bundle_hash,
        "questions": keys,
        "admission": admission,
    }
