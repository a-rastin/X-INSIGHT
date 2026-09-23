"""S43 slice 1 RED: bounded provider CPT estimation (T7, real T6 bridge).

Synthetic fixtures only, clearly labeled, never released. No live provider:
the only outbound HTTP target is an in-test localhost server. The provider
uses real HTTP (httpx) to localhost with X_INSIGHT_PROVIDER_ALLOW_LOCAL=true.
Assertions read the captured EXTERNAL request body, never an internal mock.

Expected RED: ``x_insight.reasoning.provider`` does not exist yet, so the
top-level import below fails with ModuleNotFoundError.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import secrets
import socketserver
import threading
import time as _s4_time
from typing import Any

import httpx as _s4_httpx
import pytest
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from sqlalchemy import text

from x_insight import db
from x_insight.models.inference import validate_cpt_response
from x_insight.reasoning import provider as _s4_provider
from x_insight.reasoning.mcp_host import build_scoped_server_params
from x_insight.reasoning.provider import (
    MAX_REQUEST_BYTES as _S4_MAX_REQ,
)
from x_insight.reasoning.provider import (
    MAX_RESPONSE_BYTES as _S3_MAX_BYTES,
)
from x_insight.reasoning.provider import (
    MAX_TOOL_CALLS as _S4_MAX_CALLS,
)
from x_insight.reasoning.provider import ProviderError, estimate_cpts

# --- Synthetic fixtures only (never BNs/, never clinical, never released). ---
SYNTHETIC_QUESTION_KEY = "synthetic_s43_slice1"
SYNTHETIC_NETWORK_VERSION = "v1"
SYNTHETIC_NETWORK_HASH = "ab" * 32
SYNTHETIC_PROMPT = (
    "SYNTHETIC S43 slice1 pinned question prompt: estimate every CPT as "
    "percentages summing to 100 for nodes A->B."
)
SYNTHETIC_PROJECTION_HASH = "cd" * 32
SYNTHETIC_PROJECTION_VALUE_A = "synthetic-projection-value-A-no"
SYNTHETIC_API_KEY = "synthetic-provider-key-s43-001"
SYNTHETIC_NOTES_TEXT = "SYNTHETIC clinical note text that must never be sent s43-001"
SYNTHETIC_PATIENT_NAME = "SyntheticPatient S43"
SYNTHETIC_PATIENT_ID = "0123456789"
SYNTHETIC_TEMPLATE_TEXT = "SYNTHETIC template body that must never be sent s43-001"

ALLOWED_TOP_KEYS = frozenset(
    {
        "prompt",
        "network_contract",
        "cpt_contract",
        "projection",
        "projection_hash",
        "tools",
    }
)
PERMITTED_TOOL_NAME = "get_question_patient_inputs"


def _synthetic_candidate_response() -> dict[str, Any]:
    """Strict candidate CPT for synthetic 2-node A->B (same math as S23 slice 1)."""
    return {
        "question_key": SYNTHETIC_QUESTION_KEY,
        "network_version": SYNTHETIC_NETWORK_VERSION,
        "network_hash": SYNTHETIC_NETWORK_HASH,
        "tables": [
            {
                "node_id": "A",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [80, 20]}],
            },
            {
                "node_id": "B",
                "parent_ids": ["A"],
                "states": ["no", "yes"],
                "rows": [
                    {"parent_states": ["no"], "percentages": [90, 10]},
                    {"parent_states": ["yes"], "percentages": [30, 70]},
                ],
            },
        ],
    }


class _EstimationHandler(http.server.BaseHTTPRequestHandler):
    """Deterministic localhost endpoint: capture body, return strict CPT."""

    bodies: list = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self.bodies.append(raw)
        payload = json.dumps(_synthetic_candidate_response()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture()
def estimation_server():
    bodies: list = []
    handler = type("BoundEstimation", (_EstimationHandler,), {"bodies": bodies})
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    try:
        host, port = server.server_address
        yield {"base": f"http://{host}:{port}", "bodies": bodies}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_slice1_strict_request_response(estimation_server, monkeypatch) -> None:
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    # Real HTTP (httpx, provider-owned client) to localhost; no internal mock.
    base_url = estimation_server["base"]
    network_contract: dict[str, Any] = {
        "question_key": SYNTHETIC_QUESTION_KEY,
        "network_version": SYNTHETIC_NETWORK_VERSION,
        "network_hash": SYNTHETIC_NETWORK_HASH,
        "nodes": ["A", "B"],
        "edges": [["A", "B"]],
        "states": {"A": ["no", "yes"], "B": ["no", "yes"]},
        "parents": {"A": [], "B": ["A"]},
    }
    projection: dict[str, Any] = {
        "question_key": SYNTHETIC_QUESTION_KEY,
        "network_version": SYNTHETIC_NETWORK_VERSION,
        "variables": [{"node_id": "A", "value": SYNTHETIC_PROJECTION_VALUE_A}],
    }
    cpt_contract: dict[str, Any] = {
        "all_nodes_mandatory": True,
        "nodes": ["A", "B"],
    }
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": PERMITTED_TOOL_NAME,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        }
    ]
    request: dict[str, Any] = {
        "base_url": base_url,
        "model": "synthetic-model-s43-slice1",
        "api_key": SYNTHETIC_API_KEY,
        "prompt": SYNTHETIC_PROMPT,
        "network_contract": network_contract,
        "projection": projection,
        "projection_hash": SYNTHETIC_PROJECTION_HASH,
        "cpt_contract": cpt_contract,
        "tools": tools,
    }

    def permitted_tool_bridge(
        name: str, args: dict[str, Any], call_id: str
    ) -> dict[str, Any]:
        assert name == PERMITTED_TOOL_NAME
        assert args == {}
        return {"call_id": call_id, "projection": projection}

    candidate = estimate_cpts(request, permitted_tool_bridge)

    # External captured request: exactly one real HTTP POST arrived.
    assert len(estimation_server["bodies"]) == 1
    body = json.loads(estimation_server["bodies"][0].decode("utf-8"))
    assert set(body.keys()) <= set(ALLOWED_TOP_KEYS), body.keys()
    assert "prompt" in body
    assert ("network_contract" in body) or ("cpt_contract" in body)
    assert ("projection" in body) or ("projection_hash" in body)
    assert "tools" in body
    dumped = json.dumps(body, sort_keys=True)
    assert SYNTHETIC_PROMPT in dumped
    assert SYNTHETIC_NETWORK_HASH in dumped
    assert SYNTHETIC_PROJECTION_VALUE_A in dumped
    assert SYNTHETIC_API_KEY not in dumped
    assert SYNTHETIC_NOTES_TEXT not in dumped
    assert SYNTHETIC_PATIENT_NAME not in dumped
    assert SYNTHETIC_PATIENT_ID not in dumped
    assert SYNTHETIC_TEMPLATE_TEXT not in dumped
    tool_names = [
        t.get("function", {}).get("name") for t in body["tools"] if isinstance(t, dict)
    ]
    assert tool_names == [PERMITTED_TOOL_NAME]

    # Strict candidate response passes the shared S23 validator and contract.
    accepted = validate_cpt_response(candidate)
    assert accepted["question_key"] == SYNTHETIC_QUESTION_KEY
    assert accepted["network_version"] == SYNTHETIC_NETWORK_VERSION
    assert accepted["network_hash"] == SYNTHETIC_NETWORK_HASH
    tables = accepted["tables"]
    assert [t["node_id"] for t in tables] == ["A", "B"]
    assert tables[0]["parent_ids"] == []
    assert tables[0]["states"] == ["no", "yes"]
    assert tables[1]["parent_ids"] == ["A"]
    assert tables[1]["states"] == ["no", "yes"]
    assert [r["parent_states"] for r in tables[0]["rows"]] == [[]]
    assert [r["parent_states"] for r in tables[1]["rows"]] == [["no"], ["yes"]]
    assert tables[0]["rows"][0]["percentages"] == [80, 20]
    assert tables[1]["rows"][0]["percentages"] == [90, 10]
    assert tables[1]["rows"][1]["percentages"] == [30, 70]
    for table in tables:
        for row in table["rows"]:
            assert abs(sum(row["percentages"]) - 100) <= 1e-6


# --- S43 slice2 RED: tool bridging via real MCP (T7 with real T6 bridge). ---
# Synthetic fixtures only, clearly labeled, never released. Real HTTP to
# localhost (ALLOW_LOCAL) + real MCP stdio subprocess. Expected RED:
# provider.py is slice1 single-POST direct-CPT with no tool loop, so (a)
# wrong POST count/return, (b) wrong error code, (c) DID NOT RAISE / no bridge.

_S2_QUESTION_KEY = "synthetic_s43_slice2"
_S2_NETWORK_VERSION = "v1"
_S2_NETWORK_HASH = "ee" * 32
_S2_PROMPT = "SYNTHETIC S43 slice2 pinned prompt A->B percentages s43-s2-001"
_S2_PROJ_QKEY = "synthetic_s43_slice2_q1"
_S2_PROJ_NETVER = 7
_S2_PROJ_HASH = "synthetic-s43-slice2-proj-hash-001"
_S2_SNAP_HASH = "synthetic-s43-slice2-snap-hash-001"
_S2_AGE_SENTINEL = 424242
_S2_API_KEY = "synthetic-provider-key-s43-slice2-002"
_S2_NOTES = "SYNTHETIC clinical note text must never be sent s43-slice2-002"
_S2_PATIENT_NAME = "SyntheticPatient S43 Slice2"
_S2_PATIENT_ID = "slice2-patient-99999"
_S2_TEMPLATE = "SYNTHETIC template body must never be sent s43-slice2-002"
_S2_VARIABLES = [
    {
        "node_id": "SyntheticSlice2Age",
        "status": "observed",
        "value": _S2_AGE_SENTINEL,
        "source_ref": "snapshot.synthetic.s43s2.age",
    },
    {
        "node_id": "SyntheticSlice2Cond",
        "status": "not_assessed",
        "value": None,
        "source_ref": "snapshot.synthetic.s43s2.cond",
    },
]


def _slice2_candidate_response() -> dict[str, Any]:
    """Strict synthetic A->B CPT (duplicate of slice1 helper, not refactor)."""
    return {
        "question_key": _S2_QUESTION_KEY,
        "network_version": _S2_NETWORK_VERSION,
        "network_hash": _S2_NETWORK_HASH,
        "tables": [
            {
                "node_id": "A",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [80, 20]}],
            },
            {
                "node_id": "B",
                "parent_ids": ["A"],
                "states": ["no", "yes"],
                "rows": [
                    {"parent_states": ["no"], "percentages": [90, 10]},
                    {"parent_states": ["yes"], "percentages": [30, 70]},
                ],
            },
        ],
    }


def _slice2_seed_valid_grant() -> dict[str, Any]:
    """Copy of scoped-transport slice2 seeding (no import from that module)."""
    grant = secrets.token_urlsafe(32)
    username = f"synthetic-s43-slice2-{secrets.token_hex(4)}"
    projection = {
        "question_key": _S2_PROJ_QKEY,
        "network_version": _S2_PROJ_NETVER,
        "variables": _S2_VARIABLES,
        "synthetic_marker": "test-only s43-slice2, never released",
    }
    with db.transaction() as conn:
        conn.execute(text("TRUNCATE mcp_question_grants, run_questions, runs"))
        actor_id = conn.execute(
            text(
                "INSERT INTO users (username, role, active, password_hash)"
                " VALUES (:u, 'physician', TRUE, 'synthetic') RETURNING id"
            ),
            {"u": username},
        ).scalar_one()
        enc = conn.execute(text("SELECT gen_random_uuid()")).scalar_one()
        run_id = conn.execute(
            text(
                "INSERT INTO runs (encounter_id, encounter_revision, workflow,"
                " snapshot, snapshot_hash, fingerprint, bundle_hash, pins,"
                " status) VALUES (:e, 1, 'synthetic', CAST(:s AS jsonb),"
                " :sh, 'syn-s43s2-fp', 'syn-s43s2-bundle',"
                " CAST(:p AS jsonb), 'queued') RETURNING id"
            ),
            {
                "e": str(enc),
                "s": json.dumps({"synthetic": "s43-slice2"}),
                "sh": _S2_SNAP_HASH,
                "p": json.dumps({"synthetic": True}),
            },
        ).scalar_one()
        qid = conn.execute(
            text(
                "INSERT INTO run_questions (run_id, question_key, ordinal,"
                " projection, projection_hash) VALUES (:r, :qk, 0,"
                " CAST(:proj AS jsonb), :ph) RETURNING id"
            ),
            {
                "r": str(run_id),
                "qk": _S2_PROJ_QKEY,
                "proj": json.dumps(projection),
                "ph": _S2_PROJ_HASH,
            },
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO mcp_question_grants (grant_token, run_id,"
                " run_question_id, question_key, actor_id, encounter_id,"
                " snapshot_hash, projection_hash, expires_at, revoked_at)"
                " VALUES (:g, :r, :q, :qk, :a, :e, :sh, :ph,"
                " now() + interval '1 hour', NULL)"
            ),
            {
                "g": grant,
                "r": str(run_id),
                "q": str(qid),
                "qk": _S2_PROJ_QKEY,
                "a": str(actor_id),
                "e": str(enc),
                "sh": _S2_SNAP_HASH,
                "ph": _S2_PROJ_HASH,
            },
        )
    return {
        "grant": grant,
        "actor_id": str(actor_id),
        "run_id": str(run_id),
        "question_id": str(qid),
        "projection_hash": _S2_PROJ_HASH,
    }


def _slice2_start_server(payloads: list[dict[str, Any]]):
    bodies: list[bytes] = []
    seq = list(payloads)

    class _H(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
            payload = seq[min(len(bodies) - 1, len(seq) - 1)]
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a: Any) -> None:
            pass

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _H)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05})
    th.daemon = True
    th.start()
    host, port = srv.server_address
    return srv, th, bodies, f"http://{host}:{port}"


async def _slice2_real_mcp_call(grant: str) -> Any:
    params = build_scoped_server_params(grant)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool("get_question_patient_inputs", {})


def _slice2_payload_or_raise(result: Any) -> dict[str, Any]:
    is_err = getattr(result, "is_error", False) or getattr(result, "isError", False)
    if is_err:
        raise ProviderError("grant_denied", "MCP grant denied.", False)
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    assert len(texts) == 1
    return json.loads(texts[0])


def _slice2_request(base_url: str) -> dict[str, Any]:
    return {
        "base_url": base_url,
        "model": "synthetic-model-s43-slice2",
        "api_key": _S2_API_KEY,
        "prompt": _S2_PROMPT,
        "network_contract": {
            "question_key": _S2_QUESTION_KEY,
            "network_version": _S2_NETWORK_VERSION,
            "network_hash": _S2_NETWORK_HASH,
            "nodes": ["A", "B"],
            "edges": [["A", "B"]],
            "states": {"A": ["no", "yes"], "B": ["no", "yes"]},
            "parents": {"A": [], "B": ["A"]},
        },
        "projection_hash": _S2_PROJ_HASH,
        "cpt_contract": {"all_nodes_mandatory": True, "nodes": ["A", "B"]},
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_question_patient_inputs",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            }
        ],
    }


def test_slice2_permitted_tool_crosses_real_mcp(monkeypatch) -> None:
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    seeded = _slice2_seed_valid_grant()
    grant = seeded["grant"]
    first = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_question_patient_inputs",
                                "arguments": "{}",
                            },
                        }
                    ],
                }
            }
        ]
    }
    srv, th, bodies, base = _slice2_start_server([first, _slice2_candidate_response()])
    try:

        def bridge(name: str, args: dict[str, Any], cid: str) -> dict[str, Any]:
            assert name == "get_question_patient_inputs"
            assert args == {}
            payload = _slice2_payload_or_raise(
                asyncio.run(_slice2_real_mcp_call(grant))
            )
            return {"call_id": cid, "result": payload}

        candidate = estimate_cpts(_slice2_request(base), bridge)
        accepted = validate_cpt_response(candidate)
        assert accepted["question_key"] == _S2_QUESTION_KEY
        assert [t["node_id"] for t in accepted["tables"]] == ["A", "B"]
        assert len(bodies) == 2, f"expected 2 POSTs, got {len(bodies)}"
        dumped = [json.dumps(json.loads(b.decode()), sort_keys=True) for b in bodies]
        assert _S2_PROMPT in dumped[0] and _S2_NETWORK_HASH in dumped[0]
        assert "call_1" in dumped[1], dumped[1]
        assert str(_S2_AGE_SENTINEL) in dumped[1], dumped[1]
        for blob in dumped:
            for secret in (
                _S2_API_KEY,
                _S2_NOTES,
                _S2_PATIENT_NAME,
                _S2_PATIENT_ID,
                _S2_TEMPLATE,
                grant,
            ):
                assert secret not in blob, f"leaked {secret[:16]!r}"
    finally:
        srv.shutdown()
        srv.server_close()
        th.join(timeout=5)


def test_slice2_disallowed_tool_rejected(monkeypatch) -> None:
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    bad = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_9",
                            "type": "function",
                            "function": {"name": "do_anything", "arguments": "{}"},
                        }
                    ],
                }
            }
        ]
    }
    srv, th, bodies, base = _slice2_start_server([bad])
    try:
        calls: list[tuple] = []

        def bridge(name: str, args: dict[str, Any], cid: str) -> dict[str, Any]:
            calls.append((name, args, cid))
            raise AssertionError("bridge must not run for disallowed tool")

        with pytest.raises(ProviderError) as exc:
            estimate_cpts(_slice2_request(base), bridge)
        assert exc.value.code == "tool_rejected", exc.value.code
        assert exc.value.retryable is False
        assert calls == [], "disallowed tool must not reach MCP bridge"
        assert len(bodies) == 1, f"fail fast, no retry: {len(bodies)}"
    finally:
        srv.shutdown()
        srv.server_close()
        th.join(timeout=5)


def test_slice2_initial_read_uses_mcp_and_spoofed_rejected(monkeypatch) -> None:
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    seeded = _slice2_seed_valid_grant()
    grant = seeded["grant"]
    srv, th, bodies, base = _slice2_start_server([_slice2_candidate_response()])
    try:
        calls: list[tuple] = []

        def bridge(name: str, args: dict[str, Any], cid: str) -> dict[str, Any]:
            calls.append((name, args, cid))
            assert name == "get_question_patient_inputs"
            assert args == {}
            payload = _slice2_payload_or_raise(
                asyncio.run(_slice2_real_mcp_call(grant))
            )
            return {"call_id": cid, "result": payload}

        req = _slice2_request(base)
        assert "projection" not in req, "initial read must come via MCP"
        candidate = estimate_cpts(req, bridge)
        assert validate_cpt_response(candidate)["question_key"] == _S2_QUESTION_KEY
        assert len(calls) >= 1, "estimate must read initial inputs via MCP"
        with db.transaction() as conn:
            conn.execute(
                text(
                    "UPDATE mcp_question_grants SET revoked_at=now()"
                    " WHERE grant_token=:g"
                ),
                {"g": grant},
            )
        calls.clear()
        with pytest.raises(ProviderError) as exc:
            estimate_cpts(_slice2_request(base), bridge)
        assert exc.value.retryable is False
        blob = (exc.value.code + " " + str(exc.value)).lower()
        assert "grant" in blob or "tool" in blob, blob
    finally:
        srv.shutdown()
        srv.server_close()
        th.join(timeout=5)


# --- S43 slice3 RED: capability modes + strict rejection (T7). ---
# Synthetic fixtures only, localhost HTTP with ALLOW_LOCAL, no live provider,
# no internal mocks (assert via captured bodies + raised codes).
# Capability key choice: request["capability_mode"]="schema"|"json"; schema mode
# must send "response_format" (json_schema) in first POST body, json mode must not.
# Strict codes: extra prose -> "invalid_cpt" retryable True; multiple finals ->
# "ambiguous" retryable False; truncated -> "invalid_cpt" retryable True;
# oversized -> "oversized" retryable False. Expected RED: slice2 provider sends
# neither response_format, accepts first choice, has no size bound.

_S3_QKEY = "synthetic_s43_slice3"
_S3_NETVER = "v1"
_S3_NETHASH = "fa" * 32
_S3_PROMPT = "SYNTHETIC S43 slice3 pinned prompt A->B percentages s43-s3-001"
_S3_PROJHASH = "synthetic-s43-slice3-proj-hash-001"
_S3_APIKEY = "synthetic-provider-key-s43-slice3-003"
_S3_NOTES = "SYNTHETIC clinical note must never be sent s43-slice3-003"
_S3_PATIENT = "SyntheticPatient S43 Slice3"
_S3_PID = "slice3-patient-33333"
_S3_TEMPLATE = "SYNTHETIC template must never be sent s43-slice3-003"
_S3_PROJECTION = {
    "question_key": _S3_QKEY,
    "network_version": _S3_NETVER,
    "variables": [{"node_id": "A", "value": "synthetic-s43-s3-A-no"}],
}


def _s3_candidate() -> dict[str, Any]:
    """Strict synthetic A->B CPT (duplicate of slice1 helper, not refactor)."""
    return {
        "question_key": _S3_QKEY,
        "network_version": _S3_NETVER,
        "network_hash": _S3_NETHASH,
        "tables": [
            {
                "node_id": "A",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [80, 20]}],
            },
            {
                "node_id": "B",
                "parent_ids": ["A"],
                "states": ["no", "yes"],
                "rows": [
                    {"parent_states": ["no"], "percentages": [90, 10]},
                    {"parent_states": ["yes"], "percentages": [30, 70]},
                ],
            },
        ],
    }


def _s3_request(base_url: str, mode: str) -> dict[str, Any]:
    return {
        "base_url": base_url,
        "model": "synthetic-model-s43-slice3",
        "api_key": _S3_APIKEY,
        "prompt": _S3_PROMPT,
        "network_contract": {
            "question_key": _S3_QKEY,
            "network_version": _S3_NETVER,
            "network_hash": _S3_NETHASH,
            "nodes": ["A", "B"],
            "edges": [["A", "B"]],
            "states": {"A": ["no", "yes"], "B": ["no", "yes"]},
            "parents": {"A": [], "B": ["A"]},
        },
        "projection_hash": _S3_PROJHASH,
        "cpt_contract": {"all_nodes_mandatory": True, "nodes": ["A", "B"]},
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_question_patient_inputs",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "capability_mode": mode,
    }


def _s3_stub(name: str, args: dict[str, Any], cid: str) -> dict[str, Any]:
    assert name == "get_question_patient_inputs"
    assert args == {}
    return {"call_id": cid, "projection": _S3_PROJECTION}


def _s3_start_raw(raw_list: list[bytes]):
    bodies: list[bytes] = []
    seq = list(raw_list)

    class _H(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
            data = seq[min(len(bodies) - 1, len(seq) - 1)]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a: Any) -> None:
            pass

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _H)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05})
    th.daemon = True
    th.start()
    host, port = srv.server_address
    return srv, th, bodies, f"http://{host}:{port}"


def test_slice3_capability_modes_share_strict_validator(monkeypatch) -> None:
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    s1, t1, b1, base1 = _slice2_start_server([_s3_candidate()])
    s2, t2, b2, base2 = _slice2_start_server([_s3_candidate()])
    try:
        cand_schema = estimate_cpts(_s3_request(base1, "schema"), _s3_stub)
        cand_json = estimate_cpts(_s3_request(base2, "json"), _s3_stub)
        assert validate_cpt_response(cand_schema)["question_key"] == _S3_QKEY
        assert validate_cpt_response(cand_json)["question_key"] == _S3_QKEY
        body_schema = json.loads(b1[0].decode("utf-8"))
        body_json = json.loads(b2[0].decode("utf-8"))
        for blob in (
            json.dumps(body_schema, sort_keys=True),
            json.dumps(body_json, sort_keys=True),
        ):
            for secret in (_S3_APIKEY, _S3_NOTES, _S3_PATIENT, _S3_PID, _S3_TEMPLATE):
                assert secret not in blob
        assert "response_format" in body_schema, f"schema mode: {sorted(body_schema)}"
        assert "response_format" not in body_json, f"json mode: {sorted(body_json)}"
    finally:
        s1.shutdown()
        s1.server_close()
        t1.join(timeout=5)
        s2.shutdown()
        s2.server_close()
        t2.join(timeout=5)


def test_slice3_rejects_extra_prose_and_ambiguous(monkeypatch) -> None:
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    inner = json.dumps(_s3_candidate())
    prose = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": f"SYNTHETIC prose prefix {inner} trailing prose",
                }
            }
        ]
    }
    s1, t1, b1, base1 = _slice2_start_server([prose])
    try:
        with pytest.raises(ProviderError) as e1:
            estimate_cpts(_s3_request(base1, "json"), _s3_stub)
        assert e1.value.code == "invalid_cpt", e1.value.code
        assert e1.value.retryable is True
    finally:
        s1.shutdown()
        s1.server_close()
        t1.join(timeout=5)
    cpt2 = _s3_candidate()
    cpt2["tables"][0]["rows"][0]["percentages"] = [50, 50]
    amb = {"choices": [_s3_candidate(), cpt2]}
    s2, t2, b2, base2 = _slice2_start_server([amb])
    try:
        with pytest.raises(ProviderError) as e2:
            estimate_cpts(_s3_request(base2, "json"), _s3_stub)
        assert e2.value.code == "ambiguous", e2.value.code
        assert e2.value.retryable is False
    finally:
        s2.shutdown()
        s2.server_close()
        t2.join(timeout=5)


def test_slice3_rejects_malformed_truncated_oversized(monkeypatch) -> None:
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    bad = _s3_candidate()
    bad["tables"][0]["rows"][0]["percentages"] = ["80", "20"]
    s1, t1, _b1, base1 = _slice2_start_server([bad])
    try:
        with pytest.raises(ProviderError) as e1:
            estimate_cpts(_s3_request(base1, "json"), _s3_stub)
        assert e1.value.code == "invalid_cpt", e1.value.code
        assert e1.value.retryable is True
    finally:
        s1.shutdown()
        s1.server_close()
        t1.join(timeout=5)
    s2, t2, _b2, base2 = _s3_start_raw([b'{"question_key": "x", "tables": ['])
    try:
        with pytest.raises(ProviderError) as e2:
            estimate_cpts(_s3_request(base2, "json"), _s3_stub)
        assert e2.value.code == "invalid_cpt", e2.value.code
        assert e2.value.retryable is True
    finally:
        s2.shutdown()
        s2.server_close()
        t2.join(timeout=5)
    big = _s3_candidate()
    big["padding"] = "X" * (_S3_MAX_BYTES + 100 * 1024)
    s3, t3, _b3, base3 = _slice2_start_server([big])
    try:
        with pytest.raises(ProviderError) as e3:
            estimate_cpts(_s3_request(base3, "json"), _s3_stub)
        assert e3.value.code == "oversized", e3.value.code
        assert e3.value.retryable is False
    finally:
        s3.shutdown()
        s3.server_close()
        t3.join(timeout=5)


# --- S43 slice4 RED: error retryability + budgets, no hidden retries (T7). ---
# Synthetic only, localhost ALLOW_LOCAL, stub bridge, no live provider.
# Expected RED: provider maps timeout->transport False, all non-200 to
# bad_status False, and has no request-size bound (POSTs oversized prompt).


def _s4_start_status(status: int, obj: dict[str, Any], delay: float = 0.0):
    bodies: list[bytes] = []
    data = json.dumps(obj).encode()

    class _H(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
            if delay:
                _s4_time.sleep(delay)
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *a: Any) -> None:
            pass

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _H)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05})
    th.daemon = True
    th.start()
    host, port = srv.server_address
    return srv, th, bodies, f"http://{host}:{port}"


def _s4_stop(srv, th) -> None:
    srv.shutdown()
    srv.server_close()
    th.join(timeout=5)


def test_slice4_error_retryability_maps_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    # Timeout: server sleeps 0.6s, client timeout patched to 0.2s.
    srv, th, bodies, base = _s4_start_status(200, _s3_candidate(), delay=0.6)
    try:
        monkeypatch.setattr(
            _s4_provider,
            "_REQUEST_TIMEOUT",
            _s4_httpx.Timeout(connect=0.2, read=0.2, write=0.2, pool=0.2),
        )
        with pytest.raises(ProviderError) as exc:
            estimate_cpts(_s3_request(base, "json"), _s3_stub)
        assert exc.value.code == "timeout", exc.value.code
        assert exc.value.retryable is True
        assert len(bodies) == 1, f"no hidden retry: {len(bodies)}"
    finally:
        _s4_stop(srv, th)
    cases = [
        (401, {"error": "SYNTHETIC invalid api key"}, "auth_failed", False),
        (404, {"error": "SYNTHETIC model not found"}, "model_not_found", False),
        (429, {"error": "SYNTHETIC rate limited"}, "rate_limited", True),
        (
            422,
            {"error": "SYNTHETIC tool use not supported for model"},
            "capability_unsupported",
            False,
        ),
    ]
    for status, obj, code, retry in cases:
        srv, th, bodies, base = _s4_start_status(status, obj)
        try:
            with pytest.raises(ProviderError) as exc:
                estimate_cpts(_s3_request(base, "json"), _s3_stub)
            assert exc.value.code == code, f"{status}: {exc.value.code}"
            assert exc.value.retryable is retry, f"{status}: retryable"
            assert len(bodies) == 1, f"{status}: no retry {len(bodies)}"
        finally:
            _s4_stop(srv, th)


def test_slice4_budgets_enforced_no_hidden_retries(monkeypatch) -> None:
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    bodies: list[bytes] = []
    count = [0]

    class _Loop(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
            count[0] += 1
            payload = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": f"call_{count[0]}",
                                    "type": "function",
                                    "function": {
                                        "name": "get_question_patient_inputs",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a: Any) -> None:
            pass

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Loop)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05})
    th.daemon = True
    th.start()
    host, port = srv.server_address
    base = f"http://{host}:{port}"
    try:
        with pytest.raises(ProviderError) as exc:
            estimate_cpts(_s3_request(base, "json"), _s3_stub)
        assert exc.value.code == "budget_exceeded", exc.value.code
        assert exc.value.retryable is False
        assert len(bodies) == _S4_MAX_CALLS + 1, f"POSTs={len(bodies)}"
    finally:
        _s4_stop(srv, th)
    srv2, th2, bodies2, base2 = _slice2_start_server([_s3_candidate()])
    try:
        big = _s3_request(base2, "json")
        big["prompt"] = "SYNTHETIC " + "X" * (_S4_MAX_REQ + 1024)
        with pytest.raises(ProviderError) as exc2:
            estimate_cpts(big, _s3_stub)
        assert exc2.value.code == "oversized", exc2.value.code
        assert exc2.value.retryable is False
        assert len(bodies2) == 0, f"oversize must not POST: {len(bodies2)}"
    finally:
        _s4_stop(srv2, th2)
