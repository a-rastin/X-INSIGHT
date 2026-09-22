"""Workflow bundle activation pointers and events (S24 slice 3)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_bundle_pointers",
        sa.Column(
            "workflow",
            sa.Text(),
            primary_key=True,
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("bundle_hash", sa.Text(), nullable=True),
        sa.Column("pins", JSONB(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "workflow IN ('registration', 'followup')",
            name="ck_model_bundle_pointers_workflow",
        ),
    )
    op.create_table(
        "model_bundle_events",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workflow", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("bundle_hash", sa.Text(), nullable=False),
        sa.Column("pins", JSONB(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "action IN ('activate', 'rollback')",
            name="ck_model_bundle_events_action",
        ),
        sa.UniqueConstraint(
            "workflow", "revision", name="uq_model_bundle_events_workflow_revision"
        ),
    )


def downgrade() -> None:
    op.drop_table("model_bundle_events")
    op.drop_table("model_bundle_pointers")
