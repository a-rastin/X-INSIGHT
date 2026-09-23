"""Assembled run proposals with pinned DDI (S46 slice 3)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Logical references only (no FOREIGN KEYs): TRUNCATE-safe like 0013/0014.
    # One row per run holding the assembled proposal (ordered sections,
    # skipped reasons) plus the pinned DDI report. Immutable once
    # succeeded: application code never overwrites a succeeded row; new
    # bundle activations use new runs only.
    op.create_table(
        "run_proposals",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("proposal", JSONB(), nullable=False),
        sa.Column("ddi_report", JSONB(), nullable=True),
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
        sa.UniqueConstraint("run_id", name="uq_run_proposals_run_id"),
    )
    op.create_index("ix_run_proposals_run_id", "run_proposals", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_run_proposals_run_id", table_name="run_proposals")
    op.drop_table("run_proposals")
