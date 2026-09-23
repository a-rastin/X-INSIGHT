"""Per-question durable artifacts and rendered sections (S45 slice 1)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Logical references only (no FOREIGN KEYs): TRUNCATE-safe like 0013/0014.
    # One row per (run_id, question_key) holding every provenance piece for a
    # completed question: safe provider request, frozen projection, pinned
    # prompt, model/attempt provenance, accepted percentages, run-local
    # effective XML/hash, pinned query, posterior result, rendered section.
    op.create_table(
        "run_question_artifacts",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("question_key", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "stage",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'succeeded'"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'succeeded'"),
        ),
        sa.Column("request", JSONB(), nullable=False),
        sa.Column("projection", JSONB(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("model", JSONB(), nullable=False),
        sa.Column("accepted", JSONB(), nullable=False),
        sa.Column("effective_xml", sa.Text(), nullable=False),
        sa.Column("effective_hash", sa.Text(), nullable=False),
        sa.Column("query", JSONB(), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("rendered_section", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Text(), nullable=False),
        sa.Column("provenance", JSONB(), nullable=False),
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
            "run_id", "question_key", name="uq_run_question_artifacts_run_question"
        ),
    )
    op.create_index(
        "ix_run_question_artifacts_run_id", "run_question_artifacts", ["run_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_run_question_artifacts_run_id", table_name="run_question_artifacts"
    )
    op.drop_table("run_question_artifacts")
