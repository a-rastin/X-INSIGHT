"""MCP host adapter: launch the private stdio server with a scoped grant.

S41 slice 1 (plan.md S8.2, MCP-design SS3-4): the worker (host/client)
spawns ``python -m x_insight.mcp_server`` as a private subprocess. The
short-lived opaque grant travels in the protected process environment
(:data:`MCP_GRANT_ENV_VAR`), never in command-line arguments. Only the
bound question's stored projection is ever readable through that process.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.client.stdio import StdioServerParameters
from sqlalchemy import text

from x_insight import db

MCP_GRANT_ENV_VAR = "X_INSIGHT_MCP_GRANT"


def build_scoped_server_params(grant: str) -> StdioServerParameters:
    """Return stdio launch parameters binding one grant to a fresh server.

    The environment merges the host process environment (so ``DATABASE_URL``
    reaches the test/deployed database) with the opaque grant entry. The
    grant token never appears in the argument vector.
    """
    env = dict(os.environ)
    env[MCP_GRANT_ENV_VAR] = grant
    env.setdefault("DATABASE_URL", db.database_url_for("app"))
    src_dir = Path(__file__).resolve().parents[2]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src_dir) + (os.pathsep + existing if existing else "")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "x_insight.mcp_server"],
        env=env,
    )


def stop_and_revoke(grant: str, database_url: str | None = None) -> None:
    """Revoke one scoped MCP grant idempotently (no-op when absent)."""
    with db.transaction(database_url) as conn:
        conn.execute(
            text(
                "UPDATE mcp_question_grants SET revoked_at = now(),"
                " updated_at = now() WHERE grant_token = :grant"
                " AND revoked_at IS NULL"
            ),
            {"grant": grant},
        )
