"""S10 slice 1 explicit-selection PANSS evaluator. Pure, no I/O, no DB."""

from __future__ import annotations

from typing import Any

from x_insight.assessments import evaluate

POSITIVE_IDS: list[str] = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]
NEGATIVE_IDS: list[str] = ["N1", "N2", "N3", "N4", "N5", "N6", "N7"]
GENERAL_IDS: list[str] = [
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
ALL_30_IDS: list[str] = POSITIVE_IDS + NEGATIVE_IDS + GENERAL_IDS

PANSS_DEFINITION: dict[str, Any] = {
    "schema_version": 1,
    "assessment_type": "panss",
    "definition_version": "panss-v1",
    "items": [
        {"id": item_id, "kind": "int", "min": 1, "max": 7} for item_id in ALL_30_IDS
    ],
    "required_item_ids": list(ALL_30_IDS),
    "result_rules": [
        {"id": "positive", "op": "sum", "items": list(POSITIVE_IDS)},
        {"id": "negative", "op": "sum", "items": list(NEGATIVE_IDS)},
        {"id": "general", "op": "sum", "items": list(GENERAL_IDS)},
        {"id": "total", "op": "sum", "items": list(ALL_30_IDS)},
    ],
}


def evaluate_panss(answers: dict[str, Any]) -> dict[str, Any]:
    """Evaluate PANSS answers. Delegates to generic evaluator."""
    if type(answers) is not dict:
        raise ValueError("answers must be a dict")
    return evaluate(PANSS_DEFINITION, answers)
