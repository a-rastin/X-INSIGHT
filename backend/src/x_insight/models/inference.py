"""S23 slice 1: CPT validation, effective artifact, exact inference (T5).

Synthetic fixtures only; never BNs/ as oracle. No approximate inference.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import math
import multiprocessing as mp
import platform
import queue
from typing import Any

import numpy as np
from lxml import etree  # type: ignore[import-untyped]
from pgmpy.factors.discrete import TabularCPD  # type: ignore[import-untyped]
from pgmpy.inference import VariableElimination  # type: ignore[import-untyped]
from pgmpy.models import DiscreteBayesianNetwork  # type: ignore[import-untyped]

PCT_SUM_TOL = 1e-6
PROB_SUM_TOL = 1e-8

ENGINE_PIN: dict[str, str] = {
    "engine": "pgmpy.VariableElimination",
    "engine_version": "1.1.2",
    "python": platform.python_version(),
    "dtype": "float64",
    "elimination_order": "artifact-node-order",
}

RESOURCE_DEFAULTS: dict[str, float] = {
    # Engineering execution bounds only (not clinical content).
    "timeout_s": 30.0,
}


def _check_percentages(percentages: Any, where: str) -> list[float]:
    if not isinstance(percentages, list):
        raise ValueError(f"{where}: percentages must be a list")
    out: list[float] = []
    for v in percentages:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{where}: percentage {v!r} must be int/float")
        f = float(v)
        if not math.isfinite(f):
            raise ValueError(f"{where}: percentage {v!r} must be finite")
        if f < 0.0 or f > 100.0:
            raise ValueError(f"{where}: percentage {v!r} outside [0, 100]")
        out.append(f)
    if abs(math.fsum(out) - 100.0) > PCT_SUM_TOL:
        raise ValueError(f"{where}: percentages must sum to 100 within 1e-6")
    return out


def validate_cpt_response(response: dict[str, Any]) -> dict[str, Any]:
    """Validate a full-CPT response; return an accepted deep copy.

    Enforces percentage type/finiteness/range/sum; never normalizes,
    clips, rounds, or repairs. Returns a deep copy so callers cannot
    mutate the input through the accepted value.
    """
    if not isinstance(response, dict):
        raise ValueError("response must be a dict")
    for key in ("question_key", "network_version", "network_hash", "tables"):
        if key not in response:
            raise ValueError(f"response missing {key!r}")
    for key in response:
        if key not in ("question_key", "network_version", "network_hash", "tables"):
            raise ValueError(f"response has extra field {key!r}")
    if not isinstance(response["question_key"], str):
        raise ValueError("question_key must be a string")
    if not isinstance(response["network_version"], str):
        raise ValueError("network_version must be a string")
    if not isinstance(response["network_hash"], str):
        raise ValueError("network_hash must be a string")
    tables = response["tables"]
    if not isinstance(tables, list) or not tables:
        raise ValueError("tables must be a non-empty list")
    seen: set[str] = set()
    for table in tables:
        if not isinstance(table, dict):
            raise ValueError("each table must be a dict")
        for key in ("node_id", "parent_ids", "states", "rows"):
            if key not in table:
                raise ValueError(f"table missing {key!r}")
        for key in table:
            if key not in ("node_id", "parent_ids", "states", "rows"):
                raise ValueError(f"table has extra field {key!r}")
        node_id = table["node_id"]
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("node_id must be a non-empty string")
        if node_id in seen:
            raise ValueError(f"duplicate table for node {node_id!r}")
        seen.add(node_id)
        parent_ids = table["parent_ids"]
        if not isinstance(parent_ids, list) or not all(
            isinstance(p, str) for p in parent_ids
        ):
            raise ValueError(f"{node_id}: parent_ids must be list[str]")
        states = table["states"]
        if (
            not isinstance(states, list)
            or not states
            or not all(isinstance(s, str) for s in states)
            or len(set(states)) != len(states)
        ):
            raise ValueError(f"{node_id}: states must be non-empty unique list")
        rows = table["rows"]
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{node_id}: rows must be a non-empty list")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{node_id}: each row must be a dict")
            if "parent_states" not in row or "percentages" not in row:
                raise ValueError(f"{node_id}: row missing parent_states/percentages")
            for key in row:
                if key not in ("parent_states", "percentages"):
                    raise ValueError(f"{node_id}: row has extra field {key!r}")
            ps = row["parent_states"]
            if not isinstance(ps, list) or len(ps) != len(parent_ids):
                raise ValueError(f"{node_id}: parent_states length mismatch")
            if not all(isinstance(s, str) for s in ps):
                raise ValueError(f"{node_id}: parent_states must be list[str]")
            pct = row["percentages"]
            if not isinstance(pct, list) or len(pct) != len(states):
                raise ValueError(f"{node_id}: percentages length mismatch")
            _check_percentages(pct, f"{node_id}/{ps}")
        if not parent_ids:
            if len(rows) != 1 or rows[0]["parent_states"] != []:
                raise ValueError(f"{node_id}: root must have one empty-parent row")
    return copy.deepcopy(response)


def _validated_parents(validated: dict[str, Any]) -> dict[str, list[str]]:
    networks = validated.get("networks")
    if (
        isinstance(networks, list)
        and networks
        and isinstance(networks[0], dict)
        and isinstance(networks[0].get("definitions"), list)
    ):
        out: dict[str, list[str]] = {}
        for d in networks[0]["definitions"]:
            if not isinstance(d, dict):
                continue
            child = d.get("for")
            parents = d.get("parents", d.get("given", []))
            if isinstance(child, str) and isinstance(parents, list):
                out[child] = [str(p) for p in parents if isinstance(p, str)]
        return out
    edges = validated.get("edges", [])
    out2: dict[str, list[str]] = {}
    nodes = validated.get("nodes", [])
    if isinstance(nodes, list):
        for n in nodes:
            if isinstance(n, str):
                out2[n] = []
    if isinstance(edges, list):
        for e in edges:
            if isinstance(e, (list, tuple)) and len(e) == 2:
                parent, child = str(e[0]), str(e[1])
                out2.setdefault(child, []).append(parent)
    return out2


def _safe_parser() -> Any:
    return etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        recover=False,
    )


def build_effective_artifact(
    validated: dict[str, Any], accepted: dict[str, Any]
) -> dict[str, Any]:
    """Build a run-local effective artifact from accepted percentages.

    Verifies hash/node/parent/state order and canonical Cartesian row
    order (first parent slowest); divides by 100 without rounding;
    checks probability sums within 1e-8; freezes effective XML bytes
    and hash. Never mutates ``validated`` or its stored source bytes.
    """
    source_sha = validated.get("source_sha256")
    if not isinstance(source_sha, str):
        raise ValueError("validated missing source_sha256")
    net_hash = accepted.get("network_hash")
    if net_hash != source_sha:
        raise ValueError("network_hash must equal validated source_sha256")
    nodes = validated.get("nodes")
    if not isinstance(nodes, list) or not all(isinstance(n, str) for n in nodes):
        raise ValueError("validated nodes must be list[str]")
    node_list: list[str] = [str(n) for n in nodes]
    states_raw = validated.get("states")
    if not isinstance(states_raw, dict):
        raise ValueError("validated states must be a dict")
    states: dict[str, list[str]] = {}
    for n in node_list:
        st = states_raw.get(n)
        if not isinstance(st, list) or not all(isinstance(s, str) for s in st):
            raise ValueError(f"validated states missing for {n!r}")
        states[n] = [str(s) for s in st]
    expected_parents = _validated_parents(validated)

    tables = accepted.get("tables")
    if not isinstance(tables, list):
        raise ValueError("accepted tables must be a list")
    if [t.get("node_id") for t in tables if isinstance(t, dict)] != node_list:
        raise ValueError("tables must follow validated node order, one per node")
    if len(tables) != len(node_list):
        raise ValueError("one table per node is required")

    probabilities: dict[str, list[list[float]]] = {}
    parent_configs: dict[str, list[list[str]]] = {}
    percentages: dict[str, list[list[float]]] = {}
    parents_out: dict[str, list[str]] = {}
    for table in tables:
        if not isinstance(table, dict):
            raise ValueError("each table must be a dict")
        node_id = str(table["node_id"])
        parent_ids_raw = table["parent_ids"]
        table_states_raw = table["states"]
        rows_raw = table["rows"]
        if not isinstance(parent_ids_raw, list) or not isinstance(
            table_states_raw, list
        ):
            raise ValueError(f"{node_id}: malformed table")
        parent_ids = [str(p) for p in parent_ids_raw]
        table_states = [str(s) for s in table_states_raw]
        if parent_ids != expected_parents.get(node_id, []):
            raise ValueError(f"{node_id}: parent_ids must match GIVEN order")
        if table_states != states[node_id]:
            raise ValueError(f"{node_id}: states must match validated order")
        if not isinstance(rows_raw, list):
            raise ValueError(f"{node_id}: rows must be a list")
        # Canonical Cartesian order: first parent slowest.
        # itertools.product over GIVEN-ordered parent state lists yields
        # exactly this: first parent outermost, last parent innermost.
        parent_domains = [states[p] for p in parent_ids]
        expected_cfgs: list[tuple[str, ...]] = (
            list(itertools.product(*parent_domains)) if parent_ids else [()]
        )
        if len(rows_raw) != len(expected_cfgs):
            raise ValueError(f"{node_id}: one row per parent configuration")
        prob_rows: list[list[float]] = []
        pct_rows: list[list[float]] = []
        cfg_out: list[list[str]] = []
        for i, row in enumerate(rows_raw):
            if not isinstance(row, dict):
                raise ValueError(f"{node_id}: each row must be a dict")
            ps = row.get("parent_states")
            pct = row.get("percentages")
            if not isinstance(ps, list) or [str(s) for s in ps] != list(
                expected_cfgs[i]
            ):
                raise ValueError(f"{node_id}: row {i} parent_states order mismatch")
            if not isinstance(pct, list) or len(pct) != len(table_states):
                raise ValueError(f"{node_id}: row {i} percentages length mismatch")
            pct_floats = _check_percentages(pct, f"{node_id}/{ps}")
            # Divide by 100 with no presentation rounding or repair.
            probs = [float(v) / 100.0 for v in pct_floats]
            if abs(math.fsum(probs) - 1.0) > PROB_SUM_TOL:
                raise ValueError(f"{node_id}: probability row must sum to 1")
            prob_rows.append(probs)
            pct_rows.append(pct_floats)
            cfg_out.append([str(s) for s in ps])
        probabilities[node_id] = prob_rows
        parent_configs[node_id] = cfg_out
        percentages[node_id] = pct_rows
        parents_out[node_id] = list(parent_ids)

    source_bytes = validated.get("source_bytes")
    if not isinstance(source_bytes, (bytes, bytearray)):
        raise ValueError("validated missing source_bytes")
    source_copy = bytes(source_bytes)
    root = etree.fromstring(source_copy, _safe_parser())
    networks_el = root.findall("NETWORK")
    scopes = networks_el if networks_el else [root]
    # Operate on the first network only (S21 flattening contract).
    scope = scopes[0]
    for definition in scope.findall("DEFINITION"):
        for_el = definition.find("FOR")
        if for_el is None or for_el.text is None:
            continue
        child = str(for_el.text)
        if child not in probabilities:
            raise ValueError(f"effective XML: unknown definition {child!r}")
        # XMLBIF TABLE order: child state fastest, last GIVEN parent next,
        # first GIVEN parent slowest. Flatten canonical rows (already
        # first-parent-slowest) with child states in order inside each row.
        flat: list[str] = []
        for row in probabilities[child]:
            for p in row:
                flat.append(repr(float(p)))
        table_el = definition.find("TABLE")
        if table_el is None:
            table_el = etree.SubElement(definition, "TABLE")
        table_el.text = " ".join(flat)
    effective_xml = bytes(etree.tostring(scope, encoding="utf-8"))
    # Re-serialize the full document with the updated first network so
    # document-level metadata/order outside DEFINITIONs is preserved.
    if networks_el:
        effective_xml = bytes(etree.tostring(root, encoding="utf-8"))
    effective_hash = hashlib.sha256(effective_xml).hexdigest()

    return {
        "source_sha256": source_sha,
        "network_hash": source_sha,
        "question_key": accepted.get("question_key"),
        "network_version": accepted.get("network_version"),
        "nodes": list(node_list),
        "states": copy.deepcopy(states),
        "parents": copy.deepcopy(parents_out),
        "parent_configs": copy.deepcopy(parent_configs),
        "percentages": copy.deepcopy(percentages),
        "probabilities": copy.deepcopy(probabilities),
        "effective_xml": effective_xml,
        "effective_hash": effective_hash,
    }


def _build_model(artifact: dict[str, Any]) -> DiscreteBayesianNetwork:
    """Build a pgmpy network from effective artifact tables only."""
    nodes = artifact["nodes"]
    states = artifact["states"]
    parents = artifact["parents"]
    probabilities = artifact["probabilities"]
    if not (
        isinstance(nodes, list)
        and isinstance(states, dict)
        and isinstance(parents, dict)
        and isinstance(probabilities, dict)
    ):
        raise ValueError("malformed effective artifact")
    edges: list[tuple[str, str]] = []
    for node in nodes:
        if not isinstance(node, str):
            raise ValueError("malformed artifact nodes")
        for p in parents.get(node, []):
            edges.append((str(p), node))
    model = DiscreteBayesianNetwork(edges)
    state_names: dict[str, list[str]] = {
        str(n): [str(s) for s in states[str(n)]] for n in nodes
    }
    for node in nodes:
        n = str(node)
        node_states: list[str] = state_names[n]
        node_parents: list[str] = [str(p) for p in parents.get(n, [])]
        rows: list[list[float]] = probabilities[n]
        card = len(node_states)
        if not node_parents:
            if len(rows) != 1 or len(rows[0]) != card:
                raise ValueError(f"{n}: malformed root probabilities")
            values = np.array([[float(v)] for v in rows[0]], dtype=np.float64)
            cpd = TabularCPD(
                variable=n,
                variable_card=card,
                values=values,
                state_names={n: node_states},
            )
        else:
            # XMLBIF->pgmpy mapping: XMLBIF flat order is child-fastest
            # with first GIVEN parent slowest; pgmpy TabularCPD expects
            # values[child_state][parent_cfg] with columns in Cartesian
            # order where the first evidence entry varies slowest.
            # Passing evidence in GIVEN order and columns in our canonical
            # first-parent-slowest order therefore aligns exactly.
            # Transpose: rows[j][i] -> values[i][j].
            ncols = len(rows)
            values2 = np.array(rows, dtype=np.float64).T.reshape(card, ncols)
            evidence_card = [len(state_names[p]) for p in node_parents]
            cpd = TabularCPD(
                variable=n,
                variable_card=card,
                values=values2,
                evidence=node_parents,
                evidence_card=evidence_card,
                state_names={k: state_names[k] for k in [n, *node_parents]},
            )
        model.add_cpds(cpd)
    if not model.check_model():
        raise ValueError("effective model failed pgmpy check_model")
    return model


def _count_cpt_cells(artifact: dict[str, Any]) -> int:
    """Count effective CPT cells (engineering bound, not clinical)."""
    probabilities = artifact.get("probabilities", {})
    if not isinstance(probabilities, dict):
        raise ValueError("malformed effective artifact")
    total = 0
    for rows in probabilities.values():
        if not isinstance(rows, list):
            raise ValueError("malformed effective artifact")
        for row in rows:
            if not isinstance(row, list):
                raise ValueError("malformed effective artifact")
            total += len(row)
    return total


def _enforce_engine_limits(
    artifact: dict[str, Any], engine_config: dict[str, Any] | None
) -> None:
    """Enforce engineering resource limits before expensive work."""
    if engine_config is None:
        return
    if not isinstance(engine_config, dict):
        raise ValueError("resource exhausted: engine_config must be a dict limit")
    nodes = artifact.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("malformed effective artifact")
    if "max_nodes" in engine_config and engine_config["max_nodes"] is not None:
        limit = engine_config["max_nodes"]
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, float))
            or not math.isfinite(float(limit))
        ):
            raise ValueError(f"resource exhausted: invalid max_nodes limit {limit!r}")
        if len(nodes) > int(limit) or len(nodes) > float(limit):
            raise ValueError(
                f"resource exhausted: node count {len(nodes)} exceeds "
                f"max_nodes {limit} limit"
            )
    if "max_cpt_cells" in engine_config and engine_config["max_cpt_cells"] is not None:
        limit = engine_config["max_cpt_cells"]
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, float))
            or not math.isfinite(float(limit))
        ):
            raise ValueError(
                f"resource exhausted: invalid max_cpt_cells limit {limit!r}"
            )
        cells = _count_cpt_cells(artifact)
        if cells > float(limit):
            raise ValueError(
                f"resource exhausted: cpt cells {cells} exceeds "
                f"max_cpt_cells {limit} limit"
            )
    if "timeout_s" in engine_config and engine_config["timeout_s"] is not None:
        limit = engine_config["timeout_s"]
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, float))
            or not math.isfinite(float(limit))
            or float(limit) <= 0.0
        ):
            raise ValueError(f"resource exhausted: timeout_s {limit!r} limit exhausted")


def _validate_query(
    artifact: dict[str, Any], target: str, state: str, evidence: dict[str, str]
) -> list[str]:
    nodes = artifact.get("nodes", [])
    states = artifact.get("states", {})
    if not isinstance(nodes, list) or target not in nodes:
        raise ValueError(f"unknown target {target!r}")
    if not isinstance(states, dict) or state not in states.get(target, []):
        raise ValueError(f"unknown state {state!r} for {target!r}")
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be a dict")
    for k, v in evidence.items():
        if k not in nodes:
            raise ValueError(f"unknown evidence node {k!r}")
        if not isinstance(states, dict) or v not in states.get(k, []):
            raise ValueError(f"unknown evidence state {v!r} for {k!r}")
    return [str(n) for n in nodes]


def _evidence_joint(artifact: dict[str, Any], evidence: dict[str, str]) -> float:
    """Exact float64 joint P(evidence) from effective tables only."""
    if not evidence:
        return 1.0
    nodes_raw = artifact.get("nodes", [])
    states_raw = artifact.get("states", {})
    parents_raw = artifact.get("parents", {})
    probabilities_raw = artifact.get("probabilities", {})
    if not (
        isinstance(nodes_raw, list)
        and isinstance(states_raw, dict)
        and isinstance(parents_raw, dict)
        and isinstance(probabilities_raw, dict)
    ):
        raise ValueError("malformed effective artifact")
    nodes: list[str] = [str(n) for n in nodes_raw]
    states: dict[str, list[str]] = {
        str(n): [str(s) for s in states_raw[str(n)]] for n in nodes
    }
    parents: dict[str, list[str]] = {
        str(n): [str(p) for p in parents_raw.get(str(n), [])] for n in nodes
    }
    parent_configs_raw = artifact.get("parent_configs", {})
    row_lut: dict[str, dict[tuple[str, ...], int]] = {}
    for n in nodes:
        stored = (
            parent_configs_raw.get(n) if isinstance(parent_configs_raw, dict) else None
        )
        if isinstance(stored, list) and (len(parents[n]) == 0 or len(stored) > 0):
            lut: dict[tuple[str, ...], int] = {}
            for idx, cfg in enumerate(stored):
                if isinstance(cfg, list):
                    lut[tuple(str(s) for s in cfg)] = idx
            row_lut[n] = lut
        else:
            domains = [states[p] for p in parents[n]]
            if not domains:
                row_lut[n] = {(): 0}
            else:
                lut2: dict[tuple[str, ...], int] = {}
                for idx, cfg in enumerate(itertools.product(*domains)):
                    lut2[tuple(str(s) for s in cfg)] = idx
                row_lut[n] = lut2
    node_index = {n: i for i, n in enumerate(nodes)}
    domains_all = [states[n] for n in nodes]
    terms: list[float] = []
    for assignment in itertools.product(*domains_all):
        consistent = True
        for k, v in evidence.items():
            if assignment[node_index[str(k)]] != str(v):
                consistent = False
                break
        if not consistent:
            continue
        joint = 1.0
        for i, n in enumerate(nodes):
            val = str(assignment[i])
            s_idx = states[n].index(val)
            par = parents[n]
            key = tuple(str(assignment[node_index[p]]) for p in par) if par else ()
            r_idx = row_lut[n].get(key)
            if r_idx is None:
                raise ValueError("malformed effective artifact")
            rows_n = probabilities_raw[n]
            if not isinstance(rows_n, list):
                raise ValueError("malformed effective artifact")
            row = rows_n[r_idx]
            if not isinstance(row, list):
                raise ValueError("malformed effective artifact")
            joint *= float(row[s_idx])
            if joint == 0.0:
                break
        terms.append(joint)
    return float(math.fsum(terms))


def _exact_posterior(
    artifact: dict[str, Any], target: str, state: str, evidence: dict[str, str]
) -> float:
    """Shared deterministic exact-inference core (effective tables only)."""
    nodes = _validate_query(artifact, target, state, evidence)
    norm_evidence: dict[str, str] = {str(k): str(v) for k, v in evidence.items()}
    if norm_evidence:
        joint = _evidence_joint(artifact, norm_evidence)
        if joint <= 0.0:
            raise ValueError(f"impossible evidence: joint P(evidence)={joint} is zero")
    if target in norm_evidence:
        return 1.0 if norm_evidence[target] == state else 0.0
    model = _build_model(artifact)
    # Deterministic elimination order: artifact node order excluding target
    # and observed evidence (pgmpy requires elimination vars disjoint).
    elim_order: list[str] = [n for n in nodes if n != target and n not in norm_evidence]
    ve = VariableElimination(model)
    try:
        result = ve.query(
            [target],
            evidence=dict(norm_evidence) if norm_evidence else None,
            elimination_order=elim_order,
            show_progress=False,
        )
    except Exception as exc:
        joint2 = _evidence_joint(artifact, norm_evidence) if norm_evidence else 1.0
        if norm_evidence and joint2 <= 0.0:
            raise ValueError(
                f"impossible evidence: query failed with zero-probability "
                f"evidence: {exc}"
            ) from exc
        raise ValueError(f"inference failed: {exc}") from exc
    try:
        value = float(result.get_value(**{target: state}))
    except Exception as exc:
        raise ValueError(f"inference result unreadable: {exc}") from exc
    if not math.isfinite(value):
        raise ValueError(f"impossible evidence: non-finite posterior {value!r}")
    if norm_evidence:
        joint_after = _evidence_joint(artifact, norm_evidence)
        if joint_after <= 0.0:
            raise ValueError(
                f"impossible evidence: joint P(evidence)={joint_after} is zero"
            )
    return value


def infer(
    artifact: dict[str, Any],
    target: str,
    state: str,
    evidence: dict[str, str],
    engine_config: dict[str, Any] | None = None,
) -> float:
    """Return P(target=state | evidence) via deterministic exact inference.

    Reads ONLY effective artifact tables; never registered base tables.
    Uses pinned pgmpy VariableElimination with float64 and deterministic
    artifact-node-order elimination. Never approximates.
    """
    _enforce_engine_limits(artifact, engine_config)
    return _exact_posterior(artifact, target, state, evidence)


def replay(
    artifact: dict[str, Any],
    target: str,
    state: str,
    evidence: dict[str, str],
) -> float:
    """Deterministic exact replay from the frozen stored artifact only.

    No provider argument, no network/socket I/O. Identical pgmpy path to
    :func:`infer` without engine limits.
    """
    return _exact_posterior(artifact, target, state, evidence)


def _resolve_timeout(
    engine_config: dict[str, Any] | None, timeout_s: float | None
) -> float:
    if timeout_s is not None:
        return float(timeout_s)
    if isinstance(engine_config, dict) and engine_config.get("timeout_s") is not None:
        return float(engine_config["timeout_s"])
    return float(RESOURCE_DEFAULTS["timeout_s"])


def _subprocess_worker(
    q: Any,
    artifact: dict[str, Any],
    target: str,
    state: str,
    evidence: dict[str, str],
    engine_config: dict[str, Any] | None,
) -> None:
    try:
        q.put(("ok", infer(artifact, target, state, evidence, engine_config)))
    except Exception as exc:
        q.put(("error", str(exc)))


def infer_in_subprocess(
    artifact: dict[str, Any],
    target: str,
    state: str,
    evidence: dict[str, str],
    engine_config: dict[str, Any] | None = None,
    timeout_s: float | None = None,
) -> float:
    """Run exact inference in a bounded child process (no approximation)."""
    try:
        timeout = _resolve_timeout(engine_config, timeout_s)
    except Exception as exc:
        raise ValueError(f"resource exhausted: invalid timeout limit ({exc})") from exc
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise ValueError(f"resource exhausted: timeout_s {timeout!r} limit exhausted")
    _enforce_engine_limits(artifact, engine_config)
    ctx = mp.get_context("spawn")
    q: Any = ctx.Queue()
    proc = ctx.Process(
        target=_subprocess_worker,
        args=(q, artifact, target, state, evidence, engine_config),
        daemon=True,
    )
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join(5)
        try:
            proc.kill()
        except Exception:
            pass
        raise ValueError(
            f"resource exhausted: inference timed out after {timeout}s limit"
        )
    try:
        status, payload = q.get_nowait()
    except queue.Empty as exc:
        raise ValueError(
            "resource exhausted: inference child produced no result limit"
        ) from exc
    if status == "ok":
        return float(payload)
    raise ValueError(str(payload))
