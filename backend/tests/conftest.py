"""Isolated test lifecycle: migrated disposable test database per session."""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://xinsight:xinsight_dev@localhost:5432/xinsight_test",
)

# Force the application to use the disposable test database unless an
# individual test overrides DATABASE_URL (unavailable/incompatible cases).
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

_HERE = os.path.dirname(__file__)
_BACKEND_DIR = os.path.abspath(os.path.join(_HERE, ".."))


def _upgrade_test_db() -> None:
    cfg = Config(os.path.join(_BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_DIR, "migrations"))
    cfg.set_main_option(
        "sqlalchemy.url",
        TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://"),
    )
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _migrated_test_db() -> object:
    _upgrade_test_db()
    yield


@pytest.fixture(autouse=True)
def _isolate_audit_rows() -> object:
    from x_insight import db

    try:
        with db.transaction(TEST_DATABASE_URL) as conn:
            conn.execute(text("TRUNCATE audit_events"))
    except Exception:
        pass
    db.dispose_engines()
    yield
    db.dispose_engines()
