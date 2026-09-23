"""Lease expiry fencing attempts + deployment generation (S44 slice 4)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reasoning_attempts",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_index", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("error_details", JSONB(), nullable=True),
        sa.UniqueConstraint(
            "job_id", "attempt_index", name="uq_reasoning_attempts_job_index"
        ),
    )
    op.create_index("ix_reasoning_attempts_job_id", "reasoning_attempts", ["job_id"])
    op.execute(
        "ALTER TABLE reasoning_jobs ADD COLUMN IF NOT EXISTS "
        "deployment_generation INTEGER NOT NULL DEFAULT 1"
    )
    op.create_table(
        "deployment_state",
        sa.Column("id", sa.Integer(), primary_key=True, server_default=sa.text("1")),
        sa.Column(
            "generation",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.CheckConstraint("id = 1", name="ck_deployment_state_single_row"),
    )
    op.execute(
        "INSERT INTO deployment_state (id, generation) VALUES (1, 1) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("deployment_state")
    op.drop_index("ix_reasoning_attempts_job_id", table_name="reasoning_attempts")
    op.drop_table("reasoning_attempts")
    op.execute("ALTER TABLE reasoning_jobs DROP COLUMN IF EXISTS deployment_generation")
