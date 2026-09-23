"""PostgreSQL connection lifecycle and readiness.

Roles are logical connection configurations, not separate physical users yet:
``app`` serves HTTP requests, ``migration`` runs Alembic, ``readonly`` is for
future read-only access (MCP worker, exports). Each reads its own env var and
falls back to ``DATABASE_URL`` so a single local role works in development;
production splits them by setting distinct URLs. No separate CREATE ROLE SQL
is added until tables requiring privilege separation land (first with S03/S06
domain tables); the audit table created in migration 0001 is the first
privilege-sensitive object.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

EXPECTED_SCHEMA_REVISION = "0021"

_DEFAULT_URL = "postgresql://xinsight:xinsight_dev@localhost:5432/xinsight_dev"

_ROLE_ENV_VARS = {
    "app": "DATABASE_URL",
    "migration": "MIGRATION_DATABASE_URL",
    "readonly": "READONLY_DATABASE_URL",
}

_engines: dict[str, Engine] = {}


class ReadinessError(Exception):
    """Database readiness failure with a public code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def database_url_for(role: str = "app") -> str:
    """Return the configured URL for a logical role."""
    env_var = _ROLE_ENV_VARS.get(role, "DATABASE_URL")
    fallback = os.environ.get("DATABASE_URL", _DEFAULT_URL)
    return os.environ.get(env_var, fallback)


def _sqlalchemy_url(raw: str) -> str:
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://") :]
    return raw


def get_engine(url: str | None = None) -> Engine:
    """Return a cached engine for the given URL (or the app role)."""
    key = url or database_url_for("app")
    engine = _engines.get(key)
    if engine is None:
        engine = create_engine(
            _sqlalchemy_url(key),
            pool_pre_ping=True,
            connect_args={"connect_timeout": 2},
        )
        _engines[key] = engine
    return engine


def dispose_engines() -> None:
    """Dispose cached engines (tests, process restart)."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()


def check_readiness(url: str | None = None) -> None:
    """Raise ReadinessError(UNAVAILABLE|INCOMPATIBLE_SCHEMA) when not ready."""
    dsn = url or database_url_for("app")
    try:
        with get_engine(dsn).connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise ReadinessError("UNAVAILABLE") from exc
    try:
        with get_engine(dsn).connect() as conn:
            version = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
    except Exception as exc:
        raise ReadinessError("INCOMPATIBLE_SCHEMA") from exc
    if version != EXPECTED_SCHEMA_REVISION:
        raise ReadinessError("INCOMPATIBLE_SCHEMA")


@contextmanager
def transaction(url: str | None = None) -> Iterator[Connection]:
    """Yield one transactional connection; callers commit/rollback together.

    Future command implementations share this context so the domain mutation
    and its audit row (see operations.audit.record_audit) commit atomically.
    """
    with get_engine(url).begin() as conn:
        yield conn
