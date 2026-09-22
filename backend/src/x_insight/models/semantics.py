"""S22: semantic/admission checks over structural validation output.

v1 scope: operates on the FIRST network only, consistent with S21
flattening (flat ``nodes``/``edges`` derive from the first network).
Must run AFTER structure validation; never executes a network.

S22 ``decide_activation`` is the activation gate (executable semantics +
complete reviewed package). It provides presence/shape checks only.
S25 hooks (to extend, not implemented in S22):
- validate_patient_mappings: check mapping types/relevance to patient record.
- validate_cpt_contract: check every-CPT estimation contract.
- validate_prompt_template: check prompt/template rendering contract.
- validate_queries: check declared query nodes/states and relevance.
"""

from __future__ import annotations

import math
from typing import Any

# Measured 2026-09-22 BNs/BN-04..14 max 60681 bytes / 32 nodes / 880 CPT
# cells (BN-04 largest); limits ~4x/2x/11x headroom as engineering
# anti-abuse bounds, not clinical thresholds.
DEFAULT_LIMITS: dict[str, int] = {
    "max_xml_bytes": 262144,
    "max_nodes": 64,
    "max_cpt_cells": 10000,
}


def check_admission(
    validated: dict[str, Any], limits: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return admission decision with measurements, limits, diagnostics."""
    raw_bytes = validated.get("byte_count")
    xml_bytes = raw_bytes if isinstance(raw_bytes, int) else 0

    networks = validated.get("networks")
    if (
        isinstance(networks, list)
        and networks
        and isinstance(networks[0], dict)
        and isinstance(networks[0].get("variables"), list)
    ):
        node_count = len(networks[0].get("variables", []))
        raw_defs = networks[0].get("definitions", [])
        definitions: list[Any] = list(raw_defs) if isinstance(raw_defs, list) else []
    else:
        raw_nodes = validated.get("nodes", [])
        node_count = len(raw_nodes) if isinstance(raw_nodes, list) else 0
        raw_defs2 = validated.get("definitions", [])
        definitions = list(raw_defs2) if isinstance(raw_defs2, list) else []

    cpt_cells = 0
    for d in definitions:
        if not isinstance(d, dict):
            continue
        table_text = d.get("table_text")
        if table_text is None:
            continue
        if isinstance(table_text, str):
            cpt_cells += len(table_text.split())

    eff: dict[str, Any] = dict(DEFAULT_LIMITS)
    if isinstance(limits, dict):
        eff.update(limits)
    max_xml = eff.get("max_xml_bytes")
    max_nodes = eff.get("max_nodes")
    max_cells = eff.get("max_cpt_cells")

    errors: list[dict[str, str]] = []

    def _add(code: str, message: str) -> None:
        errors.append({"code": code, "message": message[:500]})

    if isinstance(max_xml, int) and xml_bytes > max_xml:
        _add(
            "xml_too_large",
            f"xml_bytes {xml_bytes} exceeds limit {max_xml}",
        )
    if isinstance(max_nodes, int) and node_count > max_nodes:
        _add(
            "too_many_nodes",
            f"node_count {node_count} exceeds limit {max_nodes}",
        )
    if isinstance(max_cells, int) and cpt_cells > max_cells:
        _add(
            "too_many_cells",
            f"cpt_cells {cpt_cells} exceeds limit {max_cells}",
        )

    diagnostics: list[str] = []
    if isinstance(max_xml, int):
        diagnostics.append(
            f"xml_bytes={xml_bytes} <= {max_xml}"
            if xml_bytes <= max_xml
            else f"xml_bytes={xml_bytes} > {max_xml} (limit {max_xml})"
        )
    if isinstance(max_nodes, int):
        diagnostics.append(
            f"node_count={node_count} <= {max_nodes}"
            if node_count <= max_nodes
            else f"node_count={node_count} > {max_nodes} (limit {max_nodes})"
        )
    if isinstance(max_cells, int):
        diagnostics.append(
            f"cpt_cells={cpt_cells} <= {max_cells}"
            if cpt_cells <= max_cells
            else f"cpt_cells={cpt_cells} > {max_cells} (limit {max_cells})"
        )
    diagnostics.sort()
    errors.sort(key=lambda e: e["code"])
    return {
        "admitted": errors == [],
        "measurements": {
            "xml_bytes": xml_bytes,
            "node_count": node_count,
            "cpt_cells": cpt_cells,
        },
        "limits": eff,
        "diagnostics": diagnostics,
        "errors": errors,
    }


def check_semantics(validated: dict[str, Any]) -> dict[str, Any]:
    """Return executability and semantic errors for a validated document."""
    errors: list[dict[str, Any]] = []

    def _err(code: str, node: str | None, message: str) -> dict[str, Any]:
        return {"code": code, "node": node, "message": message[:500]}

    xsd_report = validated.get("xsd_report")
    xsd_valid = isinstance(xsd_report, dict) and xsd_report.get("valid") is True
    if not xsd_valid:
        return {
            "executable": False,
            "errors": [_err("xsd_invalid", None, "XSD report invalid; skip semantics")],
        }

    networks = validated.get("networks")
    if isinstance(networks, list) and networks and isinstance(networks[0], dict):
        first: dict[str, Any] = networks[0]
        raw_vars = first.get("variables", [])
        raw_defs = first.get("definitions", [])
        variables: list[dict[str, Any]] = (
            list(raw_vars) if isinstance(raw_vars, list) else []
        )
        definitions: list[dict[str, Any]] = (
            list(raw_defs) if isinstance(raw_defs, list) else []
        )
    else:
        nodes = validated.get("nodes", [])
        states = validated.get("states", {})
        variables = []
        if isinstance(nodes, list) and isinstance(states, dict):
            for n in nodes:
                st = states.get(n, [])
                variables.append(
                    {
                        "name": n,
                        "kind": "nature",
                        "states": list(st) if isinstance(st, list) else [],
                    }
                )
        definitions = []

    states_by: dict[str, list[str]] = {}
    kind_by: dict[str, str] = {}
    for v in variables:
        if not isinstance(v, dict):
            continue
        name = v.get("name")
        if not isinstance(name, str):
            continue
        st = v.get("states", [])
        kind = v.get("kind", "nature")
        states_by[name] = list(st) if isinstance(st, list) else []
        kind_by[name] = kind if isinstance(kind, str) else "nature"

    for name, st in states_by.items():
        kind = kind_by.get(name, "nature")
        if kind in ("nature", "decision") and len(st) == 0:
            errors.append(
                _err("empty_outcomes", name, f"variable {name!r} has no outcomes")
            )

    for name, st in states_by.items():
        kind = kind_by.get(name, "nature")
        if kind in ("decision", "utility"):
            errors.append(
                _err(
                    "unsupported_kind",
                    name,
                    f"variable {name!r} has kind {kind!r}; "
                    "v1 execution profile supports discrete nature only",
                )
            )

    defined: set[str] = set()
    for d in definitions:
        if isinstance(d, dict):
            child = d.get("for")
            if isinstance(child, str):
                defined.add(child)
    for name in states_by:
        if kind_by.get(name, "nature") == "nature" and name not in defined:
            errors.append(
                _err(
                    "missing_definition",
                    name,
                    f"nature variable {name!r} has no DEFINITION",
                )
            )

    for d in definitions:
        if not isinstance(d, dict):
            continue
        child = d.get("for")
        if not isinstance(child, str):
            continue
        parents = d.get("parents", [])
        parent_list: list[str] = (
            [str(p) for p in parents] if isinstance(parents, list) else []
        )
        table_text = d.get("table_text")
        raw_text = table_text if isinstance(table_text, str) else ""
        tokens = raw_text.split()
        values: list[float] = []
        parse_failed = False
        for tok in tokens:
            try:
                values.append(float(tok))
            except (ValueError, OverflowError):
                parse_failed = True
                break
        if parse_failed or any(not math.isfinite(v) for v in values):
            errors.append(
                _err(
                    "non_finite",
                    child,
                    f"table for {child!r} has non-numeric/non-finite entry",
                )
            )
            continue
        if table_text is None and not tokens:
            values = []
        kind = kind_by.get(child, "nature")
        if kind == "nature" and any(v < 0.0 or v > 1.0 for v in values):
            errors.append(
                _err(
                    "out_of_range",
                    child,
                    f"table for {child!r} has entry outside [0, 1]",
                )
            )
        if child not in states_by:
            continue
        child_n = len(states_by[child])
        parent_ns: list[int] = []
        unknown_parent = False
        for p in parent_list:
            if p not in states_by:
                unknown_parent = True
                break
            parent_ns.append(len(states_by[p]))
        if unknown_parent:
            continue
        expected = child_n * math.prod(parent_ns) if parent_ns else child_n
        if len(values) != expected:
            errors.append(
                _err(
                    "wrong_dimensions",
                    child,
                    f"table for {child!r} has {len(values)} entries, "
                    f"expected {expected}",
                )
            )
            continue
        if kind != "nature" or child_n == 0:
            continue
        bad = False
        for i in range(0, len(values), child_n):
            row = values[i : i + child_n]
            if abs(sum(row) - 1.0) > 1e-6:
                bad = True
                break
        if bad:
            errors.append(
                _err(
                    "unnormalized",
                    child,
                    f"table for {child!r} has row not summing to 1.0",
                )
            )

    adjacency: dict[str, list[str]] = {n: [] for n in states_by}
    for d in definitions:
        if not isinstance(d, dict):
            continue
        child = d.get("for")
        parents = d.get("parents", [])
        if not isinstance(child, str) or not isinstance(parents, list):
            continue
        for p in parents:
            if not isinstance(p, str):
                continue
            adjacency.setdefault(p, [])
            adjacency.setdefault(child, [])
            adjacency[p].append(child)
    color: dict[str, int] = {}
    has_cycle = False

    def _visit(node: str) -> bool:
        color[node] = 1
        for nxt in adjacency.get(node, []):
            c = color.get(nxt, 0)
            if c == 1:
                return True
            if c == 0 and _visit(nxt):
                return True
        color[node] = 2
        return False

    for node in list(adjacency):
        if color.get(node, 0) == 0 and _visit(node):
            has_cycle = True
            break
    if has_cycle:
        errors.append(_err("cycle", None, "definition graph contains a cycle"))

    errors.sort(key=lambda e: (str(e.get("code", "")), str(e.get("node") or "")))
    return {"executable": errors == [], "errors": errors}


_UNSAFE_TOKENS: tuple[str, ...] = ("__", "import", "eval", "exec", ";", "notes")


def is_safe_expression(expr: str) -> bool:
    """Return True when an applicability expression looks safe (S22 minimal).

    S25 hook: replace with an allowlist parser. S22 rejects any
    case-insensitive substring in ``__``, ``import``, ``eval``, ``exec``,
    ``;``, ``notes``.
    """
    if not isinstance(expr, str):
        return False
    lowered = expr.lower()
    for token in _UNSAFE_TOKENS:
        if token in lowered:
            return False
    return True


def decide_activation(
    validated: dict[str, Any],
    package: dict[str, Any] | None,
    semantic_report: dict[str, Any] | None = None,
    limits: dict[str, Any] | None = None,
    admission_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Decide whether a validated network plus question package may activate."""
    errors: list[dict[str, str]] = []

    def _add(code: str, message: str) -> None:
        errors.append({"code": code, "message": message[:500]})

    adm: dict[str, Any] | None = admission_report
    if adm is None:
        adm = check_admission(validated, limits)
    admitted = isinstance(adm, dict) and adm.get("admitted") is True
    if not admitted:
        detail = ""
        if isinstance(adm, dict):
            diag = adm.get("diagnostics")
            if isinstance(diag, list):
                detail = "; ".join(str(d) for d in diag)
        msg = "admission rejected"
        if detail:
            msg = f"admission rejected; {detail}"
        _add("admission_rejected", msg)

    sem: dict[str, Any] | None = semantic_report
    if sem is None:
        sem = check_semantics(validated)
    executable = isinstance(sem, dict) and sem.get("executable") is True
    if not executable:
        first_code: str | None = None
        if isinstance(sem, dict):
            raw_errs = sem.get("errors")
            if isinstance(raw_errs, list) and raw_errs:
                first = raw_errs[0]
                if isinstance(first, dict):
                    cand = first.get("code")
                    if isinstance(cand, str) and cand:
                        first_code = cand
        if first_code:
            _add(
                "semantic_not_executable",
                f"network not executable; first semantic error: {first_code}",
            )
        else:
            _add("semantic_not_executable", "network not executable")

    if package is None or not isinstance(package, dict):
        _add(
            "missing_package",
            "missing question package; activation requires complete package",
        )
    else:
        nodes_set: set[str] = set()
        states_by: dict[str, list[str]] = {}
        raw_nodes = validated.get("nodes")
        if isinstance(raw_nodes, list):
            for entry in raw_nodes:
                if isinstance(entry, str) and entry:
                    nodes_set.add(entry)
        raw_states = validated.get("states")
        if isinstance(raw_states, dict):
            for key, value in raw_states.items():
                if isinstance(key, str) and isinstance(value, list):
                    states_by[key] = [s for s in value if isinstance(s, str)]
                    if key:
                        nodes_set.add(key)
        raw_networks = validated.get("networks")
        if (
            isinstance(raw_networks, list)
            and raw_networks
            and isinstance(raw_networks[0], dict)
        ):
            first_net: dict[str, Any] = raw_networks[0]
            raw_vars = first_net.get("variables")
            if isinstance(raw_vars, list):
                for var in raw_vars:
                    if not isinstance(var, dict):
                        continue
                    name = var.get("name")
                    if not isinstance(name, str) or not name:
                        continue
                    nodes_set.add(name)
                    st = var.get("states")
                    if isinstance(st, list) and name not in states_by:
                        states_by[name] = [s for s in st if isinstance(s, str)]

        mappings = package.get("mappings")
        shape_ok = True
        if not isinstance(mappings, list) or len(mappings) == 0:
            shape_ok = False
        else:
            for item in mappings:
                if not isinstance(item, dict):
                    shape_ok = False
                    break
                node_id = item.get("node_id")
                paths = item.get("allowed_source_paths")
                if not isinstance(node_id, str) or node_id == "":
                    shape_ok = False
                    break
                if not isinstance(paths, list) or len(paths) == 0:
                    shape_ok = False
                    break
                if not all(isinstance(s, str) and s != "" for s in paths):
                    shape_ok = False
                    break
        if not shape_ok:
            _add(
                "missing_mappings",
                "missing mappings; activation requires non-empty mappings "
                "with node_id and allowed_source_paths",
            )
        if isinstance(mappings, list):
            found_note = False
            for item in mappings:
                if not isinstance(item, dict):
                    continue
                paths = item.get("allowed_source_paths")
                if not isinstance(paths, list):
                    continue
                for path in paths:
                    if isinstance(path, str) and "notes" in path.lower():
                        found_note = True
                        break
                if found_note:
                    break
            if found_note:
                _add(
                    "note_source_path",
                    "mapping allows notes source path; "
                    "free-text notes are not permitted as model input",
                )

        prompt = package.get("prompt")
        if not isinstance(prompt, str) or prompt.strip() == "":
            _add(
                "missing_prompt",
                "missing prompt; activation requires non-empty prompt text",
            )

        template = package.get("template")
        template_ok = False
        if isinstance(template, str):
            template_ok = template.strip() != ""
        elif isinstance(template, dict):
            template_ok = len(template) > 0
        if not template_ok:
            _add(
                "missing_template",
                "missing template; activation requires non-empty template",
            )

        review = package.get("review")
        review_ok = False
        if isinstance(review, dict):
            decision = review.get("decision")
            reviewer = review.get("reviewer")
            date = review.get("date")
            if (
                decision == "approved"
                and isinstance(reviewer, str)
                and reviewer.strip() != ""
                and isinstance(date, str)
                and date.strip() != ""
            ):
                review_ok = True
        if not review_ok:
            _add(
                "unreviewed_package",
                "package not approved; activation requires review "
                "decision approved with reviewer and date",
            )

        query_nodes = package.get("query_nodes")
        query_ok = False
        if (
            isinstance(query_nodes, list)
            and len(query_nodes) > 0
            and all(isinstance(n, str) and n != "" for n in query_nodes)
        ):
            query_ok = all(n in nodes_set for n in query_nodes if isinstance(n, str))
        if not query_ok:
            _add(
                "undeclared_query",
                "missing or undeclared query_nodes; activation requires "
                "non-empty declared query nodes",
            )

        query_states = package.get("query_states")
        if query_states is None:
            pass
        elif not isinstance(query_states, dict):
            _add(
                "undeclared_state",
                "malformed query_states; each state must be declared for its node",
            )
        else:
            bad_state = False
            for key, value in query_states.items():
                if not isinstance(key, str):
                    bad_state = True
                    break
                if not isinstance(value, list):
                    bad_state = True
                    break
                declared = states_by.get(key)
                if declared is None:
                    bad_state = True
                    break
                for state in value:
                    if not isinstance(state, str) or state not in declared:
                        bad_state = True
                        break
                if bad_state:
                    break
            if bad_state:
                _add(
                    "undeclared_state",
                    "undeclared query state; each state must be declared for its node",
                )

        applicability = package.get("applicability")
        if applicability is None:
            pass
        elif isinstance(applicability, str) and applicability.strip() == "":
            pass
        elif isinstance(applicability, str):
            if not is_safe_expression(applicability):
                _add(
                    "unsafe_expression",
                    "unsafe applicability expression; "
                    "only safe expressions are permitted",
                )
        else:
            _add(
                "unsafe_expression",
                "unsafe applicability expression; only safe expressions are permitted",
            )

    errors.sort(key=lambda e: e["code"])
    activatable = len(errors) == 0 and executable
    base_reason = (
        "import OK; activation requires executable semantics and complete "
        "reviewed package (S25 extends patient mappings, CPT contract, "
        "prompt template, queries)"
    )[:500]
    reasons: list[str] = [base_reason]
    for item in errors:
        reasons.append(f"{item['code']}: {item['message']}"[:500])
    return {"activatable": activatable, "reasons": reasons, "errors": errors}
