"""S10 slice 1: fresh PANSS form unanswered/skip (seam T2, no I/O, no DB).

SYNTHETIC FIXTURE WARNING: all inputs below are conspicuously synthetic
empty/skip-only answers. The 30 item ids (P1-P7, N1-N7, G1-G16) mirror the
approved arithmetic shape from docs/medical-docs/PANSS.md (7 positive +
7 negative + 16 general, each 1-7) as independent literals worked by hand.
They are not clinical data, were never produced by the implementation under
test, and never become released defaults. This file does NOT read
content/assessments/panss.json as an oracle. Slice 1 only: empty, skip,
mixed-skip. All-1/all-7/missing/invalid cases belong to slices 2-3.
"""

import pytest

from x_insight.assessments.panss import evaluate_panss

# Independent literals mirroring the approved arithmetic grouping:
# positive P1-P7, negative N1-N7, general G1-G16 (7 + 7 + 16 = 30).
POSITIVE_IDS = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]
NEGATIVE_IDS = ["N1", "N2", "N3", "N4", "N5", "N6", "N7"]
GENERAL_IDS = [
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "G6",
    "G7",
    "G8",
    "G9",
    "G10",
    "G11",
    "G12",
    "G13",
    "G14",
    "G15",
    "G16",
]
ALL_30_IDS = POSITIVE_IDS + NEGATIVE_IDS + GENERAL_IDS


def test_empty_answers_is_unanswered_with_null_scores() -> None:
    result = evaluate_panss({})
    assert result["status"] == "unanswered"
    assert result["missing_item_ids"] == ALL_30_IDS
    assert len(result["missing_item_ids"]) == 30
    # Fresh form has no default 1 and no hidden zero: scores must be None.
    assert result["scores"] is None


def test_explicit_skip_is_not_assessed_with_null_scores() -> None:
    result = evaluate_panss({"not_assessed": True})
    assert result["status"] == "not_assessed"
    assert result["scores"] is None


def test_mixed_skip_with_answer_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_panss({"not_assessed": True, "P1": 1})


# Slice 2: fully answered boundary sums (seam T2, no I/O, no DB).
# SYNTHETIC FIXTURE WARNING: uniform all-1 / all-7 inputs below are
# conspicuously synthetic arithmetic checks, not clinical data. Expected
# sums are independent hand-worked literals from docs/medical-docs/PANSS.md
# scoring section (Positive P1-P7: 7x1=7 / 7x7=49; Negative N1-N7: 7/49;
# General G1-G16: 16x1=16 / 16x7=112; Total 30/210). Not produced by the
# implementation under test; never become released defaults.


def test_all_1_yields_7_7_16_30() -> None:
    answers = {item_id: 1 for item_id in ALL_30_IDS}
    result = evaluate_panss(answers)
    assert result["status"] == "complete"
    assert result["missing_item_ids"] == []
    assert result["scores"] == {
        "positive": 7,
        "negative": 7,
        "general": 16,
        "total": 30,
    }


def test_all_7_yields_49_49_112_210() -> None:
    answers = {item_id: 7 for item_id in ALL_30_IDS}
    result = evaluate_panss(answers)
    assert result["status"] == "complete"
    assert result["missing_item_ids"] == []
    assert result["scores"] == {
        "positive": 49,
        "negative": 49,
        "general": 112,
        "total": 210,
    }


# Slice 3: completeness suppression + server-side rejection shape (seam T2).
# SYNTHETIC FIXTURE WARNING: inputs below are conspicuously synthetic
# arithmetic checks (uniform 1s with one omission / one bad value), not
# clinical data. Expected values are independent hand-worked literals:
# 29 answered -> partial, missing == ["G16"], scores None (never zero).
# Out-of-range (0/8 outside 1-7) and non-integer (float/str/bool) inputs
# raise ValueError. None means missing (partial), not invalid.


def test_one_missing_suppresses_total() -> None:
    answers = {item_id: 1 for item_id in ALL_30_IDS if item_id != "G16"}
    assert len(answers) == 29
    result = evaluate_panss(answers)
    assert result["status"] == "partial"
    assert result["missing_item_ids"] == ["G16"]
    assert result["scores"] is None
    assert result["scores"] != 0


def test_out_of_range_rejected() -> None:
    low = {item_id: 1 for item_id in ALL_30_IDS}
    low["P1"] = 0
    with pytest.raises(ValueError):
        evaluate_panss(low)
    high = {item_id: 1 for item_id in ALL_30_IDS}
    high["P1"] = 8
    with pytest.raises(ValueError):
        evaluate_panss(high)


def test_noninteger_rejected_and_none_is_missing() -> None:
    for bad in (3.5, "3", True):
        answers = {item_id: 1 for item_id in ALL_30_IDS}
        answers["P1"] = bad  # type: ignore[dict-item]
        with pytest.raises(ValueError):
            evaluate_panss(answers)
    none_missing = {item_id: 1 for item_id in ALL_30_IDS}
    none_missing["P1"] = None  # type: ignore[dict-item]
    result = evaluate_panss(none_missing)
    assert result["status"] == "partial"
    assert result["missing_item_ids"] == ["P1"]
    assert result["scores"] is None
