"""S09 slice 1 typed DSM-5-TR schizophrenia A-F evaluator. No I/O, no DB."""

from __future__ import annotations

from typing import Any

ALLOWED_DOMAINS: frozenset[str] = frozenset(
    {
        "delusions",
        "hallucinations",
        "disorganized_speech",
        "disorganized_behavior",
        "negative_symptoms",
    }
)
CORE_DOMAINS: frozenset[str] = frozenset(
    {"delusions", "hallucinations", "disorganized_speech"}
)

REQUIRED_ITEM_IDS: tuple[str, ...] = (
    "active_phase_domains",
    "shared_one_month_active_phase",
    "active_phase_abbreviated_by_intervention",
    "functional_decline",
    "continuous_months",
    "active_phase_included",
    "concurrent_mood_episode_with_psychosis",
    "mood_episodes_minority_of_course",
    "substance_or_medical_cause",
    "autism_or_childhood_communication_history",
)
BOOL_KEYS: frozenset[str] = frozenset(
    {
        "shared_one_month_active_phase",
        "active_phase_abbreviated_by_intervention",
        "functional_decline",
        "active_phase_included",
        "concurrent_mood_episode_with_psychosis",
        "mood_episodes_minority_of_course",
        "substance_or_medical_cause",
        "autism_or_childhood_communication_history",
    }
)


def _canonical_domain(value: Any) -> str:
    if type(value) is not str or value not in ALLOWED_DOMAINS:
        raise ValueError(f"undeclared domain: {value!r}")
    return value


def _validate_present(answers: dict[str, Any]) -> None:
    for key, value in answers.items():
        if value is None:
            continue
        if key == "active_phase_domains":
            if type(value) is not list:
                raise ValueError("active_phase_domains must be a list")
            for entry in value:
                _canonical_domain(entry)
        elif key == "continuous_months":
            if type(value) is not int or isinstance(value, bool):
                raise ValueError("continuous_months must be an int")
            if value < 0:
                raise ValueError("continuous_months must be >= 0")
        elif key in BOOL_KEYS:
            if type(value) is not bool:
                raise ValueError(f"{key} must be a bool")
        else:  # pragma: no cover - undeclared keys rejected earlier
            raise ValueError(f"undeclared item id: {key}")


def _criterion_a(domains: list[str], shared: bool, abbreviated: bool) -> bool:
    distinct = set(domains)
    count_ok = len(distinct) >= 2 and (shared or abbreviated)
    return bool(count_ok and bool(distinct & set(CORE_DOMAINS)))


def evaluate_diagnosis(answers: dict[str, Any]) -> dict[str, Any]:
    """Evaluate criteria A-F. Full inputs -> complete; missing -> partial."""
    if type(answers) is not dict:
        raise ValueError("answers must be a dict")
    for key in answers:
        if key not in REQUIRED_ITEM_IDS:
            raise ValueError(f"undeclared item id: {key}")
    _validate_present(answers)
    missing = [k for k in REQUIRED_ITEM_IDS if k not in answers or answers[k] is None]
    if missing:
        empty = {"A": False, "B": False, "C": False, "D": False, "E": False, "F": False}
        return {
            "status": "partial",
            "threshold_met": False,
            "missing_item_ids": missing,
            "criteria": empty,
        }
    domains = [_canonical_domain(d) for d in answers["active_phase_domains"]]
    shared = answers["shared_one_month_active_phase"]
    abbreviated = answers["active_phase_abbreviated_by_intervention"]
    crit_a = _criterion_a(domains, shared, abbreviated)
    crit_b = bool(answers["functional_decline"])
    crit_c = bool(
        answers["continuous_months"] >= 6 and answers["active_phase_included"]
    )
    crit_d = bool(
        not answers["concurrent_mood_episode_with_psychosis"]
        or answers["mood_episodes_minority_of_course"]
    )
    crit_e = bool(not answers["substance_or_medical_cause"])
    distinct = set(domains)
    crit_f = bool(
        not answers["autism_or_childhood_communication_history"]
        or bool(distinct & {"delusions", "hallucinations"})
    )
    criteria = {
        "A": crit_a,
        "B": crit_b,
        "C": crit_c,
        "D": crit_d,
        "E": crit_e,
        "F": crit_f,
    }
    return {
        "status": "complete",
        "threshold_met": bool(all(criteria.values())),
        "missing_item_ids": [],
        "criteria": criteria,
    }
