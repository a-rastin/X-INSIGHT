"""S22 slice 1 (RED tracer) through the model-admission seam (T5).

Public interface under test (not yet implemented):
    x_insight.models.semantics.check_semantics(validated: dict) -> dict

Each fixture is a small synthetic XSD-valid XMLBIF document (not clinical
content, never BNs/ as oracle). Each test proves XSD-valid-but-semantic-invalid:
validate_xmlbif first (xsd_report valid True), then check_semantics must report
executable False with the expected distinct error code.
"""

from __future__ import annotations

from x_insight.models.semantics import check_semantics
from x_insight.models.validation import validate_xmlbif


def test_cycle_is_nonexecutable() -> None:
    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Cycle_Test</NAME>'
        b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>A</FOR><GIVEN>B</GIVEN>"
        b"<TABLE>0.8 0.2 0.1 0.9</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
        b"<TABLE>0.7 0.3 0.4 0.6</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    validated = validate_xmlbif(payload)
    assert validated["xsd_report"]["valid"] is True

    result = check_semantics(validated)
    assert result["executable"] is False
    assert "cycle" in [e["code"] for e in result["errors"]]


def test_missing_definition_is_nonexecutable() -> None:
    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Missing_Test</NAME>'
        b"<VARIABLE><NAME>M</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>C</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>M</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    validated = validate_xmlbif(payload)
    assert validated["xsd_report"]["valid"] is True

    result = check_semantics(validated)
    assert result["executable"] is False
    assert "missing_definition" in [e["code"] for e in result["errors"]]


def test_wrong_dimensions_is_nonexecutable() -> None:
    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Dims_Test</NAME>'
        b"<VARIABLE><NAME>P</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>X</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>P</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>X</FOR><GIVEN>P</GIVEN>"
        b"<TABLE>0.5 0.5 0.5</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    validated = validate_xmlbif(payload)
    assert validated["xsd_report"]["valid"] is True

    result = check_semantics(validated)
    assert result["executable"] is False
    assert "wrong_dimensions" in [e["code"] for e in result["errors"]]


def test_unnormalized_is_nonexecutable() -> None:
    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Norm_Test</NAME>'
        b"<VARIABLE><NAME>N</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>N</FOR><TABLE>0.5 0.6</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    validated = validate_xmlbif(payload)
    assert validated["xsd_report"]["valid"] is True

    result = check_semantics(validated)
    assert result["executable"] is False
    assert "unnormalized" in [e["code"] for e in result["errors"]]


def test_empty_outcomes_is_nonexecutable() -> None:
    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Empty_Test</NAME>'
        b"<VARIABLE><NAME>E</NAME></VARIABLE>"
        b"<DEFINITION><FOR>E</FOR><TABLE>1.0</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    validated = validate_xmlbif(payload)
    assert validated["xsd_report"]["valid"] is True

    result = check_semantics(validated)
    assert result["executable"] is False
    assert "empty_outcomes" in [e["code"] for e in result["errors"]]


def test_valid_root_parent_ordering_passes() -> None:
    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Valid_Order_Test</NAME>'
        b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
        b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    validated = validate_xmlbif(payload)
    assert validated["xsd_report"]["valid"] is True

    result = check_semantics(validated)
    assert result["executable"] is True
    assert result["errors"] == []


def test_decision_utility_remain_drafts() -> None:
    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Decision_Utility_Test</NAME>'
        b'<VARIABLE TYPE="decision"><NAME>D</NAME>'
        b"<OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b'<VARIABLE TYPE="utility"><NAME>U</NAME>'
        b"<OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>D</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>U</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>B</FOR><TABLE>0.6 0.4</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    validated = validate_xmlbif(payload)
    assert validated["xsd_report"]["valid"] is True

    result = check_semantics(validated)
    assert result["executable"] is False
    assert "unsupported_kind" in [e["code"] for e in result["errors"]]


def test_supplied_bns_remain_inactive() -> None:
    from pathlib import Path

    files = sorted(Path("/root/X-INSIGHT/BNs").glob("BN-0*.xml")) + sorted(
        Path("/root/X-INSIGHT/BNs").glob("BN-1*.xml")
    )
    assert len(files) == 11
    for path in files:
        validated = validate_xmlbif(path.read_bytes())
        result = check_semantics(validated)
        assert result["executable"] is False, f"{path.name} must remain inactive"


# --- S22 slice 3 (RED): activation gate decide_activation (T5) ---
#
# Agreed interface (dev-backend to implement in semantics.py):
#     decide_activation(validated, package, semantic_report=None)
#     -> {"activatable": bool, "reasons": list[str],
#         "errors": [{"code": str, "message": str}]}
#
# validate + check_semantics = import/draft inspection;
# decide_activation = activation gate (executable semantics + complete
# reviewed package). Synthetic fixtures only, never BNs/ as oracle.


def _valid_validated() -> dict:
    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Valid_Order_Test</NAME>'
        b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
        b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    return validate_xmlbif(payload)


def _base_package() -> dict:
    return {
        "question_key": "q_synth_01",
        "mappings": [{"node_id": "B", "allowed_source_paths": ["history.some_field"]}],
        "prompt": "Synthetic prompt for tests.",
        "template": "Synthetic template for B.",
        "query_nodes": ["B"],
        "query_states": {"B": ["yes"]},
        "applicability": "True",
        "review": {
            "decision": "approved",
            "reviewer": "synthetic",
            "date": "2026-09-22",
        },
    }


def test_complete_package_activates() -> None:
    from x_insight.models.semantics import decide_activation

    validated = _valid_validated()
    result = decide_activation(validated, _base_package())
    assert result["activatable"] is True
    assert result["errors"] == []


def test_missing_mappings_prompt_template_block_activation() -> None:
    from x_insight.models.semantics import decide_activation

    validated = _valid_validated()

    pkg = _base_package()
    pkg["mappings"] = None
    result = decide_activation(validated, pkg)
    assert result["activatable"] is False
    assert "missing_mappings" in [e["code"] for e in result["errors"]]

    pkg = _base_package()
    pkg["prompt"] = ""
    result = decide_activation(validated, pkg)
    assert result["activatable"] is False
    assert "missing_prompt" in [e["code"] for e in result["errors"]]

    pkg = _base_package()
    pkg["template"] = ""
    result = decide_activation(validated, pkg)
    assert result["activatable"] is False
    assert "missing_template" in [e["code"] for e in result["errors"]]


def test_note_source_path_blocks_activation() -> None:
    from x_insight.models.semantics import decide_activation

    validated = _valid_validated()
    pkg = _base_package()
    pkg["mappings"] = [{"node_id": "B", "allowed_source_paths": ["notes.text"]}]
    result = decide_activation(validated, pkg)
    assert result["activatable"] is False
    assert "note_source_path" in [e["code"] for e in result["errors"]]


def test_unreviewed_package_blocks_activation() -> None:
    from x_insight.models.semantics import decide_activation

    validated = _valid_validated()

    pkg = _base_package()
    del pkg["review"]
    result = decide_activation(validated, pkg)
    assert result["activatable"] is False
    assert "unreviewed_package" in [e["code"] for e in result["errors"]]

    pkg = _base_package()
    del pkg["review"]
    pkg["reviewed"] = True
    result = decide_activation(validated, pkg)
    assert result["activatable"] is False
    assert "unreviewed_package" in [e["code"] for e in result["errors"]]

    pkg = _base_package()
    pkg["review"] = {
        "decision": "rejected",
        "reviewer": "synthetic",
        "date": "2026-09-22",
    }
    result = decide_activation(validated, pkg)
    assert result["activatable"] is False
    assert "unreviewed_package" in [e["code"] for e in result["errors"]]


def test_undeclared_query_state_blocks_activation() -> None:
    from x_insight.models.semantics import decide_activation

    validated = _valid_validated()

    pkg = _base_package()
    pkg["query_nodes"] = ["NoSuchNode"]
    pkg["query_states"] = {}
    result = decide_activation(validated, pkg)
    assert result["activatable"] is False
    assert "undeclared_query" in [e["code"] for e in result["errors"]]

    pkg = _base_package()
    pkg["query_nodes"] = ["A"]
    pkg["query_states"] = {"A": ["nope"]}
    result = decide_activation(validated, pkg)
    assert result["activatable"] is False
    assert "undeclared_state" in [e["code"] for e in result["errors"]]


def test_unsafe_expression_blocks_activation() -> None:
    from x_insight.models.semantics import decide_activation

    validated = _valid_validated()
    pkg = _base_package()
    pkg["applicability"] = "__import__('os')"
    result = decide_activation(validated, pkg)
    assert result["activatable"] is False
    assert "unsafe_expression" in [e["code"] for e in result["errors"]]

    cycle_payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Cycle_Test</NAME>'
        b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>A</FOR><GIVEN>B</GIVEN>"
        b"<TABLE>0.8 0.2 0.1 0.9</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
        b"<TABLE>0.7 0.3 0.4 0.6</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    cycle_validated = validate_xmlbif(cycle_payload)
    assert cycle_validated["xsd_report"]["valid"] is True
    result = decide_activation(cycle_validated, _base_package())
    assert result["activatable"] is False
    assert "semantic_not_executable" in [e["code"] for e in result["errors"]]


# --- S22 slice 4 (RED): configured admission limits + diagnostics (T5) ---
#
# Agreed interface (dev-backend to implement in semantics.py):
#     DEFAULT_LIMITS = {"max_xml_bytes": 262144, "max_nodes": 64,
#                       "max_cpt_cells": 10000}
#     check_admission(validated: dict, limits: dict | None = None) -> dict
#     -> {"admitted": bool, "measurements": {"xml_bytes": int,
#         "node_count": int, "cpt_cells": int}, "limits": dict,
#         "diagnostics": list[str], "errors": [{"code": str, "message": str}]}
#     decide_activation(..., limits=None, admission_report=None) backwards
#     compatible; admission failure -> activatable False + admission_rejected.
#
# Numeric thresholds are engineering anti-abuse bounds from actual model
# measurements (2026-09-22 corpus max 60681B / 32 nodes / 880 cells,
# BN-04 largest), not clinical thresholds. Synthetic fixtures only.


def test_admission_reports_measurements() -> None:
    from x_insight.models.semantics import DEFAULT_LIMITS, check_admission

    assert DEFAULT_LIMITS == {
        "max_xml_bytes": 262144,
        "max_nodes": 64,
        "max_cpt_cells": 10000,
    }
    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Valid_Order_Test</NAME>'
        b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
        b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    validated = validate_xmlbif(payload)
    assert validated["xsd_report"]["valid"] is True

    result = check_admission(validated)
    assert result["admitted"] is True
    assert result["measurements"]["xml_bytes"] == len(payload)
    assert result["measurements"]["node_count"] == 2
    assert result["measurements"]["cpt_cells"] == 6
    assert result["limits"] == {
        "max_xml_bytes": 262144,
        "max_nodes": 64,
        "max_cpt_cells": 10000,
    }
    assert result["errors"] == []
    diagnostics = result["diagnostics"]
    assert diagnostics == sorted(diagnostics)
    assert any("xml_bytes=" in d for d in diagnostics)
    assert any("node_count=" in d for d in diagnostics)
    assert any("cpt_cells=" in d for d in diagnostics)


def test_admission_rejects_configured_limits() -> None:
    from pathlib import Path

    from x_insight.models.semantics import DEFAULT_LIMITS, check_admission
    from x_insight.models.validation import validate_xmlbif as _validate

    payload = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Valid_Order_Test</NAME>'
        b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
        b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    validated = _validate(payload)
    tiny = {"max_xml_bytes": 10, "max_nodes": 1, "max_cpt_cells": 1}
    result = check_admission(validated, tiny)
    assert result["admitted"] is False
    codes = [e["code"] for e in result["errors"]]
    assert "xml_too_large" in codes
    assert "too_many_nodes" in codes
    assert "too_many_cells" in codes

    largest = Path("/root/X-INSIGHT/BNs/BN-04.xml").read_bytes()
    validated_large = _validate(largest)
    large_result = check_admission(validated_large, DEFAULT_LIMITS)
    assert large_result["admitted"] is True


def test_activation_requires_admission() -> None:
    from x_insight.models.semantics import decide_activation

    validated = _valid_validated()
    tiny = {"max_xml_bytes": 10, "max_nodes": 1, "max_cpt_cells": 1}
    result = decide_activation(validated, _base_package(), limits=tiny)
    assert result["activatable"] is False
    assert "admission_rejected" in [e["code"] for e in result["errors"]]
