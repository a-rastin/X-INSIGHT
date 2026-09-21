"""Physician account revisions (S04)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "theme", server_default=sa.text("'light'"))
    op.add_column(
        "users", sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
    )
    for name in ("actor_display", "target_display"):
        op.add_column("audit_events", sa.Column(name, sa.Text()))
    op.add_column(
        "audit_events",
        sa.Column(
            "details", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.add_column("audit_events", sa.Column("result_payload", JSONB()))
    op.add_column("audit_events", sa.Column("result_status", sa.Integer()))
    op.create_index(
        "ix_audit_command_key",
        "audit_events",
        ["actor_id", "operation", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_audit_command_key", table_name="audit_events")
    for name in (
        "actor_display",
        "target_display",
        "details",
        "result_payload",
        "result_status",
    ):
        op.drop_column("audit_events", name)
    op.drop_column("users", "revision")
    op.alter_column("users", "theme", server_default="'light'")
