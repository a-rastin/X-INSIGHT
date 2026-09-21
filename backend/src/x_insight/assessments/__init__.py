import copy
from typing import Any

ALLOWED_OPERATORS = {"sum", "max"}

FORBIDDEN_EXPRESSION_KEYS = {
    "expression",
    "eval",
    "python",
    "javascript",
    "code",
    "formula",
    "function",
    "lambda",
}


def _reject_forbidden_keys(obj: Any) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in FORBIDDEN_EXPRESSION_KEYS:
                raise ValueError(f"forbidden key: {key}")
            _reject_forbidden_keys(value)
    elif isinstance(obj, list):
        for entry in obj:
            _reject_forbidden_keys(entry)


def load_definition(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("definition payload must be a dict")
    _reject_forbidden_keys(payload)
    if payload.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    assessment_type = payload.get("assessment_type")
    if not isinstance(assessment_type, str) or not assessment_type:
        raise ValueError("assessment_type must be a non-empty str")
    definition_version = payload.get("definition_version")
    if not isinstance(definition_version, str) or not definition_version:
        raise ValueError("definition_version must be a non-empty str")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty list")
    declared: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each item must be a dict")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("each item must have a non-empty str id")
        if item_id in declared:
            raise ValueError(f"duplicate item id: {item_id}")
        declared.add(item_id)
        kind = item.get("kind")
        if kind not in ("int", "enum"):
            raise ValueError(f"unknown item kind for {item_id}: {kind}")
        if kind == "int":
            minimum = item.get("min")
            maximum = item.get("max")
            if type(minimum) is not int or type(maximum) is not int:
                raise ValueError(f"int item {item_id} needs int min/max")
            if minimum > maximum:
                raise ValueError(f"int item {item_id} needs min <= max")
        else:
            values = item.get("values")
            if not isinstance(values, list) or not values:
                raise ValueError(f"enum item {item_id} needs non-empty values")
    required = payload.get("required_item_ids")
    if not isinstance(required, list):
        raise ValueError("required_item_ids must be a list")
    for entry in required:
        if not isinstance(entry, str) or entry not in declared:
            raise ValueError(f"unknown required item id: {entry}")
    rules = payload.get("result_rules")
    if not isinstance(rules, list):
        raise ValueError("result_rules must be a list")
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("each result rule must be a dict")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("each result rule needs a non-empty str id")
        if rule.get("op") not in ALLOWED_OPERATORS:
            raise ValueError(f"unknown operator for rule {rule_id}")
        rule_items = rule.get("items")
        if not isinstance(rule_items, list) or not rule_items:
            raise ValueError(f"rule {rule_id} needs a non-empty items list")
        for entry in rule_items:
            if not isinstance(entry, str) or entry not in declared:
                raise ValueError(f"unknown rule item id: {entry}")
    return copy.deepcopy(payload)


def evaluate(definition: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    normalized = load_definition(definition)
    if not isinstance(answers, dict):
        raise ValueError("answers must be a dict")
    specs: dict[str, dict[str, Any]] = {
        item["id"]: item for item in normalized["items"] if isinstance(item, dict)
    }
    declared_ids = set(specs)
    if "not_assessed" in answers:
        if answers.get("not_assessed") is True:
            if set(answers.keys()) != {"not_assessed"}:
                raise ValueError("not_assessed cannot be mixed with answers")
            required_ids: list[str] = list(normalized.get("required_item_ids", []))
            version: Any = normalized.get("definition_version")
            return {
                "status": "not_assessed",
                "missing_item_ids": required_ids,
                "item_errors": {},
                "scores": None,
                "findings": {},
                "definition_version": version,
            }
        raise ValueError("not_assessed must be True when present")
    for key in answers:
        if key not in declared_ids:
            raise ValueError(f"undeclared item id: {key}")
    for item_id, value in answers.items():
        if value is None:
            continue
        spec = specs[item_id]
        if spec.get("kind") == "int":
            if type(value) is not int:
                raise ValueError(f"item {item_id} must be an int")
            minimum = spec.get("min")
            maximum = spec.get("max")
            if type(minimum) is not int or type(maximum) is not int:
                raise ValueError(f"item {item_id} has invalid bounds")
            if value < minimum or value > maximum:
                raise ValueError(f"item {item_id} out of range")
        else:
            values = spec.get("values")
            if not isinstance(values, list) or value not in values:
                raise ValueError(f"item {item_id} has invalid value")
    required_all: list[str] = list(normalized.get("required_item_ids", []))
    version_all: Any = normalized.get("definition_version")
    base: dict[str, Any] = {
        "item_errors": {},
        "scores": None,
        "findings": {},
        "definition_version": version_all,
    }
    missing = [i for i in required_all if i not in answers or answers[i] is None]
    if missing:
        status = "unanswered" if len(missing) == len(required_all) else "partial"
        return {"status": status, "missing_item_ids": missing} | base
    rules: list[dict[str, Any]] = normalized.get("result_rules", [])
    scores: dict[str, Any] = {}
    for rule in rules:
        rule_items: list[str] = rule["items"]
        if any(i not in answers or answers[i] is None for i in rule_items):
            continue
        vals = [answers[i] for i in rule_items]
        if rule.get("op") == "sum":
            scores[rule["id"]] = sum(vals)
        elif rule.get("op") == "max":
            scores[rule["id"]] = max(vals)
    return {"status": "complete", "missing_item_ids": []} | base | {"scores": scores}
