"""Frozen run snapshots and per-question projections (S40 slice 1)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # encounter_id/patient_id/author_id/run_id stay logical references, not
    # database FOREIGN KEYs: disposable tests truncate encounters (and other
    # tables) without listing runs, and a formal FK would make that TRUNCATE
    # fail. Application code maintains the references.
    op.create_table(
        "runs",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("encounter_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("patient_id", sa.Uuid(), nullable=True),
        sa.Column("encounter_revision", sa.Integer(), nullable=False),
        sa.Column("workflow", sa.Text(), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("snapshot_hash", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("bundle_hash", sa.Text(), nullable=False),
        sa.Column("pins", JSONB(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
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
    )
    op.create_table(
        "run_questions",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("question_key", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("projection", JSONB(), nullable=False),
        sa.Column("projection_hash", sa.Text(), nullable=False),
    )
    op.create_index("ix_runs_encounter_id", "runs", ["encounter_id"])
    op.create_index("ix_run_questions_run_id", "run_questions", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_run_questions_run_id", table_name="run_questions")
    op.drop_index("ix_runs_encounter_id", table_name="runs")
    op.drop_table("run_questions")
    op.drop_table("runs")
