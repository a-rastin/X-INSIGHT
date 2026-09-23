"""Private read-only MCP server: question-scoped patient inputs.

S41 slice 1 (plan.md S8.2, MCP-design SS3-4, FR-32-35): launched by the
worker over private stdio (``python -m x_insight.mcp_server``); there is no
public listener. Exposes exactly one tool, ``get_question_patient_inputs``,
taking an empty object and returning the bound stored projection
(``question_key``, ``network_version``, ``projection_hash``,
``variables[]``) shaped from the persisted ``run_questions`` row.

Authorization: the opaque grant is read from the protected process
environment (:data:`x_insight.reasoning.mcp_host.MCP_GRANT_ENV_VAR`), never
from tool arguments. The server only issues SELECT statements against the
grant row and its bound question row; it never writes. Deployment must
configure the server's ``DATABASE_URL`` to a read-only database role; the
read-only posture here is that plus SELECT-only code.

Transport hygiene: MCP protocol bytes only on stdout; every diagnostic goes
to stderr.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

import mcp_types as types
from mcp.server.lowlevel.server import Server
from mcp.server.stdio import stdio_server
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from x_insight import db
from x_insight.reasoning.mcp_host import MCP_GRANT_ENV_VAR

TOOL_NAME = "get_question_patient_inputs"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

_ENGINE: Engine | None = None

_MAX_PROJECTION_BYTES_ENV = "X_INSIGHT_MCP_MAX_PROJECTION_BYTES"
_DEFAULT_MAX_PROJECTION_BYTES = 1_048_576
_OVERSIZED_MESSAGE = "projection too large"


def _max_projection_bytes() -> int:
    """Return the serialized-payload byte budget (env override or default)."""
    raw = os.environ.get(_MAX_PROJECTION_BYTES_ENV)
    if raw is None or not raw.strip():
        return _DEFAULT_MAX_PROJECTION_BYTES
    try:
        value = int(raw.strip(), 10)
    except ValueError:
        return _DEFAULT_MAX_PROJECTION_BYTES
    if value <= 0:
        return _DEFAULT_MAX_PROJECTION_BYTES
    return value


def _engine() -> Engine:
    """Return a cached engine for the server's database URL (reads only)."""
    global _ENGINE
    if _ENGINE is None:
        raw = db.database_url_for("app")
        url = (
            "postgresql+psycopg://" + raw[len("postgresql://") :]
            if raw.startswith("postgresql://")
            else raw
        )
        _ENGINE = create_engine(
            url, pool_pre_ping=True, connect_args={"connect_timeout": 5}
        )
    return _ENGINE


def _error_result(message: str) -> types.CallToolResult:
    """Return a safe tool error (never leaks grant or other-patient state)."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)],
        is_error=True,
    )


def _lookup_bound_projection(grant: str) -> dict[str, Any]:
    """Read the grant row and its bound stored projection (SELECT only)."""
    engine = _engine()
    with engine.connect() as conn:
        grant_row = (
            conn.execute(
                text(
                    "SELECT run_id, run_question_id, actor_id, snapshot_hash,"
                    " projection_hash, expires_at, revoked_at"
                    " FROM mcp_question_grants"
                    " WHERE grant_token = :grant"
                ),
                {"grant": grant},
            )
            .mappings()
            .first()
        )
        if grant_row is None or grant_row["run_question_id"] is None:
            raise LookupError("unknown or expired grant")
        if grant_row["revoked_at"] is not None:
            raise LookupError("unknown or expired grant")
        expires_at = grant_row["expires_at"]
        if expires_at is not None:
            exp = expires_at
            if not isinstance(exp, datetime):
                raise LookupError("unknown or expired grant")
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if exp <= datetime.now(UTC):
                raise LookupError("unknown or expired grant")
        stored = (
            conn.execute(
                text(
                    "SELECT run_id, question_key, projection, projection_hash"
                    " FROM run_questions WHERE id = :question_id"
                ),
                {"question_id": str(grant_row["run_question_id"])},
            )
            .mappings()
            .first()
        )
        if stored is None:
            raise LookupError("unknown or expired grant")
        grant_projection_hash = grant_row["projection_hash"]
        if (
            grant_projection_hash is not None
            and grant_projection_hash != stored["projection_hash"]
        ):
            raise LookupError("unknown or expired grant")
        grant_snapshot_hash = grant_row["snapshot_hash"]
        if grant_snapshot_hash is not None:
            run_row = (
                conn.execute(
                    text("SELECT snapshot_hash FROM runs WHERE id = :run_id"),
                    {"run_id": str(stored["run_id"])},
                )
                .mappings()
                .first()
            )
            if run_row is None or run_row["snapshot_hash"] != grant_snapshot_hash:
                raise LookupError("unknown or expired grant")
        actor_id = grant_row["actor_id"]
        if actor_id is not None:
            user_row = (
                conn.execute(
                    text("SELECT active FROM users WHERE id = :actor_id"),
                    {"actor_id": str(actor_id)},
                )
                .mappings()
                .first()
            )
            if user_row is None or user_row["active"] is not True:
                raise LookupError("unknown or expired grant")
        projection = stored["projection"]
        if not isinstance(projection, dict):
            raise LookupError("stored projection is unavailable")
        try:
            network_version = projection["network_version"]
            variables = projection["variables"]
        except KeyError as exc:
            raise LookupError("stored projection is unavailable") from exc
        return {
            "question_key": stored["question_key"],
            "network_version": network_version,
            "projection_hash": stored["projection_hash"],
            "variables": variables,
        }


async def _handle_list_tools(
    ctx: Any, params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    _ = (ctx, params)
    return types.ListToolsResult(
        tools=[
            types.Tool(
                name=TOOL_NAME,
                description=(
                    "Return the current question's represented patient "
                    "variables from the stored projection."
                ),
                input_schema=dict(INPUT_SCHEMA),
            )
        ]
    )


async def _handle_call_tool(
    ctx: Any, params: types.CallToolRequestParams
) -> types.CallToolResult:
    _ = ctx
    if params.name != TOOL_NAME:
        print("mcp_server: denied unknown_tool", file=sys.stderr, flush=True)
        return _error_result("unknown tool")
    if params.arguments:
        print("mcp_server: denied invalid_arguments", file=sys.stderr, flush=True)
        return _error_result("tool takes no arguments")
    grant = os.environ.get(MCP_GRANT_ENV_VAR)
    if not grant:
        print("mcp_server: denied grant_denied", file=sys.stderr, flush=True)
        return _error_result("unknown or expired grant")
    try:
        payload = _lookup_bound_projection(grant)
    except LookupError as exc:
        print("mcp_server: denied grant_denied", file=sys.stderr, flush=True)
        return _error_result(str(exc))
    except Exception:
        print(
            "mcp_server: storage lookup failed", file=sys.stderr, flush=True
        )
        return _error_result("storage unavailable")
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > _max_projection_bytes():
        print(
            "mcp_server: denied oversized_projection",
            file=sys.stderr,
            flush=True,
        )
        return _error_result(_OVERSIZED_MESSAGE)
    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=serialized),
        ]
    )


async def _serve() -> None:
    server = Server(
        "x-insight-mcp",
        on_list_tools=_handle_list_tools,
        on_call_tool=_handle_call_tool,
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main() -> None:
    """Run the private stdio server (protocol on stdout, logs on stderr)."""
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
