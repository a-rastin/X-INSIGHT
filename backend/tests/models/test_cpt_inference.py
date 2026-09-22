"""S23 slice 1 RED tracer through the CPT/inference seam (T5).

Proposed S23 public interface (smallest sensible, chosen for this slice)::

    x_insight.models.inference.validate_cpt_response(response: dict) -> dict
    x_insight.models.inference.build_effective_artifact(validated: dict,
        accepted: dict) -> dict
    x_insight.models.inference.infer(artifact: dict, target: str,
        state: str, evidence: dict[str, str]) -> float

``validate_cpt_response`` enforces plan section 7.4 (exact identity/hash,
node/parent/state order, one table per node, one row per ordered Cartesian
parent configuration, percentages in [0, 100], percentage sums within
absolute 1e-6 of 100, no normalize/clip/repair). ``build_effective_artifact``
populates every table into a run-local XML artifact (probabilities /100,
probability sums within 1e-8, frozen hash; registered XML unchanged).
``infer`` runs deterministic exact inference (posterior replay within 1e-9).

Synthetic mathematical fixture only (never BNs/ as oracle, never clinical
content): two-node network A (root, states [no, yes]) -> B (parent [A],
states [no, yes]). CPT percentages: A [80, 20]; B [90, 10] for A=no,
[30, 70] for A=yes. Independently worked (not from any implementation):
P(B=yes) = 0.8*0.1 + 0.2*0.7 = 0.08 + 0.14 = 0.22;
P(B=yes|A=yes) = 0.70 direct; P(A=yes|B=yes) = 0.14/0.22 = 7/11.
"""

from __future__ import annotations

from typing import Any

import pytest

from x_insight.models.inference import (  # type: ignore[import-not-found]
    build_effective_artifact,
    infer,
    validate_cpt_response,
)
from x_insight.models.validation import validate_xmlbif

POSTERIOR_TOL = 1e-9
PCT_SUM_TOL = 1e-6
PROB_SUM_TOL = 1e-8

EXPECTED_P_B_YES = 0.22
EXPECTED_P_B_YES_GIVEN_A_YES = 0.70
EXPECTED_P_A_YES_GIVEN_B_YES = 7 / 11

_XMLBIF = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>SyntheticCPT</NAME>'
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
    b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)


def _cpt_response(network_hash: str) -> dict[str, Any]:
    return {
        "question_key": "synthetic_example",
        "network_version": "v1",
        "network_hash": network_hash,
        "tables": [
            {
                "node_id": "A",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [80, 20]}],
            },
            {
                "node_id": "B",
                "parent_ids": ["A"],
                "states": ["no", "yes"],
                "rows": [
                    {"parent_states": ["no"], "percentages": [90, 10]},
                    {"parent_states": ["yes"], "percentages": [30, 70]},
                ],
            },
        ],
    }


def test_registered_xml_is_xsd_valid() -> None:
    validated = validate_xmlbif(_XMLBIF)
    assert validated["xsd_report"]["valid"] is True
    assert validated["xsd_report"]["errors"] == []
    assert validated["nodes"] == ["A", "B"]
    assert validated["states"] == {"A": ["no", "yes"], "B": ["no", "yes"]}
    assert validated["edges"] == [("A", "B")]


def test_cpt_response_shape_matches_plan_contract() -> None:
    response = _cpt_response("0" * 64)
    assert response["question_key"] == "synthetic_example"
    assert response["network_version"] == "v1"
    assert isinstance(response["network_hash"], str)
    tables = response["tables"]
    assert [t["node_id"] for t in tables] == ["A", "B"]
    assert tables[0]["parent_ids"] == []
    assert tables[0]["states"] == ["no", "yes"]
    assert tables[1]["parent_ids"] == ["A"]
    assert tables[1]["states"] == ["no", "yes"]
    assert [r["parent_states"] for r in tables[0]["rows"]] == [[]]
    assert [r["parent_states"] for r in tables[1]["rows"]] == [["no"], ["yes"]]
    for table in tables:
        for row in table["rows"]:
            for value in row["percentages"]:
                assert isinstance(value, (int, float)) and not isinstance(value, bool)
                assert 0 <= value <= 100
            assert abs(sum(row["percentages"]) - 100) <= PCT_SUM_TOL
            assert abs(sum(v / 100 for v in row["percentages"]) - 1.0) <= PROB_SUM_TOL


def test_exact_inference_posteriors_via_public_interface() -> None:
    validated = validate_xmlbif(_XMLBIF)
    response = _cpt_response(validated["source_sha256"])
    accepted = validate_cpt_response(response)
    artifact = build_effective_artifact(validated, accepted)
    assert infer(artifact, "B", "yes", {}) == pytest.approx(
        EXPECTED_P_B_YES, abs=POSTERIOR_TOL
    )
    assert infer(artifact, "B", "yes", {"A": "yes"}) == pytest.approx(
        EXPECTED_P_B_YES_GIVEN_A_YES, abs=POSTERIOR_TOL
    )
    assert infer(artifact, "A", "yes", {"B": "yes"}) == pytest.approx(
        EXPECTED_P_A_YES_GIVEN_B_YES, abs=POSTERIOR_TOL
    )


# S23 slice 2 strict-rejection tests (RED). Existing 3 tests above untouched.


def _validated_and_accepted() -> tuple[dict[str, Any], dict[str, Any]]:
    validated = validate_xmlbif(_XMLBIF)
    accepted = validate_cpt_response(_cpt_response(validated["source_sha256"]))
    return validated, accepted


def _mutated_accepted() -> tuple[dict[str, Any], dict[str, Any]]:
    import copy as _copy

    validated, accepted = _validated_and_accepted()
    return validated, _copy.deepcopy(accepted)


def test_reject_omitted_root_table() -> None:
    validated, accepted = _mutated_accepted()
    accepted["tables"] = [t for t in accepted["tables"] if t["node_id"] != "A"]
    with pytest.raises(ValueError):
        build_effective_artifact(validated, accepted)


def test_reject_omitted_child_row() -> None:
    validated, accepted = _mutated_accepted()
    for t in accepted["tables"]:
        if t["node_id"] == "B":
            t["rows"] = [t["rows"][0]]
    with pytest.raises(ValueError):
        build_effective_artifact(validated, accepted)


def test_reject_missing_tables_key() -> None:
    validated = validate_xmlbif(_XMLBIF)
    response = _cpt_response(validated["source_sha256"])
    del response["tables"]
    with pytest.raises(ValueError):
        validate_cpt_response(response)


def test_reject_duplicate_row() -> None:
    validated, accepted = _mutated_accepted()
    for t in accepted["tables"]:
        if t["node_id"] == "B":
            t["rows"] = [dict(t["rows"][0]), dict(t["rows"][0])]
    with pytest.raises(ValueError):
        build_effective_artifact(validated, accepted)


def test_reject_duplicate_table() -> None:
    import copy as _copy

    validated = validate_xmlbif(_XMLBIF)
    response = _cpt_response(validated["source_sha256"])
    response["tables"].append(_copy.deepcopy(response["tables"][0]))
    with pytest.raises(ValueError):
        validate_cpt_response(response)


def test_reject_changed_table_order() -> None:
    validated, accepted = _mutated_accepted()
    accepted["tables"] = list(reversed(accepted["tables"]))
    with pytest.raises(ValueError):
        build_effective_artifact(validated, accepted)


def test_reject_changed_row_order() -> None:
    validated, accepted = _mutated_accepted()
    for t in accepted["tables"]:
        if t["node_id"] == "B":
            t["rows"] = list(reversed(t["rows"]))
    with pytest.raises(ValueError):
        build_effective_artifact(validated, accepted)


def test_reject_changed_states_order() -> None:
    validated, accepted = _mutated_accepted()
    for t in accepted["tables"]:
        if t["node_id"] == "B":
            t["states"] = ["yes", "no"]
    with pytest.raises(ValueError):
        build_effective_artifact(validated, accepted)


def test_reject_changed_parent_ids_order() -> None:
    xml_2p = (
        b'<BIF VERSION="0.3"><NETWORK><NAME>Synthetic2P</NAME>'
        b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<VARIABLE><NAME>C</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
        b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>B</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
        b"<DEFINITION><FOR>C</FOR><GIVEN>A</GIVEN><GIVEN>B</GIVEN>"
        b"<TABLE>0.9 0.1 0.8 0.2 0.3 0.7 0.2 0.8</TABLE></DEFINITION>"
        b"</NETWORK></BIF>"
    )
    validated = validate_xmlbif(xml_2p)
    response: dict[str, Any] = {
        "question_key": "synthetic_2p",
        "network_version": "v1",
        "network_hash": validated["source_sha256"],
        "tables": [
            {
                "node_id": "A",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [80, 20]}],
            },
            {
                "node_id": "B",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [50, 50]}],
            },
            {
                "node_id": "C",
                "parent_ids": ["A", "B"],
                "states": ["no", "yes"],
                "rows": [
                    {"parent_states": ["no", "no"], "percentages": [90, 10]},
                    {"parent_states": ["no", "yes"], "percentages": [80, 20]},
                    {"parent_states": ["yes", "no"], "percentages": [30, 70]},
                    {"parent_states": ["yes", "yes"], "percentages": [20, 80]},
                ],
            },
        ],
    }
    accepted = validate_cpt_response(response)
    import copy as _copy

    swapped = _copy.deepcopy(accepted)
    for t in swapped["tables"]:
        if t["node_id"] == "C":
            t["parent_ids"] = ["B", "A"]
    with pytest.raises(ValueError):
        build_effective_artifact(validated, swapped)


def test_reject_extra_table() -> None:
    import copy as _copy

    validated, accepted = _mutated_accepted()
    extra = _copy.deepcopy(accepted["tables"][0])
    extra["node_id"] = "C"
    accepted["tables"].append(extra)
    with pytest.raises(ValueError):
        build_effective_artifact(validated, accepted)


def test_reject_extra_row() -> None:
    import copy as _copy

    validated, accepted = _mutated_accepted()
    for t in accepted["tables"]:
        if t["node_id"] == "B":
            t["rows"].append(_copy.deepcopy(t["rows"][0]))
    with pytest.raises(ValueError):
        build_effective_artifact(validated, accepted)


def test_reject_extra_top_level_field() -> None:
    validated = validate_xmlbif(_XMLBIF)
    response = _cpt_response(validated["source_sha256"])
    response["extra_field"] = "not-allowed"
    with pytest.raises(ValueError):
        validate_cpt_response(response)


def test_reject_extra_row_field() -> None:
    validated = validate_xmlbif(_XMLBIF)
    response = _cpt_response(validated["source_sha256"])
    response["tables"][0]["rows"][0]["extra"] = 1
    with pytest.raises(ValueError):
        validate_cpt_response(response)


def test_reject_boolean_percentage() -> None:
    validated = validate_xmlbif(_XMLBIF)
    response = _cpt_response(validated["source_sha256"])
    response["tables"][0]["rows"][0]["percentages"] = [True, 100]
    with pytest.raises(ValueError):
        validate_cpt_response(response)


def test_reject_string_percentage() -> None:
    validated = validate_xmlbif(_XMLBIF)
    response = _cpt_response(validated["source_sha256"])
    response["tables"][0]["rows"][0]["percentages"] = ["80", 20]
    with pytest.raises(ValueError):
        validate_cpt_response(response)


def test_reject_null_percentage() -> None:
    validated = validate_xmlbif(_XMLBIF)
    response = _cpt_response(validated["source_sha256"])
    response["tables"][0]["rows"][0]["percentages"] = [None, 100]
    with pytest.raises(ValueError):
        validate_cpt_response(response)


def test_reject_nonfinite_percentage() -> None:
    validated = validate_xmlbif(_XMLBIF)
    for bad in (float("nan"), float("inf"), float("-inf")):
        response = _cpt_response(validated["source_sha256"])
        response["tables"][0]["rows"][0]["percentages"] = [bad, 50]
        with pytest.raises(ValueError):
            validate_cpt_response(response)


def test_reject_out_of_range_percentage() -> None:
    validated = validate_xmlbif(_XMLBIF)
    for bad_row in ([-1, 101], [100.01, -0.01]):
        response = _cpt_response(validated["source_sha256"])
        response["tables"][0]["rows"][0]["percentages"] = bad_row
        with pytest.raises(ValueError):
            validate_cpt_response(response)


def test_reject_wrong_sum_percentage() -> None:
    validated = validate_xmlbif(_XMLBIF)
    # Clearly wrong sums must raise, never normalize/repair.
    for bad_row in ([80, 21], [50, 50.000002], [50.000001, 50.000001]):
        response = _cpt_response(validated["source_sha256"])
        response["tables"][0]["rows"][0]["percentages"] = bad_row
        with pytest.raises(ValueError):
            validate_cpt_response(response)


# S23 slice 3 RED: asymmetric multi-parent + effective-XML preservation.
# Existing 22 tests above untouched.
#
# Synthetic 3-node fixture (never BNs/ as oracle, never clinical content):
# roots X, Y with states [no, yes]; child C with parent_ids ["X", "Y"]
# (GIVEN order X then Y), states [no, yes]. CPT percentages are deliberately
# ASYMMETRIC under X<->Y so a transpose bug is detectable:
#   X root [60, 40]  -> P(X=no)=0.6, P(X=yes)=0.4
#   Y root [70, 30]  -> P(Y=no)=0.7, P(Y=yes)=0.3
#   C rows in canonical first-parent-slowest order:
#     (no,no)  -> [95, 5]   P(C=yes|no,no)   = 0.05
#     (no,yes) -> [80, 20]  P(C=yes|no,yes)  = 0.20
#     (yes,no) -> [40, 60]  P(C=yes|yes,no)  = 0.60
#     (yes,yes)-> [10, 90]  P(C=yes|yes,yes) = 0.90
#
# Hand arithmetic (independent of any implementation):
#   P(C=yes) = 0.6*0.7*0.05 + 0.6*0.3*0.20 + 0.4*0.7*0.60 + 0.4*0.3*0.90
#            = 0.021 + 0.036 + 0.168 + 0.108 = 0.333
#   P(C=yes|X=yes) = 0.7*0.60 + 0.3*0.90 = 0.42 + 0.27 = 0.69
#   P(X=yes,C=yes) = 0.4*0.7*0.60 + 0.4*0.3*0.90 = 0.168 + 0.108 = 0.276
#   P(X=yes|C=yes) = 0.276 / 0.333 = 276/333 = 92/111
# A transposed X/Y mapping would instead report P(C=yes|X=no,Y=yes)=0.60
# (correct: 0.20), P(C=yes|X=yes,Y=no)=0.20 (correct: 0.60), and a marginal
# P(C=yes) = 0.021+0.108+0.056+0.108 = 0.293 (correct: 0.333).
# All posterior assertions use tolerance 1e-9.

_XY_XMLBIF = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>SyntheticXY</NAME>'
    b"<PROPERTY>synthetic=asymmetric-xy-fixture</PROPERTY>"
    b"<VARIABLE><NAME>X</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>Y</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>C</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>X</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>Y</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>C</FOR><GIVEN>X</GIVEN><GIVEN>Y</GIVEN>"
    b"<PROPERTY>synthetic=child-table-note</PROPERTY>"
    # Registered TABLEs are uniform structural placeholders only; the
    # accepted CPT response below populates the run-local effective XML.
    b"<TABLE>0.5 0.5 0.5 0.5 0.5 0.5 0.5 0.5</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)

# Flattened canonical probabilities (first parent slowest, child fastest).
_XY_EXPECTED_FLAT: dict[str, list[float]] = {
    "X": [0.6, 0.4],
    "Y": [0.7, 0.3],
    "C": [0.95, 0.05, 0.8, 0.2, 0.4, 0.6, 0.1, 0.9],
}


def _xy_cpt_response(network_hash: str) -> dict[str, Any]:
    return {
        "question_key": "synthetic_asymmetric_xy",
        "network_version": "v1",
        "network_hash": network_hash,
        "tables": [
            {
                "node_id": "X",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [60, 40]}],
            },
            {
                "node_id": "Y",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [70, 30]}],
            },
            {
                "node_id": "C",
                "parent_ids": ["X", "Y"],
                "states": ["no", "yes"],
                "rows": [
                    {"parent_states": ["no", "no"], "percentages": [95, 5]},
                    {"parent_states": ["no", "yes"], "percentages": [80, 20]},
                    {"parent_states": ["yes", "no"], "percentages": [40, 60]},
                    {"parent_states": ["yes", "yes"], "percentages": [10, 90]},
                ],
            },
        ],
    }


def _xy_validated_and_artifact() -> tuple[dict[str, Any], dict[str, Any]]:
    validated = validate_xmlbif(_XY_XMLBIF)
    accepted = validate_cpt_response(
        _xy_cpt_response(validated["source_sha256"])
    )
    return validated, build_effective_artifact(validated, accepted)


def test_asymmetric_two_parent_posteriors() -> None:
    validated = validate_xmlbif(_XY_XMLBIF)
    accepted = validate_cpt_response(
        _xy_cpt_response(validated["source_sha256"])
    )
    artifact = build_effective_artifact(validated, accepted)
    # Direct asymmetric conditionals: transposing X/Y would swap these.
    assert infer(artifact, "C", "yes", {"X": "no", "Y": "yes"}) == pytest.approx(
        0.20, abs=POSTERIOR_TOL
    )
    assert infer(artifact, "C", "yes", {"X": "yes", "Y": "no"}) == pytest.approx(
        0.60, abs=POSTERIOR_TOL
    )
    # Marginal and single-parent conditional from the hand arithmetic above.
    assert infer(artifact, "C", "yes", {}) == pytest.approx(
        0.333, abs=POSTERIOR_TOL
    )
    assert infer(artifact, "C", "yes", {"X": "yes"}) == pytest.approx(
        0.69, abs=POSTERIOR_TOL
    )
    assert infer(artifact, "X", "yes", {"C": "yes"}) == pytest.approx(
        92 / 111, abs=POSTERIOR_TOL
    )


def test_effective_xml_preserves_registered() -> None:
    import copy as _copy
    import hashlib as _hashlib

    from lxml import etree as _etree  # type: ignore[import-untyped]

    validated = validate_xmlbif(_XY_XMLBIF)
    source_before = bytes(validated["source_bytes"])
    sha_before = validated["source_sha256"]
    accepted = validate_cpt_response(_xy_cpt_response(sha_before))
    artifact = build_effective_artifact(validated, accepted)
    # Registered source bytes/hash unchanged by the build.
    assert validated["source_bytes"] == source_before
    assert validated["source_sha256"] == sha_before
    # Effective XML is a distinct run-local artifact with a frozen hash.
    effective_xml = artifact["effective_xml"]
    assert isinstance(effective_xml, (bytes, bytearray))
    assert bytes(effective_xml) != source_before
    assert artifact["effective_hash"] == _hashlib.sha256(
        bytes(effective_xml)
    ).hexdigest()
    # Effective XML parses and keeps nodes/order/edges of the registered XML.
    eff = validate_xmlbif(bytes(effective_xml))
    assert eff["xsd_report"]["valid"] is True
    assert eff["nodes"] == ["X", "Y", "C"]
    assert eff["states"] == {
        "X": ["no", "yes"],
        "Y": ["no", "yes"],
        "C": ["no", "yes"],
    }
    assert eff["edges"] == [("X", "C"), ("Y", "C")]
    # Every accepted table is present: TABLE cell counts match and values
    # equal the accepted probabilities within 1e-12.
    root = _etree.fromstring(bytes(effective_xml))
    scope = root.find("NETWORK")
    scope = scope if scope is not None else root
    seen: set[str] = set()
    for definition in scope.findall("DEFINITION"):
        for_el = definition.find("FOR")
        assert for_el is not None and for_el.text is not None
        child = str(for_el.text)
        table_el = definition.find("TABLE")
        assert table_el is not None and table_el.text is not None
        cells = [float(v) for v in str(table_el.text).split()]
        expected = _XY_EXPECTED_FLAT[child]
        assert len(cells) == len(expected)
        for got, want in zip(cells, expected):
            assert abs(got - want) <= 1e-12
        seen.add(child)
    assert seen == {"X", "Y", "C"}
    # Accepted percentages are persisted verbatim alongside probabilities.
    assert artifact["percentages"]["C"] == _copy.deepcopy(
        [row["percentages"] for row in accepted["tables"][2]["rows"]]
    )
    # Metadata/properties and document order survive the conversion.
    assert b"synthetic=asymmetric-xy-fixture" in bytes(effective_xml)
    assert b"synthetic=child-table-note" in bytes(effective_xml)
    assert eff["network_properties"] == validated["network_properties"]


def test_row_order_transpose_rejected_or_detected() -> None:
    import copy as _copy

    validated = validate_xmlbif(_XY_XMLBIF)
    accepted = validate_cpt_response(
        _xy_cpt_response(validated["source_sha256"])
    )
    swapped = _copy.deepcopy(accepted)
    for t in swapped["tables"]:
        if t["node_id"] == "C":
            # Exchange the (no,yes) and (yes,no) rows: canonical order is
            # enforced, so the build must reject this transposition.
            t["rows"][1], t["rows"][2] = t["rows"][2], t["rows"][1]
    with pytest.raises(ValueError):
        build_effective_artifact(validated, swapped)


# S23 slice 4 RED: replay / impossible-evidence / resource-exhaustion.
# Existing 25 tests above untouched.
#
# Proposed minimal new public surface (documented here for this slice):
#   replay(artifact, target, state, evidence) -> float
#     Deterministic exact replay reading ONLY the frozen stored artifact
#     (effective_xml + probabilities + stored evidence/query shapes).
#     Takes no provider argument and performs no network/socket I/O.
#     Must match infer within absolute 1e-9 on the same artifact/query.
#   infer(..., engine_config: dict | None = None)
#     Optional limits e.g. {"max_nodes": ..., "max_cpt_cells": ...,
#     "timeout_s": ...}. Exceeding a limit raises ValueError whose message
#     contains "resource", "exhaust", or "limit"; never approximates.
#   infer_in_subprocess(...) bounded-isolation entry point running inference
#     in a child process under the same engine_config limits.
#   Impossible evidence raises ValueError containing "impossible"
#     (chosen over an error-dict return; never returns 0.0/NaN silently).
#   Resource exhaustion raises ValueError containing "resource"/"exhaust"/
#     "limit" (never approximates or softens probabilities).
#
# Synthetic fixtures only (never BNs/ as oracle, never clinical content).
# Slice 4 uses the two-node A->B shape from slice 1 plus a
# deterministic-zero variant: A root [100, 0] (A=no certain) with
# B|A=no [100, 0] and B|A=yes [0, 100], so P(B=yes) = 0 and any query
# conditioned on B=yes is impossible. Hand arithmetic: P(A=no,B=yes) =
# 1.0*0.0 = 0; P(A=yes,B=yes) = 0.0*1.0 = 0; hence P(B=yes) = 0.

REPLAY_TOL = 1e-9


def _zero_cpt_response(network_hash: str) -> dict[str, Any]:
    return {
        "question_key": "synthetic_zero",
        "network_version": "v1",
        "network_hash": network_hash,
        "tables": [
            {
                "node_id": "A",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [100, 0]}],
            },
            {
                "node_id": "B",
                "parent_ids": ["A"],
                "states": ["no", "yes"],
                "rows": [
                    {"parent_states": ["no"], "percentages": [100, 0]},
                    {"parent_states": ["yes"], "percentages": [0, 100]},
                ],
            },
        ],
    }


def _zero_artifact() -> dict[str, Any]:
    validated = validate_xmlbif(_XMLBIF)
    accepted = validate_cpt_response(
        _zero_cpt_response(validated["source_sha256"])
    )
    return build_effective_artifact(validated, accepted)


def test_replay_matches_within_tolerance_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import copy as _copy
    import inspect as _inspect
    import socket as _socket

    # No replay function exists yet: expect ImportError here (RED).
    from x_insight.models.inference import replay  # type: ignore[import-not-found]

    # Replay takes only the stored artifact plus query; no provider arg.
    assert "provider" not in _inspect.signature(replay).parameters
    # Forbid network use during replay: any socket attempt fails the test.
    def _forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("replay must not use the network/provider")

    monkeypatch.setattr(_socket, "create_connection", _forbidden)
    monkeypatch.setattr(_socket, "getaddrinfo", _forbidden)
    validated, accepted = _validated_and_accepted()
    artifact = build_effective_artifact(validated, accepted)
    # Frozen stored artifact: deep copy emulating persisted effective_xml
    # + probabilities + stored evidence/query (no live provider state).
    frozen = _copy.deepcopy(artifact)
    assert bytes(frozen["effective_xml"]) == bytes(artifact["effective_xml"])
    for target, state, evidence in [
        ("B", "yes", {}),
        ("B", "yes", {"A": "yes"}),
        ("A", "yes", {"B": "yes"}),
    ]:
        expected = infer(artifact, target, state, dict(evidence))
        got = replay(frozen, target, state, dict(evidence))
        assert got == pytest.approx(expected, abs=REPLAY_TOL)


def test_impossible_evidence_returns_explicit_error() -> None:
    artifact = _zero_artifact()
    # P(B=yes) = 0, so conditioning on B=yes is impossible. Must raise
    # ValueError containing "impossible" (never return 0.0/NaN).
    with pytest.raises(ValueError, match="impossible"):
        infer(artifact, "A", "no", {"B": "yes"})


def test_resource_exhaustion_returns_explicit_error() -> None:
    # Bounded-isolation entry point does not exist yet: ImportError (RED).
    from x_insight.models.inference import (  # type: ignore[import-not-found]
        infer_in_subprocess,
    )

    assert callable(infer_in_subprocess)
    validated, accepted = _validated_and_accepted()
    artifact = build_effective_artifact(validated, accepted)
    # Tiny limits on the 2-node fixture must fail explicitly, never
    # approximate. No engine_config param exists yet: TypeError (RED).
    with pytest.raises(ValueError, match="resource|exhaust|limit"):
        infer(artifact, "B", "yes", {}, engine_config={"max_nodes": 1})  # type: ignore[call-arg]


def test_no_approximation_on_failure() -> None:
    # Neither impossible evidence nor resource exhaustion may silently
    # return a posterior float (0.0/NaN); both must raise explicit errors.
    artifact = _zero_artifact()
    with pytest.raises(ValueError, match="impossible"):
        infer(artifact, "A", "no", {"B": "yes"})
    validated, accepted = _validated_and_accepted()
    artifact2 = build_effective_artifact(validated, accepted)
    with pytest.raises(ValueError, match="resource|exhaust|limit"):
        infer(artifact2, "B", "yes", {}, engine_config={"max_cpt_cells": 1})  # type: ignore[call-arg]
