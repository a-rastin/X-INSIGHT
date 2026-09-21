"""Released structured-history definition loading and value validation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from x_insight.contracts import to_utc_z, utc_now

DEFAULT_CONTENT_DIR = Path(__file__).resolve().parents[4] / "content" / "history"
EFFECT_IDS = {
    "tardive_dyskinesia",
    "akathisia",
    "parkinsonism",
    "acute_dystonia",
}


def _content_dir() -> Path:
    configured = os.environ.get("X_INSIGHT_HISTORY_CONTENT_DIR")
    return Path(configured) if configured else DEFAULT_CONTENT_DIR


def _load_released_definition() -> dict[str, Any]:
    try:
        raw = json.loads((_content_dir() / "history.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("released history definition unavailable") from exc
    if (
        not isinstance(raw, dict)
        or raw.get("review_status") != "released"
        or raw.get("content_type") != "history"
        or not isinstance(raw.get("definition"), dict)
    ):
        raise ValueError("released history definition unavailable")
    definition: dict[str, Any] = raw["definition"]
    version = definition.get("definition_version")
    fields = definition.get("fields")
    if (
        not isinstance(version, str)
        or not version
        or raw.get("content_version") != version
        or not isinstance(fields, list)
        or not fields
    ):
        raise ValueError("invalid released history definition")
    return definition


def validate_and_stamp_history(
    history: Any, *, actor_id: str, encounter_revision: int
) -> dict[str, Any]:
    """Validate a client history block and add authoritative provenance."""
    if not isinstance(history, dict) or set(history) != {
        "definition_version",
        "values",
    }:
        raise ValueError("invalid history block")
    definition = _load_released_definition()
    if history["definition_version"] != definition["definition_version"]:
        raise ValueError("history definition version is not released")
    values = history["values"]
    if not isinstance(values, dict):
        raise ValueError("history values must be an object")

    declared: set[str] = set()
    for field in definition["fields"]:
        if not isinstance(field, dict):
            raise ValueError("invalid released history definition")
        field_id = field.get("id")
        if (
            not isinstance(field_id, str)
            or not field_id
            or field_id in declared
            or field.get("kind") != "tri_state_boolean"
            or field.get("allowed_statuses") != ["known", "unknown", "not_assessed"]
        ):
            raise ValueError("invalid released history definition")
        declared.add(field_id)

    if not set(values).issubset(declared):
        raise ValueError("undeclared history field")
    for field_id, entry in values.items():
        if not isinstance(entry, dict) or set(entry) != {"status", "value"}:
            raise ValueError(f"invalid history value: {field_id}")
        status = entry["status"]
        value = entry["value"]
        if status == "known":
            if type(value) is not bool:
                raise ValueError(f"known history value must be boolean: {field_id}")
        elif status in {"unknown", "not_assessed"}:
            if value is not None:
                raise ValueError(f"missing history value must be null: {field_id}")
        else:
            raise ValueError(f"invalid history status: {field_id}")

    return {
        "definition_version": history["definition_version"],
        "values": values,
        "provenance": {
            "actor_id": actor_id,
            "recorded_at": to_utc_z(utc_now()),
            "encounter_revision": encounter_revision,
        },
    }


def validate_and_stamp_effects(
    effects: Any, *, actor_id: str, encounter_revision: int
) -> dict[str, Any]:
    """Validate all four adverse effects and add authoritative provenance."""
    if not isinstance(effects, dict) or set(effects) != {
        "definition_version",
        "values",
    }:
        raise ValueError("invalid effects block")
    definition = _load_released_definition()
    if effects["definition_version"] != definition["definition_version"]:
        raise ValueError("effects definition version is not released")
    values = effects["values"]
    if not isinstance(values, dict):
        raise ValueError("effect values must be an object")

    declared: dict[str, set[str]] = {}
    effect_definitions = definition.get("effects")
    if not isinstance(effect_definitions, list):
        raise ValueError("invalid released effect definition")
    for effect in effect_definitions:
        if not isinstance(effect, dict):
            raise ValueError("invalid released effect definition")
        effect_id = effect.get("id")
        severities = effect.get("severity_values")
        if (
            not isinstance(effect_id, str)
            or effect_id in declared
            or effect.get("status_values") != ["present", "absent", "not_assessed"]
            or not isinstance(severities, list)
            or not severities
            or any(not isinstance(value, str) or not value for value in severities)
            or len(set(severities)) != len(severities)
        ):
            raise ValueError("invalid released effect definition")
        declared[effect_id] = set(severities)
    if set(declared) != EFFECT_IDS or set(values) != EFFECT_IDS:
        raise ValueError("all four declared effects are required")

    for effect_id, entry in values.items():
        if not isinstance(entry, dict) or set(entry) != {"status", "severity"}:
            raise ValueError(f"invalid effect value: {effect_id}")
        status = entry["status"]
        severity = entry["severity"]
        if status == "present":
            if severity not in declared[effect_id]:
                raise ValueError(f"invalid effect severity: {effect_id}")
        elif status in {"absent", "not_assessed"}:
            if severity is not None:
                raise ValueError(f"effect severity must be null: {effect_id}")
        else:
            raise ValueError(f"invalid effect status: {effect_id}")

    return {
        "definition_version": effects["definition_version"],
        "values": values,
        "provenance": {
            "actor_id": actor_id,
            "recorded_at": to_utc_z(utc_now()),
            "encounter_revision": encounter_revision,
        },
    }
