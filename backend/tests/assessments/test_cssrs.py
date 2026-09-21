"""S11 slice 1 (RED): C-SSRS empty/skip/all-negative ideation severity (T2).

SYNTHETIC FIXTURE WARNING: all inputs below are conspicuously synthetic
empty/skip-only/explicit-negative checks, never clinical data. Level ids
L1-L5 mirror the approved severity ordering from docs/medical-docs/CSSRS.md
(1 wish to be dead .. 5 plan+intent). Expected severities are independent
hand-worked literals from CSSRS.md scoring (severity = highest endorsed
0-5; all explicit negatives -> 0). Not produced by the implementation under
test; never become released defaults. This file does NOT read
content/assessments/cssrs.json as an oracle. Slice 1 only: empty, skip,
mixed-skip, all-explicit-negative. Intensity/behavior/lethality belong to
slices 2-3.

Proposed synthetic v1 contract under test (pure typed evaluator, no I/O):
- from x_insight.assessments.cssrs import evaluate_cssrs.
- Answer shape: {"L1": {"endorsed": bool, "period": "current"|"historical"
  when endorsed True}, ... L1-L5}. For explicit negatives,
  {"endorsed": False} with no period required.
- Skip shape {not_assessed: True} exclusive; mixing with any L-level
  raises ValueError. No autofill. No composite risk score.
- Return shape (minimal): {"status": "unanswered"|"not_assessed"|"complete",
  "severity": int|None, "ideation_present": bool|None, ...}. Empty ->
  unanswered/severity None (no assessed result); skip -> not_assessed/
  severity None; all L1-L5 explicitly {endorsed: False} -> complete/
  severity 0 / ideation_present False (reviewed no-ideation, no intensity
  required).

Current backend has no x_insight/assessments/cssrs.py, so collection of
this file fails with ModuleNotFoundError (expected red).
"""

import pytest

from x_insight.assessments.cssrs import evaluate_cssrs

LEVEL_IDS = ["L1", "L2", "L3", "L4", "L5"]


def test_empty_unanswered() -> None:
    result = evaluate_cssrs({})
    assert result["status"] == "unanswered"
    # No assessed result on a fresh form: severity must be None, never 0.
    assert result["severity"] is None


def test_skip_not_assessed() -> None:
    result = evaluate_cssrs({"not_assessed": True})
    assert result["status"] == "not_assessed"
    assert result["severity"] is None


def test_mixed_skip_rejected() -> None:
    # SYNTHETIC: skip flag mixed with one explicit answer, not clinical data.
    with pytest.raises(ValueError):
        evaluate_cssrs({"not_assessed": True, "L3": {"endorsed": False}})


def test_all_explicit_negative() -> None:
    # SYNTHETIC: all L1-L5 explicitly negative, hand-worked -> severity 0.
    answers = {level: {"endorsed": False} for level in LEVEL_IDS}
    assert len(answers) == 5
    result = evaluate_cssrs(answers)
    assert result["status"] == "complete"
    assert result["severity"] == 0
    # Reviewed no-ideation result; no intensity required for this case.
    assert result["ideation_present"] is False


# Slice 3 (RED): period retention, missing guidance, approved alerts (T2).
# SYNTHETIC FIXTURE WARNING: inputs below are conspicuously synthetic
# hand-worked checks, never clinical data. Periods "historical"/"current"
# mirror the v1 mapping approved 2026-09-21 (per-endorsed-level period
# verbatim; current = recent/current window, historical = lifetime/history).
# Expected severities/flags are independent literals from
# docs/medical-docs/CSSRS.md Interpretation table (no positive -> no-ideation;
# L1-L3 or historical behavior -> clinical review; recent L4/L5 or recent
# suicidal behavior -> high-risk; no calculated immediate emergency, no
# composite). Never produced by the implementation under test; never become
# released defaults.


def test_periods_retained_not_guessed() -> None:
    # SYNTHETIC: L3 historical + L4 current, L1/L2/L5 missing.
    answers: dict = {
        "L3": {"endorsed": True, "period": "historical"},
        "L4": {"endorsed": True, "period": "current"},
    }
    result = evaluate_cssrs(answers)
    assert result["status"] == "partial"
    assert result["severity"] == 4
    assert set(result["missing_item_ids"]) == {"L1", "L2", "L5"}
    # Periods retained verbatim, never guessed; missing never auto-filled.
    assert result["details"]["L3"] == {"endorsed": True, "period": "historical"}
    assert result["details"]["L4"] == {"endorsed": True, "period": "current"}
    assert "L1" not in result["details"]
    assert "L2" not in result["details"]
    assert "L5" not in result["details"]


def test_missing_branch_guidance() -> None:
    # SYNTHETIC: L1 explicit negative only, rest missing.
    answers: dict = {"L1": {"endorsed": False}}
    result = evaluate_cssrs(answers)
    assert result["status"] == "partial"
    # Severity from available endorsements only (0 here, never None-guessed).
    assert result["severity"] == 0
    assert result["missing_item_ids"] == ["L2", "L3", "L4", "L5"]
    # Guidance, not guessed negatives: details holds only answered L1.
    assert result["details"]["L1"] == {"endorsed": False}
    assert "L2" not in result["details"]


def test_approved_alerts_only() -> None:
    # SYNTHETIC: all flag cases use hand-worked literals from CSSRS.md table.
    all_negative = {level: {"endorsed": False} for level in LEVEL_IDS}
    result_none = evaluate_cssrs(dict(all_negative))
    assert result_none["flags"] == {
        "no_ideation": True,
        "clinical_review": False,
        "high_risk": False,
    }
    # (b) L2 current -> clinical review, not high-risk.
    answers_review = {level: {"endorsed": False} for level in LEVEL_IDS}
    answers_review["L2"] = {"endorsed": True, "period": "current"}
    result_review = evaluate_cssrs(answers_review)
    assert result_review["flags"]["no_ideation"] is False
    assert result_review["flags"]["clinical_review"] is True
    assert result_review["flags"]["high_risk"] is False
    # (c) L4 current -> high-risk.
    answers_high = {level: {"endorsed": False} for level in LEVEL_IDS}
    answers_high["L4"] = {"endorsed": True, "period": "current"}
    result_high = evaluate_cssrs(answers_high)
    assert result_high["flags"]["high_risk"] is True
    assert result_high["flags"]["no_ideation"] is False
    # (c) recent actual attempt -> high-risk.
    behavior_recent = {
        "actual_attempt": {"present": True, "recency": "recent"},
        "interrupted_attempt": {"present": False},
        "aborted_attempt": {"present": False},
        "preparatory_acts": {"present": False},
        "nonsuicidal_self_injury": {"present": False},
    }
    answers_behavior = {level: {"endorsed": False} for level in LEVEL_IDS}
    answers_behavior["behavior"] = behavior_recent
    result_behavior = evaluate_cssrs(answers_behavior)
    assert result_behavior["flags"]["high_risk"] is True
    assert result_behavior["flags"]["no_ideation"] is False
    # NSSI recent never triggers high-risk (separate category).
    behavior_nssi = {
        "actual_attempt": {"present": False},
        "interrupted_attempt": {"present": False},
        "aborted_attempt": {"present": False},
        "preparatory_acts": {"present": False},
        "nonsuicidal_self_injury": {"present": True, "recency": "recent"},
    }
    answers_nssi = {level: {"endorsed": False} for level in LEVEL_IDS}
    answers_nssi["behavior"] = behavior_nssi
    result_nssi = evaluate_cssrs(answers_nssi)
    assert result_nssi["flags"]["high_risk"] is False
    assert result_nssi["flags"]["no_ideation"] is False
    # (d) no composite score and no calculated immediate emergency.
    for checked in (
        result_none,
        result_review,
        result_high,
        result_behavior,
        result_nssi,
    ):
        for composite_key in ("risk_score", "composite", "total"):
            assert composite_key not in checked
        assert checked.get("scores") is None
        assert "immediate_emergency" not in checked
        assert "immediate_emergency" not in checked.get("flags", {})


def test_level3_endorsed_gives_severity3_without_autofill() -> None:
    # SYNTHETIC slice2: L3 True/current, L4/L5 explicit negatives, L1/L2 absent.
    answers: dict = {
        "L3": {"endorsed": True, "period": "current"},
        "L4": {"endorsed": False},
        "L5": {"endorsed": False},
    }
    result = evaluate_cssrs(answers)
    # Partial form still yields ordinal severity 3 from available answers.
    assert result["status"] == "partial"
    assert result["severity"] == 3
    assert result["ideation_present"] is True
    assert set(result["missing_item_ids"]) == {"L1", "L2"}
    # No auto-fill of lower levels in stored answers.
    assert "L1" not in answers or answers.get("L1") is None
    assert "L2" not in answers or answers.get("L2") is None
    # No intensity/behavior/lethality and no composite in this result.
    assert result.get("intensity") is None
    assert result.get("behavior") is None
    assert result.get("lethality") is None
    for composite_key in ("risk_score", "composite", "total"):
        assert composite_key not in result


def test_intensity_behavior_lethality_separate_no_composite() -> None:
    # SYNTHETIC: full ideation (L3 True/current, rest False) + separate blocks.
    intensity = {
        "frequency": 3,
        "duration": 2,
        "controllability": 1,
        "deterrents": 0,
        "reasons": 4,
    }
    behavior = {
        "actual_attempt": {"present": False},
        "interrupted_attempt": {"present": False},
        "aborted_attempt": {"present": False},
        "preparatory_acts": {"present": False},
        "nonsuicidal_self_injury": {"present": False},
    }
    lethality = {"actual": 0, "potential": 1}
    answers: dict = {
        "L1": {"endorsed": False},
        "L2": {"endorsed": False},
        "L3": {"endorsed": True, "period": "current"},
        "L4": {"endorsed": False},
        "L5": {"endorsed": False},
        "intensity": dict(intensity),
        "behavior": {k: dict(v) for k, v in behavior.items()},
        "lethality": dict(lethality),
    }
    result = evaluate_cssrs(answers)
    # Severity stays the ordinal max (3), never a sum.
    assert result["status"] == "complete"
    assert result["severity"] == 3
    assert result["ideation_present"] is True
    # Blocks echoed separately, values preserved verbatim.
    assert result.get("intensity") == intensity
    assert result.get("behavior") == behavior
    assert result.get("lethality") == lethality
    # No composite risk score anywhere in the result.
    for composite_key in ("risk_score", "composite", "total"):
        assert composite_key not in result
    assert result.get("scores") is None
    hand_sum = 3 + 2 + 1 + 0 + 4
    assert hand_sum == 10
    assert result["severity"] != hand_sum
