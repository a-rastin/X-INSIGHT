"""S25 slice 1 RED: question-package contract and review harness (T5).

Template branch convention (chosen for slice 1, documented here): branches
are keyed by posterior outcome state -- the query node B states ("no"/"yes")
each get one branch dict {"heading", "body"}, plus "needs_clarification"
and "not_applicable" branches. Bodies use escaped-value slots {SLOT}; the
top-level "slots" list must contain every {slot} referenced in any body.

Target public interface (not yet implemented; these tests must fail with
ModuleNotFoundError/ImportError as red evidence)::

    x_insight.models.question_packages.validate_package(
        manifest, validated, prompt_text, template, review, examples) -> dict
    x_insight.models.question_packages.load_package(package_dir) -> tuple

Synthetic fixtures only (never content/questions/ or BNs/ as oracle, never
clinical content): two-node network A (root, [no, yes]) -> B ([A], [no, yes]).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from x_insight.models.question_packages import (  # type: ignore[import-not-found]
    load_package,
    validate_package,
)
from x_insight.models.validation import validate_xmlbif

_XMLBIF = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>SyntheticCPT</NAME>'
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
    b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)

_TEMPLATE_VERSION = "synthetic-template-v1"
_PROMPT_VERSION = "synthetic-prompt-v1"


def _prompt_text() -> str:
    return (
        "Estimate every CPT table in percentages for the fixed synthetic network. "
        "Use only the scoped projection as conditioning context. "
        "Do not write a plan, do not choose applicability, "
        "do not add patient facts beyond the projection."
    )


def _template() -> dict[str, Any]:
    return {
        "template_version": _TEMPLATE_VERSION,
        "branches": {
            "no": {
                "heading": "synthetic review heading no",
                "body": "synthetic review body no with input {A_state}",
            },
            "yes": {
                "heading": "synthetic review heading yes",
                "body": "synthetic review body yes with input {A_state}",
            },
            "needs_clarification": {
                "heading": "synthetic clarification heading",
                "body": "synthetic clarification body naming {missing_fields}",
            },
            "not_applicable": {
                "heading": "synthetic not applicable heading",
                "body": "synthetic not applicable body",
            },
        },
        "deterministic_urgent_flag": {
            "conditions": [
                {"when": "synthetic urgent condition", "text": "synthetic urgent text"}
            ],
            "otherwise": "synthetic otherwise text",
        },
        "mapping_rule": (
            "Render the matching branch ONLY as a review prompt; "
            "the posterior maximum is not a treatment rule; "
            "the physician decides."
        ),
        "slots": ["A_state", "missing_fields"],
    }


def _manifest(validated: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "question_key": "synthetic_example",
        "title": "synthetic example question",
        "workflow": "registration",
        "version": "v1",
        "review_status": "reviewed",
        "network_file": "network.xml",
        "network_hash": "sha256:" + str(validated["source_sha256"]),
        "source_refs": [],
        "declared_node_order": ["A", "B"],
        "variables": [
            {
                "node_id": "A",
                "xmlbif_kind": "nature",
                "patient_value_type": "enum",
                "states": ["no", "yes"],
                "ordered_parents": [],
            },
            {
                "node_id": "B",
                "xmlbif_kind": "nature",
                "patient_value_type": "enum",
                "states": ["no", "yes"],
                "ordered_parents": ["A"],
            },
        ],
        "patient_mappings": [
            {
                "node_id": "A",
                "allowed_source_paths": ["encounters.draft_data.synthetic_field"],
                "typed_transform": "synthetic typed transform",
                "time_window": "synthetic current encounter window",
                "usage": "both",
                "missing_policy": "synthetic missing policy blocks on required input",
            }
        ],
        "applicability": {
            "expression": "encounter.kind == 'registration'",
            "expression_language": "synthetic allowlist of == comparisons",
            "required_fields": ["encounter.kind"],
            "unknown_policy": (
                "required unknown yields needs_clarification; "
                "gate-absent yields not_applicable"
            ),
        },
        "cpt_contract": {
            "units": "percentages [0,100]",
            "all_nodes_mandatory": True,
            "row_order": "child state fastest; first parent slowest",
            "rows": [
                {"node_id": "A", "parent_ids": [], "row_count": 1},
                {"node_id": "B", "parent_ids": ["A"], "row_count": 2},
            ],
        },
        "query_nodes": ["B"],
        "evidence_mappings": [
            {"node_id": "A", "evidence": "synthetic mapped state as hard evidence"}
        ],
        "impossible_evidence_policy": "fail with explicit error; never approximate",
        "likelihood_evidence": "disabled",
        "prompt_version": _PROMPT_VERSION,
        "template_version": _TEMPLATE_VERSION,
        "reviewed_result_mapping": "synthetic reviewed result mapping",
        "numerical_tolerances": {
            "percentage_row_sum_absolute": 1e-06,
            "probability_sum_after_divide_by_100_absolute": 1e-08,
            "replay_posterior_absolute": 1e-09,
        },
        "context_output_resource_limits": {"synthetic_limit": "synthetic value"},
        "engine_configuration": {"inference": "deterministic exact"},
        "review": {
            "reviewer": "synthetic reviewer",
            "decision": "approved",
            "date": "2026-09-22",
        },
    }


def _review() -> dict[str, Any]:
    return {
        "package_version": "v1",
        "question_key": "synthetic_example",
        "workflow": "registration",
        "review_status": "reviewed",
        "reviewer": "synthetic reviewer",
        "decision": "approved",
        "date": "2026-09-22",
        "sources": [
            {
                "path": "synthetic/source.txt",
                "bytes": 42,
                "sha256": "synthetic-sha256",
                "locators": ["synthetic locator"],
                "classification": "source_derived",
            }
        ],
        "question_enumeration": {
            "specific_question": "synthetic specific question",
            "intended_setting": "synthetic intended setting",
            "output_meanings": {"no": "synthetic meaning no", "yes": "synthetic meaning yes"},
        },
        "source_classification": {"synthetic/source.txt": "source_derived"},
        "owner_questions": [
            {
                "id": "synthetic-q1",
                "question": "synthetic owner question",
                "proposal": "synthetic proposal",
            }
        ],
        "source_comparison": "synthetic source comparison narrative",
        "graph_decision": {
            "nodes": ["A", "B"],
            "edges": [["A", "B"]],
            "why_this_shape": "synthetic rationale for this shape",
        },
        "reference_table_provenance": {
            "status": "synthetic structural placeholder only; zero clinical validity"
        },
        "admission_measurements": {
            "xml_bytes": len(_XMLBIF),
            "nodes": 2,
            "cpt_cells": 6,
        },
        "unresolved_assumptions": [],
        "independent_examples_provenance": "synthetic independent provenance",
        "double_counting_rationale": (
            "synthetic rationale: conditioning once in Bayes rule is a single "
            "update; LLM conditions estimates on context while inference "
            "instantiates the same observed state"
        ),
    }


def _examples() -> dict[str, Any]:
    return {
        "package_version": "v1",
        "clinical_cases": [
            {"name": "synthetic ordinary", "kind": "ordinary"},
            {"name": "synthetic missing", "kind": "needs_clarification"},
            {"name": "synthetic gate absent", "kind": "not_applicable"},
        ],
        "numerical_fixture": {
            "provenance": "synthetic hand-worked provenance",
            "checks": [
                {
                    "name": "synthetic check",
                    "work": "synthetic hand-worked calculation",
                }
            ],
        },
    }


def _complete_package() -> (
    tuple[dict[str, Any], dict[str, Any], str, dict[str, Any], dict[str, Any], dict[str, Any]]
):
    validated = validate_xmlbif(_XMLBIF)
    manifest = _manifest(validated)
    return (manifest, validated, _prompt_text(), _template(), _review(), _examples())


def test_complete_synthetic_package_validates() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert set(result.keys()) == {"valid", "errors"}
    assert result["valid"] is True
    assert result["errors"] == []
    for error in result["errors"]:
        assert set(error.keys()) == {"code", "message"}
        assert isinstance(error["code"], str) and error["code"]
        assert isinstance(error["message"], str) and error["message"]


def test_load_package_reads_synthetic_dir(tmp_path: Path) -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    package_dir = tmp_path / "synthetic_example"
    package_dir.mkdir()
    (package_dir / "network.xml").write_bytes(_XMLBIF)
    (package_dir / "manifest.json").write_text(json.dumps(manifest))
    (package_dir / "prompt.txt").write_text(prompt_text)
    (package_dir / "template.json").write_text(json.dumps(template))
    (package_dir / "review.json").write_text(json.dumps(review))
    (package_dir / "examples.json").write_text(json.dumps(examples))

    loaded = load_package(package_dir)
    assert isinstance(loaded, tuple) and len(loaded) == 6
    l_manifest, l_validated, l_prompt, l_template, l_review, l_examples = loaded
    assert l_manifest["question_key"] == "synthetic_example"
    assert l_manifest["network_hash"] == "sha256:" + hashlib.sha256(_XMLBIF).hexdigest()
    assert l_validated["source_sha256"] == validated["source_sha256"]
    assert isinstance(l_prompt, str) and l_prompt
    assert isinstance(l_template, dict) and l_template
    assert isinstance(l_review, dict) and l_review
    assert isinstance(l_examples, dict) and l_examples

    result = validate_package(
        l_manifest, l_validated, l_prompt, l_template, l_review, l_examples
    )
    assert result == {"valid": True, "errors": []}


def test_unknown_source_path_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    manifest = json.loads(json.dumps(manifest))
    manifest["patient_mappings"][0]["allowed_source_paths"] = [
        "mystery.unknown_field"
    ]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "unknown_source_path" in [e["code"] for e in result["errors"]]


def test_note_mapping_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    manifest = json.loads(json.dumps(manifest))
    manifest["patient_mappings"][0]["allowed_source_paths"] = [
        "encounters.draft_data.notes.page"
    ]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "note_source_path" in [e["code"] for e in result["errors"]]


def test_chained_result_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    manifest = json.loads(json.dumps(manifest))
    manifest["patient_mappings"][0]["allowed_source_paths"] = [
        "questions.high_suicide_clozapine.posterior"
    ]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "chained_result" in [e["code"] for e in result["errors"]]


def test_double_use_without_rationale_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    review = json.loads(json.dumps(review))
    del review["double_counting_rationale"]
    assert manifest["patient_mappings"][0]["usage"] == "both"
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "double_use_without_rationale" in [e["code"] for e in result["errors"]]


def test_incomplete_cpt_contract_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    manifest_a = json.loads(json.dumps(manifest))
    manifest_a["cpt_contract"]["rows"] = [manifest_a["cpt_contract"]["rows"][0]]
    result_a = validate_package(
        manifest_a, validated, prompt_text, template, review, examples
    )
    assert result_a["valid"] is False
    assert "incomplete_cpt_contract" in [e["code"] for e in result_a["errors"]]

    manifest_b = json.loads(json.dumps(manifest))
    manifest_b["cpt_contract"]["rows"][1]["row_count"] = 1
    result_b = validate_package(
        manifest_b, validated, prompt_text, template, review, examples
    )
    assert result_b["valid"] is False
    assert "incomplete_cpt_contract" in [e["code"] for e in result_b["errors"]]


def test_arbitrary_expression_rejected() -> None:
    for bad in ("A + B == 'x'", "eval('A')", "notes.foo == 'x'"):
        manifest, validated, prompt_text, template, review, examples = (
            _complete_package()
        )
        manifest = json.loads(json.dumps(manifest))
        manifest["applicability"]["expression"] = bad
        result = validate_package(
            manifest, validated, prompt_text, template, review, examples
        )
        assert result["valid"] is False, bad
        assert "unsafe_expression" in [e["code"] for e in result["errors"]], bad


def test_review_missing_source_comparison_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    review = json.loads(json.dumps(review))
    del review["source_comparison"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "review_incomplete" in [e["code"] for e in result["errors"]]


def test_review_missing_graph_decision_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    review = json.loads(json.dumps(review))
    del review["graph_decision"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "review_incomplete" in [e["code"] for e in result["errors"]]


def test_review_missing_provenance_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    review = json.loads(json.dumps(review))
    del review["reference_table_provenance"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "review_incomplete" in [e["code"] for e in result["errors"]]


def test_examples_missing_numerical_fixture_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    examples = json.loads(json.dumps(examples))
    del examples["numerical_fixture"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "examples_incomplete" in [e["code"] for e in result["errors"]]


def test_review_missing_admission_measurements_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    review = json.loads(json.dumps(review))
    del review["admission_measurements"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "review_incomplete" in [e["code"] for e in result["errors"]]


def test_review_missing_question_enumeration_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    review = json.loads(json.dumps(review))
    del review["question_enumeration"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "review_incomplete" in [e["code"] for e in result["errors"]]


def test_review_missing_owner_questions_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    review = json.loads(json.dumps(review))
    del review["owner_questions"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "review_incomplete" in [e["code"] for e in result["errors"]]


def test_review_source_missing_locators_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    review = json.loads(json.dumps(review))
    del review["sources"][0]["locators"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "review_incomplete" in [e["code"] for e in result["errors"]]


def test_review_graph_missing_rationale_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    review = json.loads(json.dumps(review))
    del review["graph_decision"]["why_this_shape"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "review_incomplete" in [e["code"] for e in result["errors"]]


def test_examples_check_missing_work_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    examples = json.loads(json.dumps(examples))
    del examples["numerical_fixture"]["checks"][0]["work"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "examples_incomplete" in [e["code"] for e in result["errors"]]


def test_template_undeclared_output_state_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    template = json.loads(json.dumps(template))
    template["branches"]["yes"]["posterior_state"] = "nonexistent_state"
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "undeclared_template_state" in [e["code"] for e in result["errors"]]


def test_template_unsupported_operator_rejected() -> None:
    for bad_snippet in ("${evil}", "{% evil %}"):
        manifest, validated, prompt_text, template, review, examples = (
            _complete_package()
        )
        template = json.loads(json.dumps(template))
        template["branches"]["yes"]["body"] += " " + bad_snippet
        result = validate_package(
            manifest, validated, prompt_text, template, review, examples
        )
        assert result["valid"] is False, bad_snippet
        assert "unsupported_operator" in [e["code"] for e in result["errors"]], (
            bad_snippet
        )


def test_template_undeclared_slot_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    template = json.loads(json.dumps(template))
    template["branches"]["yes"]["body"] += " {UndeclaredSlot}"
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "undeclared_template_state" in [e["code"] for e in result["errors"]]


def test_template_missing_deterministic_flag_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    template = json.loads(json.dumps(template))
    del template["deterministic_urgent_flag"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "template_missing" in [e["code"] for e in result["errors"]]


def test_template_argmax_without_review_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    template = json.loads(json.dumps(template))
    template["mapping_rule"] = "Give the single best drug."
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "template_missing" in [e["code"] for e in result["errors"]]


def test_template_missing_needs_clarification_rejected() -> None:
    manifest, validated, prompt_text, template, review, examples = _complete_package()
    template = json.loads(json.dumps(template))
    del template["branches"]["needs_clarification"]
    result = validate_package(
        manifest, validated, prompt_text, template, review, examples
    )
    assert result["valid"] is False
    assert "missing_branch" in [e["code"] for e in result["errors"]]
