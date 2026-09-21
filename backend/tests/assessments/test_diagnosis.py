"""S09 slice 1: diagnosis threshold tracer at seam T2 (pure, no I/O, no DB).

SYNTHETIC FIXTURE WARNING: all inputs below are conspicuously synthetic
worked examples derived by hand from
docs/medical-docs/schizophrenia-criteria.md (criteria A-F). They are not
clinical data and never become released defaults. Expected values are
independent literals, never produced by the implementation under test.
"""

from x_insight.assessments.diagnosis import evaluate_diagnosis


def _synthetic_qualifying_answers() -> dict:
    """SYNTHETIC: hand-worked qualifying case (A-F satisfied on paper)."""
    return {
        # Criterion A: delusions + hallucinations together in one 1-month
        # active-phase interval; >=1 core symptom (both are core).
        "active_phase_domains": ["delusions", "hallucinations"],
        "shared_one_month_active_phase": True,
        "active_phase_abbreviated_by_intervention": False,
        # Criterion B: work decline from prior level.
        "functional_decline": True,
        # Criterion C: 7 months continuous illness including the active phase.
        "continuous_months": 7,
        "active_phase_included": True,
        # Criterion D: no concurrent major mood episode with psychosis.
        "concurrent_mood_episode_with_psychosis": False,
        "mood_episodes_minority_of_course": True,
        # Criterion E: no substance/medication/medical cause.
        "substance_or_medical_cause": False,
        # Criterion F: no autism/childhood-communication history (vacuous).
        "autism_or_childhood_communication_history": False,
    }


def _synthetic_symptom_count_only_answers() -> dict:
    """SYNTHETIC: same 2 domains but in different intervals (no shared phase)."""
    return {
        # Same raw count as the qualifying case, but explicitly NOT in a
        # shared 1-month active-phase interval, so Criterion A must fail.
        "active_phase_domains": ["delusions", "hallucinations"],
        "shared_one_month_active_phase": False,
        "active_phase_abbreviated_by_intervention": False,
        # All other criteria unmet on paper (F vacuous: no autism history).
        "functional_decline": False,
        "continuous_months": 2,
        "active_phase_included": False,
        "concurrent_mood_episode_with_psychosis": True,
        "mood_episodes_minority_of_course": False,
        "substance_or_medical_cause": True,
        "autism_or_childhood_communication_history": False,
    }


def test_qualifying_case_satisfies_all_criteria() -> None:
    result = evaluate_diagnosis(_synthetic_qualifying_answers())
    assert result["status"] == "complete"
    assert result["threshold_met"] is True
    # Independent literal worked from criteria A-F: every criterion met.
    assert result["criteria"] == {
        "A": True,
        "B": True,
        "C": True,
        "D": True,
        "E": True,
        "F": True,
    }


def test_symptom_count_alone_does_not_satisfy() -> None:
    result = evaluate_diagnosis(_synthetic_symptom_count_only_answers())
    assert result["status"] == "complete"
    assert result["threshold_met"] is False
    # Symptom count alone cannot satisfy: no shared 1-month active phase.
    assert result["criteria"]["A"] is False
    # All other content criteria unmet on paper (F vacuous, left unpinned).
    assert result["criteria"]["B"] is False
    assert result["criteria"]["C"] is False
    assert result["criteria"]["D"] is False
    assert result["criteria"]["E"] is False


def test_missing_required_field_returns_partial_no_completed_result() -> None:
    """S09 slice 2 (FR-11/FR-16, T2): incomplete work is partial, never complete."""
    answers = _synthetic_qualifying_answers()
    del answers["continuous_months"]
    result = evaluate_diagnosis(answers)
    assert result["status"] == "partial"
    assert result["status"] != "complete"
    assert result["threshold_met"] is False
    assert "continuous_months" in result["missing_item_ids"]
    # Independent literal: no criterion may read as met on partial input.
    assert result["criteria"] == {
        "A": False,
        "B": False,
        "C": False,
        "D": False,
        "E": False,
        "F": False,
    }


def test_empty_answers_never_complete() -> None:
    """S09 slice 2: empty input is partial (all items missing), not complete."""
    result = evaluate_diagnosis({})
    assert result["status"] == "partial"
    assert result["status"] != "complete"
    assert result["threshold_met"] is False
    assert len(result["missing_item_ids"]) == 10
    assert not all(result["criteria"].values())
