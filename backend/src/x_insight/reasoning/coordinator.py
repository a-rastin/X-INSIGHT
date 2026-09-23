"""Single-question coordinator (S45 slice 1: T1/T8 end to end, T5-T7 inside).

One entry point used by :mod:`x_insight.reasoning.worker` after
:func:`x_insight.reasoning.queue.claim_next_job` has claimed the job:
:func:`execute_claimed_question` runs the claimed question outside the claim
transaction through the real MCP stdio transport, the controlled provider
endpoint, all-CPT validation, the run-local effective artifact, exact
inference, and a locally rendered template section persisted before the
fenced job commit. Synthetic fixtures only; never BNs/ as oracle.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from lxml import etree  # type: ignore[import-untyped]
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from sqlalchemy import text

from x_insight import db
from x_insight.models.inference import (
    ENGINE_PIN,
    build_effective_artifact,
    infer,
    validate_cpt_response,
)
from x_insight.models.validation import validate_xmlbif
from x_insight.reasoning import queue as queue_module
from x_insight.reasoning.mcp_host import build_scoped_server_params, stop_and_revoke
from x_insight.reasoning.provider import TOOL_NAME, ProviderError, estimate_cpts
from x_insight.reasoning.provider_config import decrypt_api_key

_GRANT_TTL = timedelta(minutes=10)
_MCP_CALL_TIMEOUT_S = 60.0


class CoordinatorError(Exception):
    """A claimed question could not be completed (fencing, config, content)."""


def _scoped_projection(
    entry: dict[str, Any], projection: dict[str, Any], projection_hash: str
) -> dict[str, Any]:
    """Return the MCP-shaped scoped projection (variables only, no facts)."""
    variables = projection.get("variables")
    return {
        "question_key": str(entry.get("question_key")),
        "network_version": entry.get("version"),
        "projection_hash": projection_hash,
        "variables": list(variables) if isinstance(variables, list) else [],
    }


def _tool_declaration() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": TOOL_NAME,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        }
    ]


def _network_contract(
    entry: dict[str, Any], validated: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    nodes = [str(n) for n in validated["nodes"]]
    states = {str(k): [str(s) for s in v] for k, v in validated["states"].items()}
    parents: dict[str, list[str]] = {node: [] for node in nodes}
    edges: list[list[str]] = []
    for parent, child in validated.get("edges", []):
        p, c = str(parent), str(child)
        edges.append([p, c])
        if c in parents and p not in parents[c]:
            parents[c].append(p)
    network_contract = {
        "question_key": str(entry.get("question_key")),
        "network_version": entry.get("version"),
        "network_hash": validated["source_sha256"],
        "nodes": nodes,
        "edges": edges,
        "states": states,
        "parents": parents,
    }
    cpt_contract = {"all_nodes_mandatory": True, "nodes": list(nodes)}
    return network_contract, cpt_contract


def _pinned_query(entry: dict[str, Any], validated: dict[str, Any]) -> dict[str, Any]:
    """Return the pinned query, defaulting to the last-node marginal.

    The S45 synthetic bundle carries no explicit query; the deterministic
    fallback asks the marginal of the last network node in validated order
    for its last state with empty evidence (synthetic A->B yields P(B=yes)).
    A bundle-carried ``query`` {target, state, evidence} wins when present.
    """
    raw = entry.get("query")
    if isinstance(raw, dict) and isinstance(raw.get("target"), str):
        evidence = raw.get("evidence")
        return {
            "target": str(raw["target"]),
            "state": str(raw.get("state")),
            "evidence": dict(evidence) if isinstance(evidence, dict) else {},
        }
    nodes = [str(n) for n in validated["nodes"]]
    target = nodes[-1]
    return {
        "target": target,
        "state": str(validated["states"][target][-1]),
        "evidence": {},
    }


def render_section(
    template: Any,
    question_key: str,
    network_version: Any,
    accepted: dict[str, Any],
    query: dict[str, Any],
    posterior: float,
) -> tuple[str, str]:
    """Render a deterministic section from stored result + accepted CPTs only.

    Never LLM prose: every token derives from the pinned template mapping
    and the stored inference result. Returns (text, template_version).
    """
    version = "synthetic-v1"
    if isinstance(template, dict) and isinstance(template.get("template_version"), str):
        version = str(template["template_version"])
    parts: list[str] = []
    for table in accepted.get("tables", []):
        if not isinstance(table, dict):
            continue
        node = str(table.get("node_id"))
        for row in table.get("rows", []):
            if not isinstance(row, dict):
                continue
            given = "/".join(str(s) for s in row.get("parent_states", []))
            pct = ",".join(str(v) for v in row.get("percentages", []))
            parts.append(f"{node}|{given}={pct}")
    evidence = query.get("evidence") or {}
    evidence_text = json.dumps(evidence, sort_keys=True)
    text_out = (
        f"[{question_key} {network_version} template {version}] "
        f"P({query.get('target')}={query.get('state')}|{evidence_text})"
        f"={posterior:.9f}. CPTs: {'; '.join(parts)}."
    )
    # S46 slice 4: one combined LAI step renders both branch outputs under
    # its mapping. Append sorted branch keys plus the deterministic
    # branches JSON (stored template only, never LLM prose) so both
    # indication+choice markers are present alongside CPTs/posterior.
    if isinstance(template, dict):
        branches = template.get("branches")
        if isinstance(branches, dict) and branches:
            keys = sorted(str(k) for k in branches)
            text_out += (
                f" branches:{','.join(keys)} "
                f"{json.dumps(branches, sort_keys=True, default=str)}."
            )
    return text_out, version


def _load_claim_context(
    claim: dict[str, Any], database_url: str | None
) -> dict[str, Any]:
    with db.transaction(database_url) as conn:
        run = (
            conn.execute(
                text("SELECT * FROM runs WHERE id = :id"),
                {"id": str(claim["run_id"])},
            )
            .mappings()
            .first()
        )
        if run is None:
            raise CoordinatorError("Run not found for claimed job.")
        question = (
            conn.execute(
                text(
                    "SELECT * FROM run_questions WHERE run_id = :run_id "
                    "AND question_key = :question_key"
                ),
                {
                    "run_id": str(claim["run_id"]),
                    "question_key": str(claim["question_key"]),
                },
            )
            .mappings()
            .first()
        )
        if question is None:
            raise CoordinatorError("Run question not found for claimed job.")
        job = (
            conn.execute(
                text("SELECT attempt_count FROM reasoning_jobs WHERE id = :id"),
                {"id": str(claim["job_id"])},
            )
            .mappings()
            .first()
        )
        return {
            "run": dict(run),
            "question": dict(question),
            "attempt_count": int(job["attempt_count"] or 0) if job else 0,
        }


def _resolve_provider(database_url: str | None) -> dict[str, Any]:
    """Resolve base_url/api_key/model from the active provider revision.

    Falls back only to the seeded active config row; never a hardcoded live
    default. The key stays in memory and never enters stored provenance.
    """
    with db.transaction(database_url) as conn:
        pointer = (
            conn.execute(text("SELECT * FROM provider_config_pointer WHERE id = 1"))
            .mappings()
            .first()
        )
        if pointer is None or pointer["active_config_id"] is None:
            raise CoordinatorError("No active provider configuration.")
        row = (
            conn.execute(
                text("SELECT * FROM provider_configs WHERE id = :id"),
                {"id": pointer["active_config_id"]},
            )
            .mappings()
            .first()
        )
        if row is None or not row["base_url"] or not row["key_ciphertext"]:
            raise CoordinatorError("No active provider configuration.")
        try:
            api_key = decrypt_api_key(str(row["key_ciphertext"]))
        except ValueError as exc:
            raise CoordinatorError("Stored provider key is unreadable.") from exc
        return {
            "base_url": str(row["base_url"]),
            "model": str(row["model"]),
            "revision": int(row["revision"]),
            "api_key": api_key,
        }


def _insert_grant(
    grant: str,
    run: dict[str, Any],
    question_id: Any,
    question_key: str,
    projection_hash: str,
    claim: dict[str, Any],
    database_url: str | None,
) -> None:
    with db.transaction(database_url) as conn:
        conn.execute(
            text(
                "INSERT INTO mcp_question_grants (grant_token, run_id, "
                "run_question_id, question_key, actor_id, encounter_id, "
                "snapshot_hash, projection_hash, lease_token, "
                "deployment_generation, expires_at, revoked_at) "
                "VALUES (:grant, :run_id, :question_id, :question_key, "
                ":actor_id, :encounter_id, :snapshot_hash, :projection_hash, "
                ":lease_token, :deployment, :expires_at, NULL)"
            ),
            {
                "grant": grant,
                "run_id": str(run["id"]),
                "question_id": str(question_id),
                "question_key": question_key,
                "actor_id": str(run["author_id"]) if run["author_id"] else None,
                "encounter_id": str(run["encounter_id"]),
                "snapshot_hash": run["snapshot_hash"],
                "projection_hash": projection_hash,
                "lease_token": str(claim["lease_token"]),
                "deployment": int(claim.get("deployment_generation") or 1),
                "expires_at": datetime.now(UTC) + _GRANT_TTL,
            },
        )


def _payload_from_mcp_result(result: Any) -> dict[str, Any]:
    is_err = getattr(result, "is_error", False) or getattr(result, "isError", False)
    if is_err:
        raise ProviderError("grant_denied", "MCP grant denied.", False)
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    if len(texts) != 1:
        raise ProviderError("invalid_cpt", "Bridge returned an unexpected shape.", True)
    payload: dict[str, Any] = json.loads(texts[0])
    return payload


async def _estimate_via_mcp(
    grant: str, request: dict[str, Any], database_url: str | None
) -> dict[str, Any]:
    """Run one estimation attempt over a single real MCP stdio subprocess."""
    params = build_scoped_server_params(grant)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            loop = asyncio.get_running_loop()

            def bridge(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
                if name != TOOL_NAME or args != {}:
                    raise ProviderError("tool_rejected", "Disallowed tool call.", False)
                future = asyncio.run_coroutine_threadsafe(
                    session.call_tool(name, {}), loop
                )
                payload = _payload_from_mcp_result(
                    future.result(timeout=_MCP_CALL_TIMEOUT_S)
                )
                return {"call_id": call_id, "result": payload}

            candidate: dict[str, Any] = await loop.run_in_executor(
                None, lambda: estimate_cpts(request, bridge)
            )
            return candidate


def _stored_success(
    run_id: str, question_key: str, database_url: str | None
) -> dict[str, Any] | None:
    """Return the succeeded artifact row, if one is already stored.

    Crash-resume guard: a re-claimed question with a stored success must
    not issue a new provider POST; the caller recommits idempotently.
    """
    with db.transaction(database_url) as conn:
        row = (
            conn.execute(
                text(
                    "SELECT result FROM run_question_artifacts "
                    "WHERE run_id = :run_id AND question_key = :question_key "
                    "AND status = 'succeeded'"
                ),
                {"run_id": run_id, "question_key": question_key},
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None


def _run_local_effective(
    artifact: dict[str, Any], question_key: str, run_id: str
) -> tuple[bytes, str]:
    """Return run-local (effective bytes, sha256) distinct from base bytes.

    Appends a deterministic XML comment binding the bytes to this run's
    question. Comments carry no XMLBIF semantics and inference reads only
    tables, never XML; the marker guarantees effective_hash differs from
    the pinned base hash even when percentages coincide with base values.
    The pinned base bytes are never touched.
    """
    raw = bytes(artifact["effective_xml"])
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        recover=False,
    )
    root = etree.fromstring(raw, parser)
    root.append(etree.Comment(f"x-insight effective {question_key} run {run_id}"))
    data = bytes(etree.tostring(root, encoding="utf-8"))
    return data, hashlib.sha256(data).hexdigest()


def _verify_artifact_for_commit(
    run_id: str, question_key: str, database_url: str | None
) -> None:
    """Refuse success when any persisted provenance reference is missing.

    Crash checkpoint: success must never commit without model identity,
    attempt reference, effective hash, query, posterior result, and the
    rendered section already stored.
    """
    with db.transaction(database_url) as conn:
        row = (
            conn.execute(
                text(
                    "SELECT model, accepted, effective_xml, effective_hash, "
                    "query, result, rendered_section "
                    "FROM run_question_artifacts "
                    "WHERE run_id = :run_id AND question_key = :question_key"
                ),
                {"run_id": run_id, "question_key": question_key},
            )
            .mappings()
            .first()
        )
    incomplete = "Question artifact references are incomplete; refusing success."
    if row is None:
        raise CoordinatorError(incomplete)
    model = row["model"]
    accepted = row["accepted"]
    query = row["query"]
    result = row["result"]
    if not isinstance(model, dict):
        raise CoordinatorError(incomplete)
    if not isinstance(model.get("model"), str) or not model["model"]:
        raise CoordinatorError(incomplete)
    if not isinstance(model.get("provider_revision"), int):
        raise CoordinatorError(incomplete)
    if not isinstance(model.get("attempt_index"), int) or model["attempt_index"] < 1:
        raise CoordinatorError(incomplete)
    if not isinstance(accepted, dict):
        raise CoordinatorError(incomplete)
    tables = accepted.get("tables")
    if not isinstance(tables, list) or not tables:
        raise CoordinatorError(incomplete)
    effective_hash = row["effective_hash"]
    if (
        not isinstance(effective_hash, str)
        or len(effective_hash) != 64
        or any(c not in "0123456789abcdef" for c in effective_hash)
    ):
        raise CoordinatorError(incomplete)
    if not isinstance(row["effective_xml"], str) or not row["effective_xml"]:
        raise CoordinatorError(incomplete)
    if not isinstance(query, dict):
        raise CoordinatorError(incomplete)
    if not isinstance(query.get("target"), str) or not isinstance(
        query.get("state"), str
    ):
        raise CoordinatorError(incomplete)
    if not isinstance(query.get("evidence"), dict):
        raise CoordinatorError(incomplete)
    if not isinstance(result, dict):
        raise CoordinatorError(incomplete)
    try:
        posterior = float(result["posterior"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CoordinatorError(incomplete) from exc
    if not math.isfinite(posterior):
        raise CoordinatorError(incomplete)
    if not isinstance(row["rendered_section"], str) or not row["rendered_section"]:
        raise CoordinatorError(incomplete)


def _persist_artifact(
    run_id: str,
    ordinal: int,
    question_key: str,
    body: dict[str, Any],
    projection: dict[str, Any],
    prompt: str,
    model_provenance: dict[str, Any],
    accepted: dict[str, Any],
    effective_xml: bytes,
    effective_hash: str,
    query: dict[str, Any],
    result: dict[str, Any],
    rendered: str,
    template_version: str,
    provenance: dict[str, Any],
    database_url: str | None,
) -> None:
    with db.transaction(database_url) as conn:
        conn.execute(
            text(
                "INSERT INTO run_question_artifacts (run_id, question_key, "
                "ordinal, stage, status, request, projection, prompt, model, "
                "accepted, effective_xml, effective_hash, query, result, "
                "rendered_section, template_version, provenance) "
                "VALUES (:run_id, :question_key, :ordinal, 'succeeded', "
                "'succeeded', CAST(:request AS jsonb), CAST(:projection AS jsonb), "
                ":prompt, CAST(:model AS jsonb), CAST(:accepted AS jsonb), "
                ":effective_xml, :effective_hash, CAST(:query AS jsonb), "
                "CAST(:result AS jsonb), :rendered_section, :template_version, "
                "CAST(:provenance AS jsonb)) "
                "ON CONFLICT (run_id, question_key) DO UPDATE SET "
                "ordinal = EXCLUDED.ordinal, stage = 'succeeded', "
                "status = 'succeeded', request = EXCLUDED.request, "
                "projection = EXCLUDED.projection, prompt = EXCLUDED.prompt, "
                "model = EXCLUDED.model, accepted = EXCLUDED.accepted, "
                "effective_xml = EXCLUDED.effective_xml, "
                "effective_hash = EXCLUDED.effective_hash, query = EXCLUDED.query, "
                "result = EXCLUDED.result, "
                "rendered_section = EXCLUDED.rendered_section, "
                "template_version = EXCLUDED.template_version, "
                "provenance = EXCLUDED.provenance, updated_at = now()"
            ),
            {
                "run_id": run_id,
                "question_key": question_key,
                "ordinal": ordinal,
                "request": json.dumps(body),
                "projection": json.dumps(projection),
                "prompt": prompt,
                "model": json.dumps(model_provenance),
                "accepted": json.dumps(accepted),
                "effective_xml": effective_xml.decode("utf-8"),
                "effective_hash": effective_hash,
                "query": json.dumps(query),
                "result": json.dumps(result),
                "rendered_section": rendered,
                "template_version": template_version,
                "provenance": json.dumps(provenance),
            },
        )


def _read_applicability(projection: Any) -> str:
    """Return persisted gate status, defaulting to ready (pre-gate rows)."""
    if isinstance(projection, dict):
        status = projection.get("applicability")
        if status in ("ready", "not_applicable", "needs_clarification"):
            return str(status)
    return "ready"


def _has_pending_clarification(q_rows: Any, succeeded: set[str]) -> bool:
    """True when any question needs clarification and has no success yet.

    A needs_clarification gate never produces an artifact, so any such
    projection blocks later ready work (S46 slice 2). Skipped
    not_applicable rows never block.
    """
    for item in q_rows:
        key = str(item["question_key"])
        if key in succeeded:
            continue
        if _read_applicability(item["projection"]) == "needs_clarification":
            return True
    return False


def _enqueue_next_ready(run_id: str, database_url: str | None) -> bool:
    """Enqueue the next ready question for one run (S46 slices 1-2).

    Next means the smallest ordinal whose persisted projection is ready,
    with no succeeded artifact yet and no existing job row for that
    question. not_applicable rows are skipped silently (no job, no call);
    any pending needs_clarification stops progression: no further jobs
    and the run becomes needs_clarification (terminal). At most one
    queued/claimed job per run is ever visible: refuse when any
    queued/claimed job already exists for the run.
    Returns True when a successor job was inserted.
    """
    with db.transaction(database_url) as conn:
        run = (
            conn.execute(
                text("SELECT encounter_id, author_id FROM runs WHERE id = :id"),
                {"id": run_id},
            )
            .mappings()
            .first()
        )
        if run is None:
            return False
        q_rows = (
            conn.execute(
                text(
                    "SELECT question_key, ordinal, projection FROM run_questions "
                    "WHERE run_id = :run_id ORDER BY ordinal, id"
                ),
                {"run_id": run_id},
            )
            .mappings()
            .all()
        )
        if not q_rows:
            return False
        art_rows = (
            conn.execute(
                text(
                    "SELECT question_key FROM run_question_artifacts "
                    "WHERE run_id = :run_id AND status = 'succeeded'"
                ),
                {"run_id": run_id},
            )
            .mappings()
            .all()
        )
        succeeded = {str(item["question_key"]) for item in art_rows}
        # S46 slice 2: required-unknown stops progression before any
        # later ready work. Terminal clarification, never success.
        if _has_pending_clarification(q_rows, succeeded):
            conn.execute(
                text(
                    "UPDATE runs SET status = 'needs_clarification', "
                    "updated_at = now() WHERE id = :id AND status NOT IN "
                    "('succeeded', 'failed', 'needs_clarification', "
                    "'stale', 'cancelled')"
                ),
                {"id": run_id},
            )
            return False
        job_rows = (
            conn.execute(
                text(
                    "SELECT question_key, status FROM reasoning_jobs "
                    "WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            )
            .mappings()
            .all()
        )
        for item in job_rows:
            if str(item["status"]) in ("queued", "claimed"):
                return False
        existing = {str(item["question_key"]) for item in job_rows}
        for item in q_rows:
            key = str(item["question_key"])
            if key in succeeded or key in existing:
                continue
            if _read_applicability(item["projection"]) != "ready":
                continue
            try:
                conn.execute(
                    text(
                        "INSERT INTO reasoning_jobs (run_id, encounter_id, "
                        "author_id, question_key, ordinal, stage, status) "
                        "VALUES (:run_id, :encounter_id, :author_id, "
                        ":question_key, :ordinal, 'preparing_question', "
                        "'queued')"
                    ),
                    {
                        "run_id": run_id,
                        "encounter_id": str(run["encounter_id"]),
                        "author_id": (
                            str(run["author_id"]) if run["author_id"] else None
                        ),
                        "question_key": key,
                        "ordinal": int(item["ordinal"]),
                    },
                )
            except Exception:
                return False
            return True
        return False


def execute_claimed_question(
    claim: dict[str, Any], database_url: str | None = None
) -> dict[str, Any]:
    """Execute one claimed job's question end to end; return a safe outcome.

    Raises on provider/config/content/fencing failure so the worker records
    an error attempt; never fabricates success. The returned outcome holds
    no secrets and is safe for the persisted attempt ledger.
    """
    job_id = str(claim["job_id"])
    run_id = str(claim["run_id"])
    question_key = str(claim["question_key"])

    context = _load_claim_context(claim, database_url)
    stored_success = _stored_success(run_id, question_key, database_url)
    if stored_success is not None:
        # Idempotent resume: a stored success recommits without a new
        # provider POST. Missing/invalid stored results never succeed.
        stored_result = stored_success.get("result")
        if not isinstance(stored_result, dict):
            raise CoordinatorError(
                "Stored question result is unreadable; refusing success."
            )
        try:
            resumed_posterior = float(stored_result["posterior"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CoordinatorError(
                "Stored question result is unreadable; refusing success."
            ) from exc
        if not math.isfinite(resumed_posterior):
            raise CoordinatorError(
                "Stored question result is unreadable; refusing success."
            )
        recommitted = queue_module.complete_job(
            job_id,
            str(claim["lease_token"]),
            {"ok": True, "resumed": True},
            database_url,
        )
        if recommitted is None:
            raise CoordinatorError(
                "Stale lease token, expired lease, or rotated deployment; "
                "the stored section was kept but the job was not committed."
            )
        # S46 slices 1-3: chain the next ready question instead of
        # succeeding. The proposal gate decides terminal status; keep the
        # run non-terminal here so sequential progression can continue.
        _enqueue_next_ready(run_id, database_url)
        try:
            from x_insight.reasoning.proposal import try_assemble_proposal

            try_assemble_proposal(run_id, database_url)
        except Exception:
            pass
        return {
            "ok": True,
            "question_key": question_key,
            "posterior": resumed_posterior,
            "resumed": True,
        }
    run = context["run"]
    stored = context["question"]
    projection = stored["projection"]
    if not isinstance(projection, dict):
        raise CoordinatorError("Stored projection is unavailable.")
    projection_hash = str(stored["projection_hash"])
    pins = run["pins"]
    if not isinstance(pins, dict):
        raise CoordinatorError("Run has no pinned bundle.")
    entry: dict[str, Any] | None = None
    questions = pins.get("questions")
    if isinstance(questions, list):
        for item in questions:
            if isinstance(item, dict) and item.get("question_key") == question_key:
                entry = dict(item)
                break
    if entry is None:
        raise CoordinatorError("Pinned bundle entry is missing.")
    network_xml = entry.get("network_xml")
    prompt = entry.get("prompt")
    if not isinstance(network_xml, str) or not network_xml:
        raise CoordinatorError("Pinned network XML is missing.")
    if not isinstance(prompt, str) or not prompt:
        raise CoordinatorError("Pinned prompt is missing.")
    network_bytes = network_xml.encode("utf-8")
    validated = validate_xmlbif(network_bytes)
    if entry.get("network_hash") != validated["source_sha256"]:
        raise CoordinatorError("Pinned network hash does not match XML bytes.")

    network_contract, cpt_contract = _network_contract(entry, validated)
    query = _pinned_query(entry, validated)
    scoped = _scoped_projection(entry, projection, projection_hash)
    provider = _resolve_provider(database_url)
    body = {
        "prompt": prompt,
        "network_contract": network_contract,
        "cpt_contract": cpt_contract,
        "projection": scoped,
        "projection_hash": projection_hash,
        "tools": _tool_declaration(),
    }
    request = {
        **body,
        "base_url": provider["base_url"],
        "api_key": provider["api_key"],
    }

    grant = secrets.token_urlsafe(32)
    _insert_grant(
        grant,
        run,
        stored["id"],
        question_key,
        projection_hash,
        claim,
        database_url,
    )
    try:
        candidate = asyncio.run(_estimate_via_mcp(grant, request, database_url))
    finally:
        stop_and_revoke(grant, database_url)

    accepted = validate_cpt_response(candidate)
    artifact = build_effective_artifact(validated, accepted)
    effective_xml, effective_hash = _run_local_effective(artifact, question_key, run_id)
    posterior = infer(
        artifact,
        str(query["target"]),
        str(query["state"]),
        {str(k): str(v) for k, v in dict(query["evidence"]).items()},
    )
    result = {
        "target": str(query["target"]),
        "state": str(query["state"]),
        "posterior": float(posterior),
        "evidence": {str(k): str(v) for k, v in dict(query["evidence"]).items()},
    }
    rendered, template_version = render_section(
        entry.get("template"),
        question_key,
        entry.get("version"),
        accepted,
        query,
        float(posterior),
    )
    variables = scoped["variables"]
    source_paths = sorted(
        {
            str(item["source_path"])
            for item in variables
            if isinstance(item, dict) and item.get("source_path")
        }
    )
    provenance = {
        "bundle_hash": run["bundle_hash"],
        "network_hash": validated["source_sha256"],
        "network_version": entry.get("version"),
        "projection_hash": projection_hash,
        "snapshot_hash": run["snapshot_hash"],
        "source_paths": source_paths,
        "missingness": {
            str(item["node_id"]): str(item.get("status"))
            for item in variables
            if isinstance(item, dict) and item.get("node_id")
        },
        "engine": dict(ENGINE_PIN),
    }
    model_provenance = {
        "base_url": provider["base_url"],
        "model": provider["model"],
        "provider_revision": provider["revision"],
        "lease_token": str(claim["lease_token"]),
        "fencing_generation": int(claim.get("fencing_generation") or 0),
        "attempt_index": int(context["attempt_count"]) + 1,
    }
    _persist_artifact(
        run_id,
        int(stored["ordinal"]),
        question_key,
        body,
        dict(projection),
        prompt,
        model_provenance,
        accepted,
        effective_xml,
        effective_hash,
        query,
        result,
        rendered,
        template_version,
        provenance,
        database_url,
    )

    _verify_artifact_for_commit(run_id, question_key, database_url)

    committed = queue_module.complete_job(
        job_id, str(claim["lease_token"]), {"ok": True}, database_url
    )
    if committed is None:
        raise CoordinatorError(
            "Stale lease token, expired lease, or rotated deployment; "
            "the section was stored but the job was not committed."
        )
    # S46 slices 1-3: chain the next ready question instead of succeeding.
    # Only one queued/claimed job per run; the run stays non-terminal
    # until the proposal gate decides terminal status.
    _enqueue_next_ready(run_id, database_url)
    try:
        from x_insight.reasoning.proposal import try_assemble_proposal

        try_assemble_proposal(run_id, database_url)
    except Exception:
        pass
    return {"ok": True, "question_key": question_key, "posterior": float(posterior)}
