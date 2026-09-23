"""Append-only guard for audit events (S52 slice 3).

Row-level BEFORE UPDATE OR DELETE trigger: every UPDATE/DELETE on
audit_events raises, for all roles. INSERT and TRUNCATE (which fires no
row triggers, so test fixtures keep working) are unaffected.
"""

from __future__ import annotations

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_TRIGGER_FUNCTION = "audit_events_append_only_guard"
_TRIGGER_NAME = "audit_events_append_only"


def upgrade() -> None:
    op.execute(
        f"""CREATE OR REPLACE FUNCTION {_TRIGGER_FUNCTION}()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql"""
    )
    op.execute(
        f"""CREATE TRIGGER {_TRIGGER_NAME}
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION {_TRIGGER_FUNCTION}()"""
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON audit_events")
    op.execute(f"DROP FUNCTION IF EXISTS {_TRIGGER_FUNCTION}()")
