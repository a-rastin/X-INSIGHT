"""S08 slice 1: pure assessment evaluator status/scoring (seam T2, no I/O, no DB).

Synthetic fixture only — conspicuously synthetic, never clinical.
"""

from copy import deepcopy

import pytest

from x_insight.assessments import evaluate, load_definition


def _synthetic_definition() -> dict:
    return {
        "schema_version": 1,
        "assessment_type": "synthetic_demo",
        "definition_version": "synthetic-v1",
        "items": [
            {"id": "q1", "kind": "int", "min": 1, "max": 7},
            {"id": "q2", "kind": "int", "min": 1, "max": 7},
        ],
        "required_item_ids": ["q1", "q2"],
        "result_rules": [{"id": "total", "op": "sum", "items": ["q1", "q2"]}],
    }


def test_empty_answers_is_unanswered() -> None:
    result = evaluate(_synthetic_definition(), {})
    assert result["status"] == "unanswered"
    assert result["missing_item_ids"] == ["q1", "q2"]
    assert result["scores"] is None
    assert result["definition_version"] == "synthetic-v1"


def test_single_answer_is_partial_with_scores_none() -> None:
    result = evaluate(_synthetic_definition(), {"q1": 3})
    assert result["status"] == "partial"
    assert result["missing_item_ids"] == ["q2"]
    # A missing answer never becomes zero: scores must be None, not {"total": 3}.
    assert result["scores"] is None


def test_full_answers_is_complete_with_hand_computed_total() -> None:
    result = evaluate(_synthetic_definition(), {"q1": 3, "q2": 4})
    assert result["status"] == "complete"
    assert result["missing_item_ids"] == []
    assert result["scores"] == {"total": 7}  # 3 + 4 = 7, worked by hand


def test_explicit_skip_is_not_assessed() -> None:
    result = evaluate(_synthetic_definition(), {"not_assessed": True})
    assert result["status"] == "not_assessed"
    assert result["scores"] is None


SYNTHETIC_DEFN = _synthetic_definition()


def test_undeclared_item_id_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate(SYNTHETIC_DEFN, {"q1": 3, "bogus_item": 1})


def test_out_of_range_answer_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate(SYNTHETIC_DEFN, {"q1": 99, "q2": 4})


def test_wrong_type_string_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate(SYNTHETIC_DEFN, {"q1": "high", "q2": 4})


def test_bool_answer_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate(SYNTHETIC_DEFN, {"q1": True, "q2": 4})


def test_mixed_skip_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate(SYNTHETIC_DEFN, {"not_assessed": True, "q1": 3})


def test_load_definition_rejects_unknown_operator() -> None:
    bad = deepcopy(SYNTHETIC_DEFN)
    bad["result_rules"][0]["op"] = "median"
    with pytest.raises(ValueError):
        load_definition(bad)


def test_load_definition_rejects_executable_expressions() -> None:
    top_level = deepcopy(SYNTHETIC_DEFN)
    top_level["expression"] = "q1 + q2"
    with pytest.raises(ValueError):
        load_definition(top_level)
    nested = deepcopy(SYNTHETIC_DEFN)
    nested["result_rules"][0]["code"] = "eval(q1 + q2)"
    with pytest.raises(ValueError):
        load_definition(nested)


def test_load_definition_round_trip_preserves_scoring() -> None:
    loaded = load_definition(SYNTHETIC_DEFN)
    result = evaluate(loaded, {"q1": 3, "q2": 4})
    assert result["status"] == "complete"
    assert result["scores"] == {"total": 7}


def test_max_operator_scores_peak() -> None:
    definition = deepcopy(SYNTHETIC_DEFN)
    definition["result_rules"] = [{"id": "peak", "op": "max", "items": ["q1", "q2"]}]
    result = evaluate(definition, {"q1": 3, "q2": 5})
    assert result["status"] == "complete"
    assert result["scores"] == {"peak": 5}
