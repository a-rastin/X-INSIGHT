"""Durable leased question jobs, atomic first job (S44 slice 1)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Logical references only (no FOREIGN KEYs): TRUNCATE-safe like 0013.
    op.create_table(
        "reasoning_jobs",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("encounter_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("question_key", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "stage",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'preparing_question'"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("lease_token", sa.Text(), nullable=True),
        sa.Column("lease_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fencing_generation",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("failure_details", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "run_id", "question_key", name="uq_reasoning_jobs_run_question"
        ),
    )
    op.create_index("ix_reasoning_jobs_run_id", "reasoning_jobs", ["run_id"])
    op.create_index(
        "ix_reasoning_jobs_encounter_id", "reasoning_jobs", ["encounter_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_reasoning_jobs_encounter_id", table_name="reasoning_jobs")
    op.drop_index("ix_reasoning_jobs_run_id", table_name="reasoning_jobs")
    op.drop_table("reasoning_jobs")
