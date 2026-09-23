"""S41 slice 1 (RED): real private MCP stdio transport + context grants (T6).

Slice-1 scope ONLY (plan.md S8.2, MCP-design SS3-4, FR-32-35, NFR-02):
a real MCP SDK client spawns the private server as a stdio subprocess,
discovers exactly one tool, and reads back the bound stored projection.
Grant lifecycle details (expiry, revocation, multi-question rebinding,
cross-patient isolation) belong to later slices and are NOT tested here.

EXPECTED RED: x_insight.reasoning.mcp_host, the mcp_question_grants
table, and the `python -m x_insight.mcp_server` entry point do not
exist yet.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError
from sqlalchemy import text

from x_insight import db
from x_insight.reasoning.mcp_host import MCP_GRANT_ENV_VAR, build_scoped_server_params

TOOL_NAME = "get_question_patient_inputs"
EXPECTED_INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

# --- Clearly labeled SYNTHETIC fixture (test-only, never a released default).

_SYNTHETIC_QUESTION_KEY = "synthetic_registration_q1"
_SYNTHETIC_NETWORK_VERSION = 1
_SYNTHETIC_PROJECTION_HASH = "synthetic-projection-hash-001"
_SYNTHETIC_VARIABLES = [
    {
        "node_id": "SyntheticAge",
        "status": "observed",
        "value": 42,
        "source_ref": "snapshot.synthetic.age",
    },
    {
        "node_id": "SyntheticCondition",
        "status": "not_assessed",
        "value": None,
        "source_ref": "snapshot.synthetic.condition",
    },
]


def _seed_synthetic_bound_projection() -> dict:
    """Persist one synthetic run/question + grant; return grant + expected.

    Writes against the INTENDED minimal schema: runs/run_questions exist
    (migration 0013); mcp_question_grants does not exist yet and fails red.
    The expected tool payload is READ BACK from the stored run_questions
    row so the behavior assertion compares against persisted state.
    """
    grant = secrets.token_urlsafe(32)
    projection = {
        "question_key": _SYNTHETIC_QUESTION_KEY,
        "network_version": _SYNTHETIC_NETWORK_VERSION,
        "variables": _SYNTHETIC_VARIABLES,
        "synthetic_marker": "test-only fixture, never a released default",
    }
    with db.transaction() as conn:
        try:
            conn.execute(text("TRUNCATE run_questions, runs"))
        except Exception:
            pass
        run_id = conn.execute(
            text(
                "INSERT INTO runs (encounter_id, encounter_revision, workflow,"
                " snapshot, snapshot_hash, fingerprint, bundle_hash, pins,"
                " status) VALUES (gen_random_uuid(), 1, 'synthetic',"
                " CAST(:snapshot AS jsonb), 'synthetic-snapshot-hash',"
                " 'synthetic-fingerprint', 'synthetic-bundle',"
                " CAST(:pins AS jsonb), 'queued') RETURNING id"
            ),
            {
                "snapshot": json.dumps({"synthetic": True}),
                "pins": json.dumps({"synthetic": True}),
            },
        ).scalar_one()
        question_id = conn.execute(
            text(
                "INSERT INTO run_questions (run_id, question_key, ordinal,"
                " projection, projection_hash) VALUES (:run_id, :question_key,"
                " 0, CAST(:projection AS jsonb), :projection_hash)"
                " RETURNING id"
            ),
            {
                "run_id": str(run_id),
                "question_key": _SYNTHETIC_QUESTION_KEY,
                "projection": json.dumps(projection),
                "projection_hash": _SYNTHETIC_PROJECTION_HASH,
            },
        ).scalar_one()
        # INTENDED minimal grant schema (table does not exist yet -> red).
        conn.execute(
            text(
                "INSERT INTO mcp_question_grants"
                " (grant_token, run_id, run_question_id, question_key)"
                " VALUES (:grant, :run_id, :question_id, :question_key)"
            ),
            {
                "grant": grant,
                "run_id": str(run_id),
                "question_id": str(question_id),
                "question_key": _SYNTHETIC_QUESTION_KEY,
            },
        )
        stored = conn.execute(
            text(
                "SELECT question_key, projection, projection_hash"
                " FROM run_questions WHERE id = :question_id"
            ),
            {"question_id": str(question_id)},
        ).mappings().one()
    stored_projection = stored["projection"]
    expected = {
        "question_key": stored["question_key"],
        "network_version": stored_projection["network_version"],
        "projection_hash": stored["projection_hash"],
        "variables": stored_projection["variables"],
    }
    return {"grant": grant, "expected": expected}


async def _list_and_call_via_real_stdio(
    params: StdioServerParameters,
) -> tuple[object, object]:
    """Drive discovery + tool call through a REAL subprocess + SDK client."""
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            call = await session.call_tool(TOOL_NAME, {})
    return tools, call


def test_scoped_stdio_transport_returns_bound_projection() -> None:
    seeded = _seed_synthetic_bound_projection()
    grant = seeded["grant"]
    expected = seeded["expected"]

    # Host adapter builds the private-server launch; the test still drives
    # a real subprocess + SDK client below (never a direct function call
    # for the tool result).
    params = build_scoped_server_params(grant)

    # Entry point contract: private stdio server, no public listener.
    assert params.command == sys.executable
    assert params.args == ["-m", "x_insight.mcp_server"]
    # Opaque grant travels via protected process environment, never CLI.
    assert params.env is not None
    assert params.env.get(MCP_GRANT_ENV_VAR) == grant
    assert grant not in " ".join(params.args)

    tools, call = asyncio.run(_list_and_call_via_real_stdio(params))

    # Exactly one tool with the exact empty-arguments schema.
    assert [t.name for t in tools.tools] == [TOOL_NAME]
    assert tools.tools[0].input_schema == EXPECTED_INPUT_SCHEMA

    # Tool result equals the bound STORED projection.
    assert not getattr(call, "isError", False)
    texts = [
        block.text for block in call.content if getattr(block, "type", "") == "text"
    ]
    assert len(texts) == 1
    payload = json.loads(texts[0])
    assert payload == expected
    assert set(payload) == {
        "question_key",
        "network_version",
        "projection_hash",
        "variables",
    }
    for variable in payload["variables"]:
        assert {"node_id", "status", "value", "source_ref"} <= set(variable)


# --- S41 slice 2 (RED): denial of invalid/unauthorized MCP access (T6).
#
# FR-32-35, NFR-02. Every case drives a SAFE failure through the REAL stdio
# transport (real SDK client + real `python -m x_insight.mcp_server`
# subprocess via `build_scoped_server_params`): either an MCP protocol error
# (MCPError) or a green-safe error result (isError True) — never success,
# never leaked projection values/secrets, never another patient's data.
# Context comes ONLY from protected worker state (grant row + env), never
# from model arguments.
#
# EXPECTED RED: mcp_server.py currently checks only grant existence and
# rejects extra args / unknown tools. It does NOT yet enforce expiry,
# revocation, snapshot/projection hash binding, or actor active/eligible on
# EVERY read, so the expiry/revocation/binding/actor sub-cases fail red
# (server returns the projection instead of a safe denial).

_S2_QUESTION_KEY = "synthetic_slice2_q1"
_S2_NETWORK_VERSION = 7
_S2_PROJECTION_HASH = "synthetic-slice2-projection-hash-001"
_S2_SNAPSHOT_HASH = "synthetic-slice2-snapshot-hash-001"
_S2_SECRET_NODE = "SyntheticSlice2Age"
_S2_SECRET_VALUE = 424242
_S2_OTHER_PATIENT_MARKER = "synthetic-other-patient-sentinel-9f3a-slice2"
_S2_VARIABLES = [
    {
        "node_id": _S2_SECRET_NODE,
        "status": "observed",
        "value": _S2_SECRET_VALUE,
        "source_ref": "snapshot.synthetic.slice2.age",
    },
    {
        "node_id": "SyntheticSlice2Condition",
        "status": "not_assessed",
        "value": None,
        "source_ref": "snapshot.synthetic.slice2.condition",
    },
]


def _s2_markers(grant: str) -> list[str]:
    """Secrets that must never appear in a denial message/payload."""
    return [
        grant,
        _S2_PROJECTION_HASH,
        _S2_SNAPSHOT_HASH,
        _S2_SECRET_NODE,
        str(_S2_SECRET_VALUE),
        _S2_OTHER_PATIENT_MARKER,
    ]


def _seed_slice2_valid_grant() -> dict:
    """Persist one synthetic actor/run/question + fully-bound grant.

    Clearly labeled SYNTHETIC fixture (test-only, never a released default).
    Seeds a second other-patient run/question so denial tests can assert no
    cross-patient leak. Returns grant + ids for per-test mutation.
    """
    grant = secrets.token_urlsafe(32)
    username = f"synthetic-slice2-{secrets.token_hex(4)}"
    projection = {
        "question_key": _S2_QUESTION_KEY,
        "network_version": _S2_NETWORK_VERSION,
        "variables": _S2_VARIABLES,
        "synthetic_marker": "test-only fixture, never a released default",
    }
    other_projection = {
        "question_key": "synthetic_slice2_other_q1",
        "network_version": _S2_NETWORK_VERSION,
        "variables": [
            {
                "node_id": "OtherPatientNode",
                "status": "observed",
                "value": _S2_OTHER_PATIENT_MARKER,
                "source_ref": "snapshot.synthetic.other",
            }
        ],
        "synthetic_marker": "test-only other-patient fixture",
    }
    with db.transaction() as conn:
        conn.execute(text("TRUNCATE mcp_question_grants, run_questions, runs"))
        actor_id = conn.execute(
            text(
                "INSERT INTO users (username, role, active, password_hash)"
                " VALUES (:username, 'physician', TRUE, 'synthetic')"
                " RETURNING id"
            ),
            {"username": username},
        ).scalar_one()
        encounter_id = conn.execute(text("SELECT gen_random_uuid()")).scalar_one()
        run_id = conn.execute(
            text(
                "INSERT INTO runs (encounter_id, encounter_revision, workflow,"
                " snapshot, snapshot_hash, fingerprint, bundle_hash, pins,"
                " status) VALUES (:encounter_id, 1, 'synthetic',"
                " CAST(:snapshot AS jsonb), :snapshot_hash,"
                " 'synthetic-slice2-fingerprint', 'synthetic-slice2-bundle',"
                " CAST(:pins AS jsonb), 'queued') RETURNING id"
            ),
            {
                "encounter_id": str(encounter_id),
                "snapshot": json.dumps({"synthetic": "slice2"}),
                "snapshot_hash": _S2_SNAPSHOT_HASH,
                "pins": json.dumps({"synthetic": True}),
            },
        ).scalar_one()
        question_id = conn.execute(
            text(
                "INSERT INTO run_questions (run_id, question_key, ordinal,"
                " projection, projection_hash) VALUES (:run_id, :question_key,"
                " 0, CAST(:projection AS jsonb), :projection_hash)"
                " RETURNING id"
            ),
            {
                "run_id": str(run_id),
                "question_key": _S2_QUESTION_KEY,
                "projection": json.dumps(projection),
                "projection_hash": _S2_PROJECTION_HASH,
            },
        ).scalar_one()
        other_run_id = conn.execute(
            text(
                "INSERT INTO runs (encounter_id, encounter_revision, workflow,"
                " snapshot, snapshot_hash, fingerprint, bundle_hash, pins,"
                " status) VALUES (gen_random_uuid(), 1, 'synthetic',"
                " CAST(:snapshot AS jsonb), 'synthetic-other-snapshot',"
                " 'synthetic-other-fingerprint', 'synthetic-other-bundle',"
                " CAST(:pins AS jsonb), 'queued') RETURNING id"
            ),
            {
                "snapshot": json.dumps({"synthetic": "other-patient"}),
                "pins": json.dumps({"synthetic": True}),
            },
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO run_questions (run_id, question_key, ordinal,"
                " projection, projection_hash) VALUES (:run_id, :question_key,"
                " 0, CAST(:projection AS jsonb), 'synthetic-other-hash')"
            ),
            {
                "run_id": str(other_run_id),
                "question_key": "synthetic_slice2_other_q1",
                "projection": json.dumps(other_projection),
            },
        )
        conn.execute(
            text(
                "INSERT INTO mcp_question_grants (grant_token, run_id,"
                " run_question_id, question_key, actor_id, encounter_id,"
                " snapshot_hash, projection_hash, expires_at, revoked_at)"
                " VALUES (:grant, :run_id, :question_id, :question_key,"
                " :actor_id, :encounter_id, :snapshot_hash, :projection_hash,"
                " now() + interval '1 hour', NULL)"
            ),
            {
                "grant": grant,
                "run_id": str(run_id),
                "question_id": str(question_id),
                "question_key": _S2_QUESTION_KEY,
                "actor_id": str(actor_id),
                "encounter_id": str(encounter_id),
                "snapshot_hash": _S2_SNAPSHOT_HASH,
                "projection_hash": _S2_PROJECTION_HASH,
            },
        )
    return {
        "grant": grant,
        "actor_id": str(actor_id),
        "run_id": str(run_id),
        "question_id": str(question_id),
        "encounter_id": str(encounter_id),
    }


async def _call_via_real_stdio(grant: str, tool_name: str, arguments: dict) -> object:
    """Call one tool through a REAL subprocess + SDK client (T6 idiom)."""
    params = build_scoped_server_params(grant)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool_name, arguments)


def _assert_no_leak(text_blob: str, grant: str) -> None:
    for marker in _s2_markers(grant):
        assert marker not in text_blob, f"denial leaked {marker!r}"


def _assert_safe_denial(result: object, grant: str) -> None:
    """Assert a green-safe error result: isError, no data, no leak."""
    is_error = getattr(result, "is_error", False) or getattr(
        result, "isError", False
    )
    assert is_error, f"expected SAFE denial (isError), got success: {result!r}"
    content = getattr(result, "content", []) or []
    texts = [
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", "") == "text"
    ]
    combined = "\n".join(texts)
    _assert_no_leak(combined, grant)


def _run_denial(grant: str, tool_name: str, arguments: dict) -> None:
    """Drive one denial through real transport; accept MCPError or isError."""
    try:
        result = asyncio.run(_call_via_real_stdio(grant, tool_name, arguments))
    except MCPError as exc:
        _assert_no_leak(str(exc), grant)
        return
    except Exception as exc:
        if type(exc).__name__ in ("McpError", "MCPError"):
            _assert_no_leak(str(exc), grant)
            return
        raise
    _assert_safe_denial(result, grant)


def test_slice2_extra_arguments_rejected() -> None:
    seeded = _seed_slice2_valid_grant()
    _run_denial(seeded["grant"], TOOL_NAME, {"foo": "bar"})


def test_slice2_unknown_tool_rejected() -> None:
    seeded = _seed_slice2_valid_grant()
    _run_denial(seeded["grant"], "do_anything", {})


def test_slice2_forged_grant_rejected() -> None:
    _seed_slice2_valid_grant()
    forged = secrets.token_urlsafe(32)
    _run_denial(forged, TOOL_NAME, {})


def test_slice2_expired_grant_rejected() -> None:
    seeded = _seed_slice2_valid_grant()
    with db.transaction() as conn:
        conn.execute(
            text(
                "UPDATE mcp_question_grants SET expires_at = now()"
                " - interval '1 hour' WHERE grant_token = :grant"
            ),
            {"grant": seeded["grant"]},
        )
    _run_denial(seeded["grant"], TOOL_NAME, {})


def test_slice2_revoked_grant_rejected() -> None:
    seeded = _seed_slice2_valid_grant()
    with db.transaction() as conn:
        conn.execute(
            text(
                "UPDATE mcp_question_grants SET revoked_at = now()"
                " WHERE grant_token = :grant"
            ),
            {"grant": seeded["grant"]},
        )
    _run_denial(seeded["grant"], TOOL_NAME, {})


def test_slice2_altered_grant_projection_hash_rejected() -> None:
    seeded = _seed_slice2_valid_grant()
    with db.transaction() as conn:
        conn.execute(
            text(
                "UPDATE mcp_question_grants SET projection_hash = :tampered"
                " WHERE grant_token = :grant"
            ),
            {"tampered": "tampered-non-matching-hash", "grant": seeded["grant"]},
        )
    _run_denial(seeded["grant"], TOOL_NAME, {})


def test_slice2_rotated_stored_projection_hash_rejected() -> None:
    seeded = _seed_slice2_valid_grant()
    with db.transaction() as conn:
        conn.execute(
            text(
                "UPDATE run_questions SET projection_hash = :rotated"
                " WHERE id = :question_id"
            ),
            {"rotated": "rotated-after-grant-hash",
             "question_id": seeded["question_id"]},
        )
    _run_denial(seeded["grant"], TOOL_NAME, {})


def test_slice2_inactive_actor_rejected() -> None:
    seeded = _seed_slice2_valid_grant()
    with db.transaction() as conn:
        conn.execute(
            text("UPDATE users SET active = FALSE WHERE id = :actor_id"),
            {"actor_id": seeded["actor_id"]},
        )
    _run_denial(seeded["grant"], TOOL_NAME, {})


def test_slice2_deleted_actor_rejected() -> None:
    seeded = _seed_slice2_valid_grant()
    with db.transaction() as conn:
        conn.execute(
            text("DELETE FROM users WHERE id = :actor_id"),
            {"actor_id": seeded["actor_id"]},
        )
    _run_denial(seeded["grant"], TOOL_NAME, {})


# --- S41 slice 3 (RED): context isolation over the REAL transport (T6).
#
# FR-32-35, NFR-02. All tests drive REAL stdio subprocesses
# (`python -m x_insight.mcp_server` via `build_scoped_server_params` +
# real SDK `ClientSession`); never an in-process server call.
#
# INTENDED minimal host API assumed here (does NOT exist yet -> RED):
#   from x_insight.reasoning.mcp_host import stop_and_revoke
#   def stop_and_revoke(grant: str) -> None: ...
# Synchronously revokes one scoped context: UPDATE mcp_question_grants
# SET revoked_at = now() WHERE grant_token = :grant (idempotent, no
# return). The "stop" half is the caller exiting its `stdio_client`
# context (killing that grant's subprocess); the helper is the
# "revoke" half so the old grant fails safely on any later transport.
# The alternative name `close_scoped_session` was considered and is NOT
# used; backend must add exactly `stop_and_revoke`.
#
# EXPECTED RED: (a) importing `stop_and_revoke` fails (successive-
# context test); (b) the stderr/stdout separation test fails because
# denied calls return isError without emitting any stderr diagnostic
# (server only logs generic storage exceptions today).

_S3_AGE_A = 424241
_S3_AGE_B = 424242
_S3_NOTES_A = "synthetic-slice3-notes-alpha-8f2c-never-in-projection"
_S3_NOTES_B = "synthetic-slice3-notes-beta-9d4e-never-in-projection"
_S3_Q1_KEY = "synthetic_slice3_q1"
_S3_Q2_KEY = "synthetic_slice3_q2"
_S3_PATIENT_A_KEY = "synthetic_slice3_patient_a_q1"
_S3_PATIENT_B_KEY = "synthetic_slice3_patient_b_q1"


def _s3_projection(question_key: str, age_value: int) -> dict:
    return {
        "question_key": question_key,
        "network_version": 7,
        "variables": [
            {
                "node_id": "SyntheticSlice3Age",
                "status": "observed",
                "value": age_value,
                "source_ref": "snapshot.synthetic.slice3.age",
            },
            {
                "node_id": "SyntheticSlice3Condition",
                "status": "not_assessed",
                "value": None,
                "source_ref": "snapshot.synthetic.slice3.condition",
            },
        ],
        "synthetic_marker": "test-only fixture, never a released default",
    }


def _s3_insert_actor(conn: object, prefix: str) -> dict:
    username = f"synthetic-slice3-{prefix}-{secrets.token_hex(4)}"
    actor_id = conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO users (username, role, active, password_hash)"
            " VALUES (:username, 'physician', TRUE, 'synthetic')"
            " RETURNING id"
        ),
        {"username": username},
    ).scalar_one()
    return {"username": username, "actor_id": str(actor_id)}


def _s3_insert_patient_encounter(
    conn: object, actor_id: str, tag: str
) -> dict:
    patient_id_text = f"synthetic-slice3-{tag}-{secrets.token_hex(4)}"
    patient_id = conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO patients (patient_id_text, first_name, last_name,"
            " sex, age, clinical_status) VALUES (:pid_text, 'Syn',"
            " 'Thetic', 'F', 30, 'first_time') RETURNING id"
        ),
        {"pid_text": patient_id_text},
    ).scalar_one()
    encounter_id = conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO encounters (patient_id, kind, author_id, state)"
            " VALUES (:pid, 'registration', :author, 'draft') RETURNING id"
        ),
        {"pid": str(patient_id), "author": str(actor_id)},
    ).scalar_one()
    return {"patient_id": str(patient_id), "encounter_id": str(encounter_id)}


def _s3_insert_run_question_grant(
    conn: object,
    *,
    actor_id: str,
    encounter_id: str,
    question_key: str,
    age_value: int,
    projection_hash: str,
    snapshot_hash: str,
    ordinal: int = 0,
    run_id: object | None = None,
) -> dict:
    grant = secrets.token_urlsafe(32)
    if run_id is None:
        run_id = conn.execute(  # type: ignore[union-attr]
            text(
                "INSERT INTO runs (encounter_id, encounter_revision, workflow,"
                " snapshot, snapshot_hash, fingerprint, bundle_hash, pins,"
                " status) VALUES (:encounter_id, 1, 'synthetic',"
                " CAST(:snapshot AS jsonb), :snapshot_hash,"
                " 'synthetic-slice3-fingerprint',"
                " 'synthetic-slice3-bundle', CAST(:pins AS jsonb), 'queued')"
                " RETURNING id"
            ),
            {
                "encounter_id": str(encounter_id),
                "snapshot": json.dumps({"synthetic": "slice3"}),
                "snapshot_hash": snapshot_hash,
                "pins": json.dumps({"synthetic": True}),
            },
        ).scalar_one()
    question_id = conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO run_questions (run_id, question_key, ordinal,"
            " projection, projection_hash) VALUES (:run_id, :question_key,"
            " :ordinal, CAST(:projection AS jsonb), :projection_hash)"
            " RETURNING id"
        ),
        {
            "run_id": str(run_id),
            "question_key": question_key,
            "ordinal": ordinal,
            "projection": json.dumps(_s3_projection(question_key, age_value)),
            "projection_hash": projection_hash,
        },
    ).scalar_one()
    conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO mcp_question_grants (grant_token, run_id,"
            " run_question_id, question_key, actor_id, encounter_id,"
            " snapshot_hash, projection_hash, expires_at, revoked_at)"
            " VALUES (:grant, :run_id, :question_id, :question_key,"
            " :actor_id, :encounter_id, :snapshot_hash, :projection_hash,"
            " now() + interval '1 hour', NULL)"
        ),
        {
            "grant": grant,
            "run_id": str(run_id),
            "question_id": str(question_id),
            "question_key": question_key,
            "actor_id": str(actor_id),
            "encounter_id": str(encounter_id),
            "snapshot_hash": snapshot_hash,
            "projection_hash": projection_hash,
        },
    )
    return {
        "grant": grant,
        "run_id": str(run_id),
        "question_id": str(question_id),
    }


def _s3_seed_two_isolated_patients() -> dict:
    """Seed two synthetic patients/runs/questions/grants + notes rows."""
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, mcp_question_grants,"
                " run_questions, runs, encounters, patients, users"
            )
        )
        actor = _s3_insert_actor(conn, "iso")
        actor_id = actor["actor_id"]
        side_a = _s3_insert_patient_encounter(conn, actor_id, "patientA")
        side_b = _s3_insert_patient_encounter(conn, actor_id, "patientB")
        for encounter_id, notes_text in (
            (side_a["encounter_id"], _S3_NOTES_A),
            (side_b["encounter_id"], _S3_NOTES_B),
        ):
            conn.execute(
                text(
                    "INSERT INTO encounter_notes (encounter_id, page, text,"
                    " author_id, author_display) VALUES (:encounter_id,"
                    " 'history', :text, :author_id, :display)"
                ),
                {
                    "encounter_id": str(encounter_id),
                    "text": notes_text,
                    "author_id": str(actor_id),
                    "display": actor["username"],
                },
            )
        grant_a = _s3_insert_run_question_grant(
            conn,
            actor_id=actor_id,
            encounter_id=side_a["encounter_id"],
            question_key=_S3_PATIENT_A_KEY,
            age_value=_S3_AGE_A,
            projection_hash="synthetic-slice3-hash-patient-a",
            snapshot_hash="synthetic-slice3-snapshot-a",
        )
        grant_b = _s3_insert_run_question_grant(
            conn,
            actor_id=actor_id,
            encounter_id=side_b["encounter_id"],
            question_key=_S3_PATIENT_B_KEY,
            age_value=_S3_AGE_B,
            projection_hash="synthetic-slice3-hash-patient-b",
            snapshot_hash="synthetic-slice3-snapshot-b",
        )
    return {
        "grant_a": grant_a["grant"],
        "grant_b": grant_b["grant"],
        "encounter_a": side_a["encounter_id"],
        "encounter_b": side_b["encounter_id"],
    }


def _s3_seed_successive_questions() -> dict:
    """Seed one encounter/run with two questions Q1/Q2 + grants."""
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, mcp_question_grants,"
                " run_questions, runs, encounters, patients, users"
            )
        )
        actor = _s3_insert_actor(conn, "succ")
        actor_id = actor["actor_id"]
        base = _s3_insert_patient_encounter(conn, actor_id, "succ")
        encounter_id = base["encounter_id"]
        snapshot_hash = "synthetic-slice3-succ-snapshot"
        seeded_q1 = _s3_insert_run_question_grant(
            conn,
            actor_id=actor_id,
            encounter_id=encounter_id,
            question_key=_S3_Q1_KEY,
            age_value=_S3_AGE_A,
            projection_hash="synthetic-slice3-hash-q1",
            snapshot_hash=snapshot_hash,
            ordinal=0,
        )
        run_id = seeded_q1["run_id"]
        seeded_q2 = _s3_insert_run_question_grant(
            conn,
            actor_id=actor_id,
            encounter_id=encounter_id,
            question_key=_S3_Q2_KEY,
            age_value=_S3_AGE_B,
            projection_hash="synthetic-slice3-hash-q2",
            snapshot_hash=snapshot_hash,
            ordinal=1,
            run_id=run_id,
        )
    return {
        "grant_q1": seeded_q1["grant"],
        "grant_q2": seeded_q2["grant"],
        "encounter_id": encounter_id,
    }


def _s3_seed_notes_encounter() -> dict:
    """Seed one encounter with notes rows + bound run/question/grant."""
    notes_texts = [
        "synthetic-slice3-note-text-gamma-6a1e-never-in-projection",
        "synthetic-slice3-note-text-delta-7b2f-never-in-projection",
    ]
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, mcp_question_grants,"
                " run_questions, runs, encounters, patients, users"
            )
        )
        actor = _s3_insert_actor(conn, "notes")
        actor_id = actor["actor_id"]
        base = _s3_insert_patient_encounter(conn, actor_id, "notes")
        encounter_id = base["encounter_id"]
        for notes_text in notes_texts:
            conn.execute(
                text(
                    "INSERT INTO encounter_notes (encounter_id, page, text,"
                    " author_id, author_display) VALUES (:encounter_id,"
                    " 'history', :text, :author_id, :display)"
                ),
                {
                    "encounter_id": str(encounter_id),
                    "text": notes_text,
                    "author_id": str(actor_id),
                    "display": actor["username"],
                },
            )
        seeded = _s3_insert_run_question_grant(
            conn,
            actor_id=actor_id,
            encounter_id=encounter_id,
            question_key=_S3_Q1_KEY,
            age_value=_S3_AGE_A,
            projection_hash="synthetic-slice3-hash-notes",
            snapshot_hash="synthetic-slice3-snapshot-notes",
        )
    return {
        "grant": seeded["grant"],
        "encounter_id": encounter_id,
        "notes_texts": notes_texts,
    }


def _s3_parse_success_payload(result: object) -> dict:
    is_error = getattr(result, "is_error", False) or getattr(
        result, "isError", False
    )
    assert not is_error, f"expected success payload, got denial: {result!r}"
    content = getattr(result, "content", []) or []
    texts = [
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", "") == "text"
    ]
    assert len(texts) == 1
    return json.loads(texts[0])


def _s3_assert_safe_denial(result: object, must_not_contain: list[str]) -> None:
    is_error = getattr(result, "is_error", False) or getattr(
        result, "isError", False
    )
    assert is_error, f"expected SAFE denial (isError), got success: {result!r}"
    content = getattr(result, "content", []) or []
    texts = [
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", "") == "text"
    ]
    combined = "\n".join(texts)
    for marker in must_not_contain:
        assert marker not in combined, f"denial leaked {marker!r}"


def _s3_run_denial(grant: str, must_not_contain: list[str]) -> None:
    try:
        result = asyncio.run(_call_via_real_stdio(grant, TOOL_NAME, {}))
    except MCPError as exc:
        for marker in must_not_contain:
            assert marker not in str(exc)
        return
    except Exception as exc:
        if type(exc).__name__ in ("McpError", "MCPError"):
            for marker in must_not_contain:
                assert marker not in str(exc)
            return
        raise
    _s3_assert_safe_denial(result, must_not_contain)


async def _s3_read_one_via_real_stdio(grant: str) -> object:
    params = build_scoped_server_params(grant)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(TOOL_NAME, {})


def test_slice3_concurrent_patient_isolation() -> None:
    """Two live servers return only their own sentinel, no notes leak."""
    seeded = _s3_seed_two_isolated_patients()
    grant_a = seeded["grant_a"]
    grant_b = seeded["grant_b"]

    async def _concurrent_reads() -> tuple[object, object]:
        async def _read(grant: str) -> object:
            params = build_scoped_server_params(grant)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool(TOOL_NAME, {})

        return await asyncio.gather(_read(grant_a), _read(grant_b))

    result_a, result_b = asyncio.run(_concurrent_reads())
    payload_a = _s3_parse_success_payload(result_a)
    payload_b = _s3_parse_success_payload(result_b)

    assert payload_a["question_key"] == _S3_PATIENT_A_KEY
    assert payload_b["question_key"] == _S3_PATIENT_B_KEY
    blob_a = json.dumps(payload_a)
    blob_b = json.dumps(payload_b)
    # Each process returns ONLY its own sentinel.
    assert str(_S3_AGE_A) in blob_a
    assert str(_S3_AGE_B) not in blob_a
    assert str(_S3_AGE_B) in blob_b
    assert str(_S3_AGE_A) not in blob_b
    # NEITHER process output contains any notes text.
    for notes_text in (_S3_NOTES_A, _S3_NOTES_B):
        assert notes_text not in blob_a, "patient-A payload leaked notes"
        assert notes_text not in blob_b, "patient-B payload leaked notes"
    # Grants themselves never appear in the other payload.
    assert grant_a not in blob_b
    assert grant_b not in blob_a


def test_slice3_successive_question_rebinding_revokes_old() -> None:
    """Q1 read, stop/revoke Q1, Q2 reads Q2; old Q1 denied; stopped reuse fails."""
    # INTENDED host API (missing today -> RED ImportError).
    from x_insight.reasoning.mcp_host import stop_and_revoke

    seeded = _s3_seed_successive_questions()
    grant_q1 = seeded["grant_q1"]
    grant_q2 = seeded["grant_q2"]

    payload_q1 = _s3_parse_success_payload(
        asyncio.run(_s3_read_one_via_real_stdio(grant_q1))
    )
    assert payload_q1["question_key"] == _S3_Q1_KEY
    assert str(_S3_AGE_A) in json.dumps(payload_q1)

    # Stop/revoke the Q1 context (host revokes the grant row; the Q1
    # subprocess already exited when its `stdio_client` block closed).
    stop_and_revoke(grant_q1)

    payload_q2 = _s3_parse_success_payload(
        asyncio.run(_s3_read_one_via_real_stdio(grant_q2))
    )
    assert payload_q2["question_key"] == _S3_Q2_KEY
    assert str(_S3_AGE_B) in json.dumps(payload_q2)
    assert str(_S3_AGE_A) not in json.dumps(payload_q2)

    # Old Q1 grant now fails safely (revoked), leaking nothing.
    _s3_run_denial(grant_q1, [grant_q1, grant_q2, str(_S3_AGE_A)])

    # Reuse of a stopped session/client without a fresh grant cannot read.
    async def _stopped_reuse_fails() -> bool:
        params = build_scoped_server_params(grant_q2)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                ok = await session.call_tool(TOOL_NAME, {})
                assert not (
                    getattr(ok, "is_error", False)
                    or getattr(ok, "isError", False)
                )
                captured = session
        try:
            await captured.call_tool(TOOL_NAME, {})
        except Exception:
            return True
        return False

    assert asyncio.run(_stopped_reuse_fails()), (
        "stopped session reuse must not read without a fresh grant"
    )


def test_slice3_stderr_stdout_separation() -> None:
    """Denied call emits stderr diagnostics; stdout protocol still parses."""
    import tempfile

    seeded = _seed_slice2_valid_grant()
    grant = seeded["grant"]

    async def _denied_then_valid_on_one_transport(
        params: StdioServerParameters, errlog: object
    ) -> tuple[object, object, str]:
        async with stdio_client(params, errlog=errlog) as (read, write):  # type: ignore[arg-type]
            async with ClientSession(read, write) as session:
                await session.initialize()
                # Record end-of-startup position so the diagnostic below
                # must come from the denied call itself, not launch noise.
                errlog.flush()  # type: ignore[union-attr]
                errlog.seek(0, 2)  # type: ignore[union-attr]
                start = errlog.tell()  # type: ignore[union-attr]
                denied = await session.call_tool(TOOL_NAME, {"foo": "bar"})
                await asyncio.sleep(0.2)
                errlog.flush()  # type: ignore[union-attr]
                errlog.seek(start)  # type: ignore[union-attr]
                diagnostic = errlog.read()  # type: ignore[union-attr]
                valid = await session.call_tool(TOOL_NAME, {})
                return denied, valid, diagnostic

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errlog:
        params = build_scoped_server_params(grant)
        denied_result, valid_result, diagnostic = asyncio.run(
            _denied_then_valid_on_one_transport(params, errlog)
        )
    # Stdout protocol stream still parses: denial is a clean isError.
    _s3_assert_safe_denial(denied_result, [grant, str(_S2_SECRET_VALUE)])
    # Stderr bytes contain diagnostics for the denied call.
    assert diagnostic.strip() != "", "expected stderr diagnostic on denial"
    # Stdout JSON contains no diagnostic text: the later success payload
    # equals the stored projection shape and does not embed stderr bytes.
    payload = _s3_parse_success_payload(valid_result)
    assert set(payload) == {
        "question_key",
        "network_version",
        "projection_hash",
        "variables",
    }
    assert diagnostic.strip() not in json.dumps(payload)
    assert grant not in diagnostic, "stderr diagnostic leaked grant"


def test_slice3_notes_excluded_from_projection() -> None:
    """Encounter notes rows never appear in the returned projection."""
    seeded = _s3_seed_notes_encounter()
    grant = seeded["grant"]
    notes_texts = seeded["notes_texts"]
    result = asyncio.run(_s3_read_one_via_real_stdio(grant))
    payload = _s3_parse_success_payload(result)
    blob = json.dumps(payload)
    for notes_text in notes_texts:
        assert notes_text not in blob, "projection leaked encounter note text"
    lowered = blob.lower()
    assert "encounter_notes" not in lowered
    assert "note_text" not in lowered
    assert set(payload) == {
        "question_key",
        "network_version",
        "projection_hash",
        "variables",
    }


# --- S41 slice 4 (RED): bounded errors + cleanup over the REAL transport.
#
# FR-32-35, NFR-02, seam T6. All tests drive REAL stdio subprocesses
# (`python -m x_insight.mcp_server` via `build_scoped_server_params` +
# real SDK `ClientSession`); never an in-process server call.
#
# INTENDED minimal backend contract assumed here (missing today -> RED):
# * Oversized projection: the server reads env var
#   `X_INSIGHT_MCP_MAX_PROJECTION_BYTES` (decimal byte budget for the
#   serialized bound projection/payload). When the bound projection
#   exceeds it, `{}` returns a BOUNDED safe tool error: isError True,
#   exactly one text block equal to `projection too large` (small fixed
#   message, no truncation dump, no partial variables).
# * Database failure: `{}` returns a BOUNDED safe tool error quickly
#   (isError True, exactly `storage unavailable`, well under 30s, no
#   DSN/credentials/stack leak).
# * Transport failure/cleanup: terminating the live server mid-session
#   surfaces a clean transport error on the client (raises within a
#   bounded `asyncio.wait_for`, never hangs, never returns data); then
#   `stop_and_revoke(grant)` marks the grant revoked so a fresh server
#   with the same grant is safely denied.
#
# CURRENT state (read 2026-09-23): `mcp_server.py` has NO output-size
# bound constant/env var (oversized test fails red: server returns the
# full payload as success). It DOES have generic DB-failure handling
# (`except Exception -> "storage unavailable"`, stderr-only diagnostic),
# but its engine has no connect timeout, so unroutable hosts could hang;
# port-1 refusal is fast. Lease/deployment fencing is S47 scope and is
# NOT tested here.
#
# EXPECTED RED: at least the oversized-projection test fails red (success
# payload instead of the bounded isError).

_S4_MAX_BYTES_ENV = "X_INSIGHT_MCP_MAX_PROJECTION_BYTES"
_S4_TINY_BOUND = "64"
_S4_OVERSIZED_MESSAGE = "projection too large"
_S4_STORAGE_MESSAGE = "storage unavailable"
_S4_RPC_TIMEOUT_S = 20.0
_S4_DB_TIMEOUT_S = 25.0
_S4_KILL_OBSERVE_TIMEOUT_S = 10.0
_S4_PADDING_TOKEN = "synthetic-slice4-padding-6c9a-never-a-secret"
_S4_PADDING_VALUE = "P" * 4096


def _s4_seed_oversized_grant() -> dict:
    """Seed a valid-bound grant whose stored projection exceeds 64 bytes.

    Clearly labeled SYNTHETIC fixture (test-only, never a released
    default). Reuses the slice-2 valid grant, then widens its stored
    projection with a synthetic padding variable (inside `variables` so
    BOTH the stored row and the returned payload exceed any tiny bound)
    and rebinds the grant's projection_hash so the request reaches the
    size gate instead of failing on hash mismatch.
    """
    seeded = _seed_slice2_valid_grant()
    grant = seeded["grant"]
    question_id = seeded["question_id"]
    big_projection = {
        "question_key": _S2_QUESTION_KEY,
        "network_version": _S2_NETWORK_VERSION,
        "variables": [
            *_S2_VARIABLES,
            {
                "node_id": "SyntheticSlice4Padding",
                "status": "observed",
                "value": _S4_PADDING_VALUE,
                "source_ref": "snapshot.synthetic.slice4.padding",
            },
        ],
        "synthetic_marker": "test-only oversized fixture",
    }
    serialized = json.dumps(big_projection)
    assert len(serialized.encode("utf-8")) > int(_S4_TINY_BOUND)
    new_hash = f"synthetic-slice4-oversized-{secrets.token_hex(4)}"
    with db.transaction() as conn:
        conn.execute(
            text(
                "UPDATE run_questions SET projection ="
                " CAST(:projection AS jsonb), projection_hash = :hash"
                " WHERE id = :question_id"
            ),
            {
                "projection": serialized,
                "hash": new_hash,
                "question_id": str(question_id),
            },
        )
        conn.execute(
            text(
                "UPDATE mcp_question_grants SET projection_hash = :hash"
                " WHERE grant_token = :grant"
            ),
            {"hash": new_hash, "grant": grant},
        )
    return {"grant": grant, "projection_hash": new_hash}


async def _s4_call_with_extra_env(
    grant: str, extra_env: dict, timeout_s: float
) -> object:
    """Call `{}` on a REAL server whose subprocess env is extended."""
    params = build_scoped_server_params(grant)
    assert params.env is not None
    for key, value in extra_env.items():
        params.env[key] = value
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await asyncio.wait_for(
                session.call_tool(TOOL_NAME, {}), timeout_s
            )


def _s4_text_of(result: object) -> str:
    content = getattr(result, "content", []) or []
    texts = [
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", "") == "text"
    ]
    assert len(texts) == 1, f"expected exactly one text block: {result!r}"
    return texts[0]


def test_slice4_oversized_projection_bounded() -> None:
    """Tiny `X_INSIGHT_MCP_MAX_PROJECTION_BYTES=64` forces a safe bound."""
    seeded = _s4_seed_oversized_grant()
    grant = seeded["grant"]
    result = asyncio.run(
        _s4_call_with_extra_env(
            grant, {_S4_MAX_BYTES_ENV: _S4_TINY_BOUND}, _S4_RPC_TIMEOUT_S
        )
    )
    is_error = getattr(result, "is_error", False) or getattr(
        result, "isError", False
    )
    assert is_error, f"oversized projection must be denied: {result!r}"
    message = _s4_text_of(result)
    # Small FIXED message: exact contract, no dump, no partial variables.
    assert message.strip() == _S4_OVERSIZED_MESSAGE
    assert len(message) < 200
    for marker in (
        grant,
        str(_S2_SECRET_VALUE),
        _S2_SECRET_NODE,
        _S4_PADDING_TOKEN,
        _S4_PADDING_VALUE[:32],
        _S2_PROJECTION_HASH,
    ):
        assert marker not in message, f"bounded error leaked {marker[:24]!r}"
    lowered = message.lower()
    assert "variables" not in lowered
    assert _S4_PADDING_VALUE[:16].lower() not in lowered


def test_slice4_database_failure_bounded() -> None:
    """Unreachable DATABASE_URL (port 1) returns a fast safe error."""
    import time

    seeded = _seed_slice2_valid_grant()
    grant = seeded["grant"]
    unreachable = "postgresql://xinsight:xinsight_dev@localhost:1/xinsight_dev"
    started = time.monotonic()
    result = asyncio.run(
        _s4_call_with_extra_env(
            grant, {"DATABASE_URL": unreachable}, _S4_DB_TIMEOUT_S
        )
    )
    elapsed = time.monotonic() - started
    assert elapsed < 30.0, f"DB failure must complete quickly: {elapsed:.1f}s"
    is_error = getattr(result, "is_error", False) or getattr(
        result, "isError", False
    )
    assert is_error, f"DB failure must be a safe error: {result!r}"
    message = _s4_text_of(result)
    assert message.strip() == _S4_STORAGE_MESSAGE
    assert len(message) < 500
    lowered = message.lower()
    for marker in (
        grant,
        unreachable.lower(),
        "postgresql",
        "localhost:1",
        "xinsight_dev",
        str(_S2_SECRET_VALUE).lower(),
        _S2_SECRET_NODE.lower(),
        "traceback",
        "psycopg",
        "operationalerror",
    ):
        assert marker not in lowered, f"DB error leaked {marker!r}"


def _s4_list_mcp_server_pids() -> set:
    """Return PIDs whose cmdline runs the private MCP server (Linux)."""
    import os

    found: set = set()
    proc_root = "/proc"
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return found
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(
                f"/proc/{entry}/cmdline", "rb"
            ) as handle:
                cmdline = handle.read().decode(errors="ignore")
        except OSError:
            continue
        if "x_insight.mcp_server" in cmdline:
            found.add(int(entry))
    return found


def test_slice4_transport_kill_then_cleanup_revokes() -> None:
    """Kill a live server mid-session: client errors fast, revoke sticks.

    Lease/deployment fencing is S47 scope and is NOT asserted here; this
    test only proves process cleanup via `stop_and_revoke` denies reuse
    of the same grant on a FRESH server.
    """
    import os
    import signal

    from x_insight.reasoning.mcp_host import stop_and_revoke

    seeded = _seed_slice2_valid_grant()
    grant = seeded["grant"]

    async def _live_then_killed() -> None:
        params = build_scoped_server_params(grant)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                healthy = await asyncio.wait_for(
                    session.call_tool(TOOL_NAME, {}),
                    _S4_KILL_OBSERVE_TIMEOUT_S,
                )
                assert not (
                    getattr(healthy, "is_error", False)
                    or getattr(healthy, "isError", False)
                ), f"pre-kill read must succeed: {healthy!r}"
                targets = _s4_list_mcp_server_pids()
                assert targets, "expected a live MCP server subprocess"
                for pid in targets:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError):
                        continue
                await asyncio.sleep(0.5)
                remaining = _s4_list_mcp_server_pids() & targets
                for pid in remaining:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        continue
                # Post-kill call must ERROR cleanly (raise), not hang and
                # never return projection data.
                try:
                    outcome = await asyncio.wait_for(
                        session.call_tool(TOOL_NAME, {}),
                        _S4_KILL_OBSERVE_TIMEOUT_S,
                    )
                except Exception as exc:
                    blob = str(exc)
                    for marker in (grant, str(_S2_SECRET_VALUE)):
                        assert marker not in blob, "transport error leaked"
                    return
                raise AssertionError(
                    "killed server must not answer"
                    f" (got {'isError' if getattr(outcome, 'is_error', False) or getattr(outcome, 'isError', False) else 'success'}): {outcome!r}"
                )

    asyncio.run(_live_then_killed())

    # Cleanup half: revoke, verify the row, and prove a FRESH server with
    # the same grant is now safely denied.
    stop_and_revoke(grant)
    with db.transaction() as conn:
        revoked_at = conn.execute(
            text(
                "SELECT revoked_at FROM mcp_question_grants"
                " WHERE grant_token = :grant"
            ),
            {"grant": grant},
        ).scalar_one_or_none()
    assert revoked_at is not None, "stop_and_revoke must set revoked_at"
    _run_denial(grant, TOOL_NAME, {})
