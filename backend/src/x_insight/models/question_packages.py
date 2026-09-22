"""S25 slice 1: question-package contract (T5)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from x_insight.models.validation import validate_xmlbif

REQ: tuple[str, ...] = (
    "schema_version",
    "question_key",
    "title",
    "workflow",
    "version",
    "review_status",
    "network_file",
    "network_hash",
    "declared_node_order",
    "variables",
    "patient_mappings",
    "applicability",
    "cpt_contract",
    "query_nodes",
    "evidence_mappings",
    "impossible_evidence_policy",
    "likelihood_evidence",
    "prompt_version",
    "template_version",
    "reviewed_result_mapping",
    "numerical_tolerances",
    "context_output_resource_limits",
    "engine_configuration",
    "review",
)

TOLS: dict[str, float] = {
    "percentage_row_sum_absolute": 1e-06,
    "probability_sum_after_divide_by_100_absolute": 1e-08,
    "replay_posterior_absolute": 1e-09,
}

VTYPES = ("enum", "boolean", "integer", "number", "string")
USAGES = ("cpt_context", "observation", "both")
WFLOWS = ("registration", "followup")
EXEMPT = (
    "needs_clarification",
    "not_applicable",
    "unknown_disclosure",
    "context_note",
)
# S25-compat: owner-approved real packages use false-gate review branches
# beyond not_applicable (e.g. indication_not_established,
# consideration_table, outside_scope, no_current_treatment_rule).
FALSE_GATE_BRANCHES = frozenset(
    {
        "not_applicable",
        "indication_not_established",
        "consideration_table",
        "outside_scope",
        "no_current_treatment_rule",
    }
)
# S25-compat: display-only template slots that are intentionally not in the
# "slots" list (branch keys, top-level template keys, p_-prefixed posterior
# display values, *_table renderings, plus a fixed allowlist).
SLOT_ALLOWLIST = frozenset(
    {
        "network_version",
        "urgent_text",
        "unknown_fields_or_none",
        "missing_fields",
        "effect_source",
        "choice_table",
        "safety_table",
        "delivery_table",
        "discussion_table",
        "consideration_table",
        "ddi_pointer",
        "unknown_disclosure",
        "context_note",
    }
)
# S25-compat: runs.pinned_ddi_report is an explicitly non-evidence
# informational reference ("never substituted for this review").
RUNS_REPORT_PREFIX = "runs.pinned_ddi_report"
SINGLE_TOKEN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
GATE_RE = re.compile(r"\bAND\b|\bOR\b")
NOT_NEVER_RE = re.compile(r"\b(not|never)\b", flags=re.IGNORECASE)
SLOT_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")


def _e(code: str, msg: str) -> dict[str, str]:
    return {"code": code, "message": msg[:500]}


def _is_applicability(nid: Any) -> bool:
    return isinstance(nid, str) and "(applicability input" in nid.lower()


def _usage_is_both(usage: Any) -> bool:
    return isinstance(usage, str) and usage.strip().lower().startswith("both")


def _usage_ok(usage: Any) -> bool:
    if not isinstance(usage, str):
        return False
    u = usage.strip().lower()
    if u in USAGES:
        return True
    return u.startswith(("both ", "both when", "cpt_context", "observation"))


def _has_gate(expression: Any) -> bool:
    return isinstance(expression, str) and GATE_RE.search(expression) is not None


def _nes(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _norm(h: str) -> str:
    t = h.strip()
    if t.lower().startswith("sha256:"):
        return t.split(":", 1)[1].strip()
    return t


def _states(v: Any) -> dict[str, list[str]]:
    if not isinstance(v, dict):
        return {}
    raw = v.get("states")
    if not isinstance(raw, dict):
        return {}
    o: dict[str, list[str]] = {}
    for k, val in raw.items():
        if isinstance(k, str) and isinstance(val, list):
            o[k] = [s for s in val if isinstance(s, str)]
    return o


def _parents(v: Any) -> dict[str, list[str]]:
    if not isinstance(v, dict):
        return {}
    nets = v.get("networks")
    if not isinstance(nets, list) or not nets:
        return {}
    fst = nets[0]
    if not isinstance(fst, dict):
        return {}
    defs = fst.get("definitions")
    if not isinstance(defs, list):
        return {}
    o: dict[str, list[str]] = {}
    for d in defs:
        if not isinstance(d, dict):
            continue
        c = d.get("for")
        if not isinstance(c, str):
            continue
        p = d.get("parents")
        if p is None:
            p = d.get("given")
        if not isinstance(p, list):
            continue
        o[c] = [str(x) for x in p if isinstance(x, str)]
    return o


def validate_package(
    manifest: dict[str, Any],
    validated: dict[str, Any],
    prompt_text: str,
    template: dict[str, Any],
    review: dict[str, Any],
    examples: dict[str, Any],
) -> dict[str, Any]:
    errs: list[dict[str, str]] = []
    m: dict[str, Any] = manifest if isinstance(manifest, dict) else {}
    if not isinstance(manifest, dict):
        errs.append(_e("manifest_missing_field", "bad manifest"))
    else:
        for f in REQ:
            if f not in m:
                errs.append(_e("manifest_missing_field", f"missing {f}"))
    for f in (
        "schema_version",
        "question_key",
        "title",
        "version",
        "review_status",
        "network_file",
    ):
        if f in m and not _nes(m.get(f)):
            errs.append(_e("manifest_missing_field", f"bad {f}"))
    if "network_hash" in m and not _nes(m.get("network_hash")):
        errs.append(_e("manifest_missing_field", "bad network_hash"))
    for f in ("prompt_version", "template_version"):
        if f in m and not _nes(m.get(f)):
            errs.append(_e("manifest_missing_field", f"bad {f}"))
    if "reviewed_result_mapping" in m:
        rrm = m.get("reviewed_result_mapping")
        if isinstance(rrm, str):
            if rrm.strip() == "":
                errs.append(_e("manifest_missing_field", "bad mapping"))
        elif isinstance(rrm, dict):
            if not rrm:
                errs.append(_e("manifest_missing_field", "bad mapping"))
        else:
            errs.append(_e("manifest_missing_field", "bad mapping"))
    for f in ("context_output_resource_limits", "engine_configuration"):
        if f in m and not isinstance(m.get(f), dict):
            errs.append(_e("manifest_missing_field", f"bad {f}"))
    if "review" in m and not isinstance(m.get("review"), dict):
        errs.append(_e("manifest_missing_field", "bad review"))
    if "workflow" in m and m.get("workflow") not in WFLOWS:
        errs.append(_e("workflow_invalid", "bad workflow"))
    if isinstance(review, dict) and isinstance(m.get("question_key"), str):
        rk = review.get("question_key")
        if isinstance(rk, str) and rk != m["question_key"]:
            errs.append(_e("question_key_mismatch", "bad key"))
    if "network_hash" in m:
        raw = m.get("network_hash")
        sha = validated.get("source_sha256") if isinstance(validated, dict) else None
        if not isinstance(raw, str) or raw.strip() == "":
            errs.append(_e("network_hash_mismatch", "bad hash"))
        elif not isinstance(sha, str) or sha == "":
            errs.append(_e("network_hash_mismatch", "bad sha"))
        elif _norm(raw) != sha.strip():
            errs.append(_e("network_hash_mismatch", "hash mismatch"))
    declared: list[str] = []
    if "declared_node_order" in m:
        od = m.get("declared_node_order")
        nodes = validated.get("nodes") if isinstance(validated, dict) else None
        if (
            not isinstance(od, list)
            or not od
            or any(not isinstance(n, str) or n == "" for n in od)
            or len(set(od)) != len(od)
        ):
            errs.append(_e("declared_node_order_mismatch", "bad order"))
        elif not isinstance(nodes, list) or list(nodes) != list(od):
            errs.append(_e("declared_node_order_mismatch", "order mismatch"))
        else:
            declared = list(od)
    st = _states(validated)
    pb = _parents(validated)
    vars_ok: list[dict[str, Any]] = []
    if "variables" in m:
        vs = m.get("variables")
        if not isinstance(vs, list) or not vs:
            errs.append(_e("variable_mismatch", "bad variables"))
        else:
            ids = [x.get("node_id") if isinstance(x, dict) else None for x in vs]
            if declared and ids != list(declared):
                errs.append(_e("variable_mismatch", "bad ids"))
            else:
                bad = False
                for x in vs:
                    if not isinstance(x, dict):
                        bad = True
                        break
                    nid = x.get("node_id")
                    kind = x.get("xmlbif_kind")
                    vt = x.get("patient_value_type")
                    s = x.get("states")
                    op = x.get("ordered_parents")
                    if not isinstance(nid, str) or nid == "":
                        bad = True
                        break
                    if kind in ("decision", "utility"):
                        errs.append(_e("unsupported_kind", f"bad kind {nid}"))
                        bad = True
                        vs = []
                        break
                    if kind != "nature" or vt not in VTYPES:
                        bad = True
                        break
                    if (
                        not isinstance(s, list)
                        or not s
                        or any(not isinstance(i, str) or i == "" for i in s)
                        or len(set(s)) != len(s)
                    ):
                        bad = True
                        break
                    if st.get(str(nid)) is None or list(s) != list(st[str(nid)]):
                        bad = True
                        break
                    if not isinstance(op, list):
                        bad = True
                        break
                    if any(not isinstance(i, str) for i in op):
                        bad = True
                        break
                    exp = pb.get(str(nid))
                    if exp is None:
                        if list(op) != []:
                            bad = True
                            break
                    elif list(op) != list(exp):
                        bad = True
                        break
                if bad and not any(e["code"] == "unsupported_kind" for e in errs):
                    errs.append(_e("variable_mismatch", "bad variable"))
                if not bad:
                    vars_ok = [x for x in vs if isinstance(x, dict)]
    if "patient_mappings" in m:
        pm = m.get("patient_mappings")
        if not isinstance(pm, list) or not pm:
            errs.append(_e("missing_patient_mapping", "bad mappings"))
        else:
            ALLOWED_PREFIXES = (
                "encounters.",
                "encounter.",
                "content/history/",
                "content/assessments/",
                "docs/medical-docs/",
                "BNs/",
                "content/",
            )
            ds = set(declared)
            s_bad = False
            u_bad = False
            chained_bad = False
            note_bad = False
            unknown_bad = False
            cnt: dict[str, int] = {}
            for it in pm:
                if not isinstance(it, dict):
                    s_bad = True
                    continue
                nid = it.get("node_id")
                paths = it.get("allowed_source_paths")
                applic = _is_applicability(nid)
                if applic:
                    # Applicability inputs are linkage descriptors, not
                    # network evidence: exempt from node-membership,
                    # source-path, and coverage counting checks.
                    pass
                else:
                    if not isinstance(nid, str) or nid not in ds:
                        s_bad = True
                if not isinstance(paths, list) or not paths:
                    s_bad = True
                elif not applic:
                    if any(not isinstance(p, str) or p == "" for p in paths):
                        s_bad = True
                    for p in paths:
                        if not isinstance(p, str) or p == "":
                            continue
                        lowered = p.lower()
                        if (
                            lowered.startswith("questions.")
                            or lowered.startswith("questions/")
                            or "posterior" in lowered
                        ):
                            chained_bad = True
                        elif "notes" in lowered:
                            note_bad = True
                        elif not (
                            p.startswith(ALLOWED_PREFIXES)
                            or p.startswith(RUNS_REPORT_PREFIX)
                        ):
                            unknown_bad = True
                if not _nes(it.get("typed_transform")):
                    s_bad = True
                if not _nes(it.get("time_window")):
                    s_bad = True
                if not _nes(it.get("missing_policy")):
                    s_bad = True
                if not _usage_ok(it.get("usage")):
                    u_bad = True
                if isinstance(nid, str) and not applic:
                    cnt[nid] = cnt.get(nid, 0) + 1
            roots = [
                str(x.get("node_id")) for x in vars_ok if x.get("ordered_parents") == []
            ]
            c_bad = False
            if vars_ok:
                for r in roots:
                    if cnt.get(r, 0) != 1:
                        c_bad = True
                rs = set(roots)
                for k, c in cnt.items():
                    if k not in rs and c > 0:
                        c_bad = True
            if s_bad or c_bad:
                errs.append(_e("missing_patient_mapping", "bad coverage"))
            if u_bad:
                errs.append(_e("invalid_usage", "bad usage"))
            if chained_bad:
                errs.append(_e("chained_result", "chained posterior result"))
            if note_bad:
                errs.append(_e("note_source_path", "note source path"))
            if unknown_bad:
                errs.append(_e("unknown_source_path", "unknown source path"))
            has_both = any(
                isinstance(it, dict) and _usage_is_both(it.get("usage")) for it in pm
            )
            if has_both:
                r1 = (
                    review.get("double_counting_rationale")
                    if isinstance(review, dict)
                    else None
                )
                gd = review.get("graph_decision") if isinstance(review, dict) else None
                r2 = (
                    gd.get("double_counting_rationale_for_review")
                    if isinstance(gd, dict)
                    else None
                )
                r3 = (
                    gd.get("double_counting_rationale")
                    if isinstance(gd, dict)
                    else None
                )
                if not (_nes(r1) or _nes(r2) or _nes(r3)):
                    errs.append(
                        _e(
                            "double_use_without_rationale",
                            "both usage needs rationale",
                        )
                    )
    if "applicability" in m:
        ap = m.get("applicability")
        if not isinstance(ap, dict):
            errs.append(_e("unknown_policy_missing", "bad applicability"))
        else:
            ex = ap.get("expression")
            if not _nes(ex):
                errs.append(_e("unsafe_expression", "bad expression"))
            elif isinstance(ex, str):
                lw = ex.lower()
                bad_token = False
                for tk in (
                    "__",
                    "import",
                    "eval",
                    "exec",
                    ";",
                    "notes",
                    "posterior",
                    "questions",
                ):
                    if tk in lw:
                        errs.append(_e("unsafe_expression", "bad token"))
                        bad_token = True
                        break
                if not bad_token:
                    depth = 0
                    balanced = True
                    for char in ex:
                        if char == "(":
                            depth += 1
                        elif char == ")":
                            depth -= 1
                            if depth < 0:
                                balanced = False
                                break
                    if depth != 0:
                        balanced = False
                    if not balanced:
                        errs.append(_e("unsafe_expression", "bad parens"))
                    else:
                        bad_case = False
                        for mm in re.finditer(r"\b(and|or)\b", ex, flags=re.IGNORECASE):
                            if mm.group(0) not in ("AND", "OR"):
                                bad_case = True
                                break
                        if bad_case:
                            errs.append(_e("unsafe_expression", "bad conjunction"))
                        else:
                            no_paren = ex.replace("(", " ").replace(")", " ")
                            parts = re.split(r"\s+AND\s+|\s+OR\s+", no_paren)
                            clause_re = re.compile(
                                r"^\s*(encounter\.kind|[A-Za-z_][A-Za-z0-9_.]*)\s*==\s*'[^']*'\s*$"
                            )
                            ok = True
                            for part in parts:
                                mm2 = clause_re.match(part)
                                if not mm2:
                                    ok = False
                                    break
                                if mm2.group(1) in ("AND", "OR"):
                                    ok = False
                                    break
                            if not ok:
                                errs.append(_e("unsafe_expression", "bad clause"))
            rq = ap.get("required_fields")
            if not isinstance(rq, list) or not rq:
                errs.append(_e("manifest_missing_field", "bad fields"))
            un = ap.get("unknown_policy")
            # needs_clarification is always required; not_applicable is only
            # required when the expression has a gate beyond encounter.kind
            # (i.e. contains AND/OR). Extra branches in the policy are allowed.
            if not _nes(un) or "needs_clarification" not in str(un):
                errs.append(_e("unknown_policy_missing", "bad policy"))
            elif _has_gate(ex) and "not_applicable" not in str(un):
                errs.append(_e("unknown_policy_missing", "bad policy"))
    if "cpt_contract" in m:
        cc = m.get("cpt_contract")
        if not isinstance(cc, dict) or cc.get("all_nodes_mandatory") is not True:
            errs.append(_e("incomplete_cpt_contract", "bad contract"))
        else:
            rows = cc.get("rows")
            if not isinstance(rows, list):
                errs.append(_e("incomplete_cpt_contract", "bad rows"))
            elif not declared or not vars_ok:
                errs.append(_e("incomplete_cpt_contract", "no order"))
            elif len(rows) != len(declared):
                errs.append(_e("incomplete_cpt_contract", "bad count"))
            else:
                vp: dict[str, list[str]] = {}
                for x in vars_ok:
                    nid = x.get("node_id")
                    op = x.get("ordered_parents")
                    if isinstance(nid, str) and isinstance(op, list):
                        vp[nid] = [p for p in op if isinstance(p, str)]
                ok = True
                for i, row in enumerate(rows):
                    if not isinstance(row, dict) or row.get("node_id") != declared[i]:
                        ok = False
                        break
                    par = row.get("parent_ids")
                    if not isinstance(par, list) or list(par) != vp.get(
                        declared[i], []
                    ):
                        ok = False
                        break
                    prod = 1
                    for pp in vp.get(declared[i], []):
                        cards = st.get(pp)
                        if cards is None:
                            for x in vars_ok:
                                if x.get("node_id") == pp:
                                    sv = x.get("states")
                                    if isinstance(sv, list):
                                        cards = [s for s in sv if isinstance(s, str)]
                                    break
                        if not cards:
                            ok = False
                            break
                        prod *= len(cards)
                    if not ok or row.get("row_count") != prod:
                        ok = False
                        break
                if not ok:
                    errs.append(_e("incomplete_cpt_contract", "bad row"))
    queries: list[str] = []
    if "query_nodes" in m:
        qn = m.get("query_nodes")
        if (
            not isinstance(qn, list)
            or not qn
            or any(not isinstance(n, str) or n == "" for n in qn)
            or any(n not in set(declared) for n in qn if isinstance(n, str))
        ):
            errs.append(_e("undeclared_query", "bad queries"))
        else:
            queries = [str(n) for n in qn]
    if "evidence_mappings" in m:
        ev = m.get("evidence_mappings")
        bad_ev = False
        if not isinstance(ev, list) or not ev:
            bad_ev = True
        else:
            for it in ev:
                if not isinstance(it, dict):
                    bad_ev = True
                    break
                if not isinstance(it.get("node_id"), str) or it["node_id"] not in set(
                    declared
                ):
                    bad_ev = True
                    break
                if not _nes(it.get("evidence")):
                    bad_ev = True
                    break
        if bad_ev:
            errs.append(_e("missing_evidence_mapping", "bad evidence"))
    if "impossible_evidence_policy" in m:
        pol = m.get("impossible_evidence_policy")
        if not isinstance(pol, str) or "fail" not in pol.lower():
            errs.append(_e("impossible_evidence_policy_missing", "bad policy"))
    if "likelihood_evidence" in m and m.get("likelihood_evidence") != "disabled":
        errs.append(_e("likelihood_not_disabled", "bad likelihood"))
    if not isinstance(prompt_text, str) or prompt_text.strip() == "":
        errs.append(_e("prompt_missing", "bad prompt"))
    elif (
        "CPT" not in prompt_text
        or "percentages" not in prompt_text
        or "do not" not in prompt_text.lower()
        or "plan" not in prompt_text
        or "choose applicability" not in prompt_text
        or "patient facts" not in prompt_text
    ):
        errs.append(_e("prompt_forbidden", "bad prompt content"))
    if not isinstance(template, dict):
        errs.append(_e("template_missing", "bad template"))
    else:
        br = template.get("branches")
        if not isinstance(br, dict):
            errs.append(_e("template_missing", "bad branches"))
        else:
            # needs_clarification is always required; a false-gate branch is
            # only required when the applicability expression has a gate
            # (contains AND/OR). needs_clarification/not_applicable extras
            # beyond the requirement are allowed.
            _ap = m.get("applicability")
            _ex = _ap.get("expression") if isinstance(_ap, dict) else None
            if "needs_clarification" not in br:
                errs.append(_e("missing_branch", "bad branches"))
            elif _has_gate(_ex) and not any(k in FALSE_GATE_BRANCHES for k in br):
                errs.append(_e("missing_branch", "bad branches"))
            ug = None
            for _dk in (
                "deterministic_urgent_flag",
                "deterministic_caution_pointer",
                "deterministic_pointers",
            ):
                _cand = template.get(_dk)
                if isinstance(_cand, dict):
                    ug = _cand
                    break
            _conds = (
                ug.get("conditions")
                if isinstance(ug, dict) and isinstance(ug.get("conditions"), list)
                else (ug.get("pointers") if isinstance(ug, dict) else None)
            )
            _rule = ug.get("rule") if isinstance(ug, dict) else None
            if (
                not isinstance(ug, dict)
                or not isinstance(_conds, list)
                or not _conds
                or not _nes(ug.get("otherwise"))
                or (
                    _rule is not None
                    and (
                        not isinstance(_rule, str)
                        or "without waiting" not in _rule.lower()
                    )
                )
            ):
                errs.append(_e("template_missing", "bad flag"))
            mr = template.get("mapping_rule")
            _mr_low = mr.lower() if isinstance(mr, str) else ""
            if (
                not isinstance(mr, str)
                or "review" not in _mr_low
                or NOT_NEVER_RE.search(mr) is None
                or not any(
                    kw in _mr_low
                    for kw in (
                        "recommend",
                        "selected",
                        "selects",
                        "selection",
                        "presented",
                        "prescription",
                        "disposition",
                        "treatment rule",
                        "treatment recommendation",
                    )
                )
            ):
                errs.append(_e("template_missing", "bad rule"))
            sl = template.get("slots")
            if (
                not isinstance(sl, list)
                or not sl
                or any(not isinstance(s, str) or s == "" for s in sl)
            ):
                errs.append(_e("template_missing", "bad slots"))
                sl = []
            sset = set(s for s in sl if isinstance(s, str))
            try:
                blob = json.dumps(template, sort_keys=True)
            except (TypeError, ValueError):
                blob = str(template)
            low = blob.lower()
            hit = False
            for tk in ("${", "{%", "eval(", "exec(", "__"):
                hay = low if tk not in ("${", "{%", "__") else blob
                if tk in hay:
                    errs.append(_e("unsupported_operator", "bad op"))
                    hit = True
                    break
            if not hit and "import " in low:
                errs.append(_e("unsupported_operator", "bad op"))
            for k, b in br.items():
                if not isinstance(b, dict):
                    # Exempt display-only branches (unknown_disclosure,
                    # context_note) may carry plain string content.
                    if isinstance(k, str) and k in EXEMPT:
                        continue
                    errs.append(_e("template_missing", "bad branch"))
                    continue
                for fd in ("heading", "body"):
                    vv = b.get(fd)
                    if isinstance(vv, str):
                        for sname in SLOT_RE.findall(vv):
                            if sname in sset:
                                continue
                            if sname in br or sname in template:
                                continue
                            if sname.startswith("p_") or sname.endswith("_table"):
                                continue
                            if sname in SLOT_ALLOWLIST:
                                continue
                            errs.append(_e("undeclared_template_state", "bad slot"))
            allow: set[str] = set()
            for q in queries:
                for sname in st.get(q, []):
                    allow.add(sname)
            for k, b in br.items():
                if not isinstance(k, str) or k in EXEMPT:
                    continue
                ps = b.get("posterior_state") if isinstance(b, dict) else None
                # A single-token posterior_state is a state reference and
                # must name a declared query state, even when the branch
                # key itself is valid.
                if (
                    isinstance(ps, str)
                    and SINGLE_TOKEN_RE.match(ps)
                    and ps not in allow
                ):
                    errs.append(_e("undeclared_template_state", "bad branch"))
                    continue
                if k in allow:
                    continue
                if isinstance(ps, str) and ps in allow:
                    continue
                # Descriptive distribution sentences (contain spaces, not a
                # single state token) are review copy, not state references.
                if isinstance(ps, str) and not SINGLE_TOKEN_RE.match(ps):
                    continue
                errs.append(_e("undeclared_template_state", "bad branch"))
    if not isinstance(review, dict):
        errs.append(_e("review_incomplete", "bad review"))
    else:
        probs: list[str] = []
        if not _nes(review.get("package_version")):
            probs.append("package_version")
        rk = review.get("question_key")
        mk = m.get("question_key")
        qk_ok = False
        if _nes(rk) and isinstance(mk, str) and rk == mk:
            qk_ok = True
        elif not _nes(rk):
            pv_r = review.get("package_version")
            if (
                _nes(pv_r)
                and isinstance(mk, str)
                and mk != ""
                and str(pv_r).startswith(mk)
            ):
                qk_ok = True
        if not qk_ok:
            probs.append("question_key")
        rw = review.get("workflow")
        if not _nes(rw):
            probs.append("workflow")
        elif isinstance(m.get("workflow"), str) and rw != m["workflow"]:
            probs.append("workflow")
        if not _nes(review.get("reviewer")):
            probs.append("reviewer")
        dec_ok = _nes(review.get("decision"))
        if not dec_ok:
            mrev = m.get("review")
            if isinstance(mrev, dict) and _nes(mrev.get("decision")):
                dec_ok = True
        if not dec_ok:
            probs.append("decision")
        if not (_nes(review.get("date")) or _nes(review.get("review_date"))):
            probs.append("date")
        srcs = review.get("sources")
        if not isinstance(srcs, list) or not srcs:
            probs.append("sources")
        else:
            for sitem in srcs:
                if not isinstance(sitem, dict):
                    probs.append("sources")
                    break
                if not _nes(sitem.get("path")):
                    probs.append("sources")
                    break
                if not isinstance(sitem.get("bytes"), int):
                    probs.append("sources")
                    break
                if not _nes(sitem.get("sha256")):
                    probs.append("sources")
                    break
                loc = sitem.get("locators")
                if not isinstance(loc, list) or not loc:
                    probs.append("sources")
                    break
        qe = review.get("question_enumeration")
        if not (isinstance(qe, dict) and _nes(qe.get("specific_question"))):
            probs.append("question_enumeration")
        oq = review.get("owner_questions")
        if not (isinstance(oq, list) and len(oq) > 0):
            probs.append("owner_questions")
        scl = review.get("source_classification")
        if isinstance(scl, str):
            if scl.strip() == "":
                probs.append("source_classification")
        elif isinstance(scl, dict):
            if not scl:
                probs.append("source_classification")
        else:
            probs.append("source_classification")
        sc = review.get("source_comparison")
        if isinstance(sc, str):
            if sc.strip() == "":
                probs.append("source_comparison")
        elif isinstance(sc, dict):
            if not sc:
                probs.append("source_comparison")
        else:
            probs.append("source_comparison")
        gd = review.get("graph_decision")
        if (
            not isinstance(gd, dict)
            or not isinstance(gd.get("nodes"), list)
            or not gd["nodes"]
            or "edges" not in gd
            or not _nes(gd.get("why_this_shape"))
        ):
            probs.append("graph_decision")
        rp = review.get("reference_table_provenance")
        if isinstance(rp, str):
            if rp.strip() == "":
                probs.append("reference_table_provenance")
        elif isinstance(rp, dict):
            if not rp:
                probs.append("reference_table_provenance")
        else:
            probs.append("reference_table_provenance")
        am = review.get("admission_measurements")
        if (
            not isinstance(am, dict)
            or "xml_bytes" not in am
            or "nodes" not in am
            or "cpt_cells" not in am
        ):
            probs.append("admission_measurements")
        if not isinstance(review.get("unresolved_assumptions"), (list, str)):
            probs.append("unresolved_assumptions")
        iep = review.get("independent_examples_provenance")
        if isinstance(iep, str):
            if iep.strip() == "":
                probs.append("independent_examples_provenance")
        elif isinstance(iep, dict):
            if not iep:
                probs.append("independent_examples_provenance")
        else:
            probs.append("independent_examples_provenance")
        if probs:
            errs.append(
                _e("review_incomplete", "review: " + ",".join(sorted(set(probs))))
            )
    if not isinstance(examples, dict):
        errs.append(_e("examples_incomplete", "bad examples"))
    else:
        xprob: list[str] = []
        if not _nes(examples.get("package_version")):
            xprob.append("package_version")
        cases = examples.get("clinical_cases")
        if not isinstance(cases, list) or not cases:
            xprob.append("clinical_cases")
        else:
            for citem in cases:
                if not isinstance(citem, dict):
                    xprob.append("clinical_cases")
                    break
                if not _nes(citem.get("name")):
                    xprob.append("clinical_cases")
                    break
                if not _nes(citem.get("kind")) and citem.get("inputs") is None:
                    xprob.append("clinical_cases")
                    break
        fx = examples.get("numerical_fixture")
        if not isinstance(fx, dict):
            xprob.append("numerical_fixture")
        else:
            pv = fx.get("provenance")
            ch = fx.get("checks")
            pok = _nes(pv) or (isinstance(pv, dict) and bool(pv))
            if not pok or not isinstance(ch, list) or not ch:
                xprob.append("numerical_fixture")
            else:
                for citem in ch:
                    if not isinstance(citem, dict):
                        xprob.append("numerical_fixture")
                        break
                    # Nameless transpose/asymmetry detectors carry their work
                    # plus row_a/row_b (or row_c/row_d) instead of a name.
                    _named = _nes(citem.get("name"))
                    _has_ab = (
                        citem.get("row_a") is not None
                        and citem.get("row_b") is not None
                    )
                    _has_cd = (
                        citem.get("row_c") is not None
                        and citem.get("row_d") is not None
                    )
                    if not _named and not (_has_ab or _has_cd):
                        xprob.append("numerical_fixture")
                        break
                    if not _nes(citem.get("work")):
                        xprob.append("numerical_fixture")
                        break
        if xprob:
            errs.append(
                _e("examples_incomplete", "ex: " + ",".join(sorted(set(xprob))))
            )
    if "numerical_tolerances" in m:
        tls = m.get("numerical_tolerances")
        if not isinstance(tls, dict):
            errs.append(_e("manifest_missing_field", "bad tolerances"))
        else:
            for k, w in TOLS.items():
                vv = tls.get(k)
                if not isinstance(vv, (int, float)) or float(vv) != float(w):
                    errs.append(_e("manifest_missing_field", f"bad {k}"))
                    break
    errs.sort(key=lambda d: d["code"])
    return {"valid": errs == [], "errors": errs}


def load_package(
    package_dir: str | Path,
) -> tuple[
    dict[str, Any], dict[str, Any], str, dict[str, Any], dict[str, Any], dict[str, Any]
]:
    """Load package files from a directory."""
    base = Path(package_dir)
    m: dict[str, Any] = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    data = (base / "network.xml").read_bytes()
    v = validate_xmlbif(data)
    p = (base / "prompt.txt").read_text(encoding="utf-8")
    t: dict[str, Any] = json.loads((base / "template.json").read_text(encoding="utf-8"))
    r: dict[str, Any] = json.loads((base / "review.json").read_text(encoding="utf-8"))
    x: dict[str, Any] = json.loads((base / "examples.json").read_text(encoding="utf-8"))
    return (m, v, p, t, r, x)
