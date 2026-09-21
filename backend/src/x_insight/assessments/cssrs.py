"""S11 slice 3 C-SSRS evaluator: ideation + flags/details, separate blocks."""

from __future__ import annotations

from typing import Any

IDEATION_IDS: list[str] = ["L1", "L2", "L3", "L4", "L5"]
ALLOWED_PERIODS = {"current", "historical"}
ALLOWED_RECENCY = {"recent", "historical"}
SUICIDAL_BEHAVIOR_IDS: list[str] = [
    "actual_attempt",
    "interrupted_attempt",
    "aborted_attempt",
    "preparatory_acts",
]
INTENSITY_RANGES: dict[str, tuple[int, int]] = {
    "frequency": (1, 5),
    "duration": (1, 5),
    "controllability": (0, 5),
    "deterrents": (0, 5),
    "reasons": (0, 5),
}
BEHAVIOR_IDS: list[str] = [
    "actual_attempt",
    "interrupted_attempt",
    "aborted_attempt",
    "preparatory_acts",
    "nonsuicidal_self_injury",
]

_DEFINITION_VERSION = "cssrs-v1"


def _validate_intensity(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise ValueError("intensity must be a dict")
    if set(value.keys()) != set(INTENSITY_RANGES):
        raise ValueError(
            "intensity needs frequency/duration/controllability/deterrents/reasons"
        )
    out: dict[str, int] = {}
    for dim, (low, high) in INTENSITY_RANGES.items():
        item = value[dim]
        if type(item) is not int:
            raise ValueError(f"intensity {dim} must be an int")
        if item < low or item > high:
            raise ValueError(f"intensity {dim} out of range")
        out[dim] = item
    return out


def _validate_behavior(value: Any) -> dict[str, dict[str, Any]] | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise ValueError("behavior must be a dict")
    if set(value.keys()) != set(BEHAVIOR_IDS):
        raise ValueError("behavior needs all 5 categories")
    out: dict[str, dict[str, Any]] = {}
    for category in BEHAVIOR_IDS:
        entry = value[category]
        if type(entry) is not dict:
            raise ValueError(f"behavior {category} must be a dict")
        if set(entry.keys()) not in ({"present"}, {"present", "recency"}):
            raise ValueError(f"behavior {category} needs present")
        present = entry["present"]
        if type(present) is not bool:
            raise ValueError(f"behavior {category} present must be a bool")
        if "recency" in entry:
            if entry["recency"] not in ALLOWED_RECENCY:
                raise ValueError(f"behavior {category} has invalid recency")
        elif present is True:
            raise ValueError(f"behavior {category} needs recency when present")
        kept: dict[str, Any] = {"present": present}
        if "recency" in entry:
            kept["recency"] = entry["recency"]
        out[category] = kept
    return out


def _build_details(answers: dict[str, Any]) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    for level_id in IDEATION_IDS:
        entry = answers.get(level_id)
        if not isinstance(entry, dict):
            continue
        kept: dict[str, Any] = {"endorsed": entry.get("endorsed")}
        if "period" in entry:
            kept["period"] = entry["period"]
        details[level_id] = kept
    return details


def _compute_flags(
    answered: dict[str, dict[str, Any]],
    behavior: dict[str, dict[str, Any]] | None,
) -> dict[str, bool]:
    endorsed_true = {
        level_id
        for level_id, entry in answered.items()
        if entry.get("endorsed") is True
    }
    any_l1_3 = any(level_id in endorsed_true for level_id in ("L1", "L2", "L3"))
    any_l4_5_current = any(
        level_id in endorsed_true and answered[level_id].get("period") == "current"
        for level_id in ("L4", "L5")
    )
    any_behavior_present = False
    any_historical_suicidal = False
    any_recent_suicidal = False
    if isinstance(behavior, dict):
        for category, entry in behavior.items():
            if entry.get("present") is True:
                any_behavior_present = True
                if category in SUICIDAL_BEHAVIOR_IDS:
                    if entry.get("recency") == "historical":
                        any_historical_suicidal = True
                    elif entry.get("recency") == "recent":
                        any_recent_suicidal = True
    no_ideation = not endorsed_true and not any_behavior_present
    return {
        "no_ideation": no_ideation,
        "clinical_review": bool(any_l1_3 or any_historical_suicidal),
        "high_risk": bool(any_l4_5_current or any_recent_suicidal),
    }


_NO_FLAGS: dict[str, bool] = {
    "no_ideation": False,
    "clinical_review": False,
    "high_risk": False,
}


def _validate_lethality(value: Any) -> dict[str, int | None] | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise ValueError("lethality must be a dict")
    for key in value:
        if key not in ("actual", "potential"):
            raise ValueError(f"undeclared lethality key: {key}")
    if "actual" not in value:
        raise ValueError("lethality needs actual")
    actual = value["actual"]
    if type(actual) is not int:
        raise ValueError("lethality actual must be an int")
    if actual < 0 or actual > 5:
        raise ValueError("lethality actual out of range")
    if actual == 0:
        if "potential" not in value:
            raise ValueError("lethality potential required when actual is 0")
        potential = value["potential"]
        if type(potential) is not int:
            raise ValueError("lethality potential must be an int")
        if potential < 0 or potential > 2:
            raise ValueError("lethality potential out of range")
        return {"actual": actual, "potential": potential}
    if "potential" in value and value["potential"] is not None:
        raise ValueError("lethality potential must be absent when actual > 0")
    return {"actual": actual, "potential": None}


def evaluate_cssrs(answers: dict[str, Any]) -> dict[str, Any]:
    """Evaluate C-SSRS answers; severity max L1-L5, approved flags only."""
    if type(answers) is not dict:
        raise ValueError("answers must be a dict")
    if set(answers.keys()) == {"not_assessed"}:
        if answers.get("not_assessed") is True:
            return {
                "status": "not_assessed",
                "severity": None,
                "ideation_present": None,
                "missing_item_ids": list(IDEATION_IDS),
                "scores": None,
                "findings": {},
                "flags": dict(_NO_FLAGS),
                "details": {},
                "intensity": None,
                "behavior": None,
                "lethality": None,
                "definition_version": _DEFINITION_VERSION,
            }
        raise ValueError("not_assessed must be True when present")
    if "not_assessed" in answers:
        raise ValueError("not_assessed cannot be mixed with answers")
    allowed = set(IDEATION_IDS) | {"intensity", "behavior", "lethality"}
    for key in answers:
        if key not in allowed:
            raise ValueError(f"undeclared item id: {key}")
    for level_id in IDEATION_IDS:
        if level_id not in answers:
            continue
        value = answers[level_id]
        if value is None:
            continue
        if type(value) is not dict:
            raise ValueError(f"item {level_id} must be a dict")
        for inner_key in value:
            if inner_key not in ("endorsed", "period"):
                raise ValueError(f"undeclared key for {level_id}: {inner_key}")
        if "endorsed" not in value:
            raise ValueError(f"item {level_id} needs endorsed")
        endorsed = value["endorsed"]
        if type(endorsed) is not bool:
            raise ValueError(f"item {level_id} endorsed must be a bool")
        if "period" in value:
            if value["period"] not in ALLOWED_PERIODS:
                raise ValueError(f"item {level_id} has invalid period")
        elif endorsed is True:
            raise ValueError(f"item {level_id} needs period when endorsed")
    intensity = (
        _validate_intensity(answers.get("intensity"))
        if "intensity" in answers
        else None
    )
    behavior = (
        _validate_behavior(answers.get("behavior")) if "behavior" in answers else None
    )
    lethality = (
        _validate_lethality(answers.get("lethality"))
        if "lethality" in answers
        else None
    )
    missing = [i for i in IDEATION_IDS if i not in answers or answers[i] is None]
    base: dict[str, Any] = {
        "scores": None,
        "findings": {},
        "intensity": intensity,
        "behavior": behavior,
        "lethality": lethality,
        "definition_version": _DEFINITION_VERSION,
    }
    if missing:
        if len(missing) == len(IDEATION_IDS):
            return {
                "status": "unanswered",
                "severity": None,
                "ideation_present": None,
                "missing_item_ids": missing,
                "flags": dict(_NO_FLAGS),
                "details": {},
            } | base
        severity = 0
        for idx, level_id in enumerate(IDEATION_IDS, start=1):
            entry = answers.get(level_id)
            if isinstance(entry, dict) and entry.get("endorsed") is True:
                severity = idx
        answered = {
            level_id: answers[level_id]
            for level_id in IDEATION_IDS
            if isinstance(answers.get(level_id), dict)
        }
        return {
            "status": "partial",
            "severity": severity,
            "ideation_present": severity > 0,
            "missing_item_ids": missing,
            "flags": _compute_flags(answered, behavior),
            "details": _build_details(answers),
        } | base
    severity = 0
    for idx, level_id in enumerate(IDEATION_IDS, start=1):
        entry = answers[level_id]
        if isinstance(entry, dict) and entry.get("endorsed") is True:
            severity = idx
    answered = {
        level_id: answers[level_id]
        for level_id in IDEATION_IDS
        if isinstance(answers.get(level_id), dict)
    }
    return {
        "status": "complete",
        "severity": severity,
        "ideation_present": severity > 0,
        "missing_item_ids": [],
        "flags": _compute_flags(answered, behavior),
        "details": _build_details(answers),
    } | base
