"""Secondary plans, signed snapshots, and addenda (S49 slice 1)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Logical references only (no FOREIGN KEYs): TRUNCATE-safe like 0013/0019.
    # Revisioned physician secondary-plan text per encounter; the initial
    # proposal in run_proposals is never touched by secondary saves.
    op.create_table(
        "secondary_plan_revisions",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("encounter_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "encounter_id", "revision", name="uq_secondary_plan_encounter_revision"
        ),
    )
    op.create_index(
        "ix_secondary_plan_encounter_id", "secondary_plan_revisions", ["encounter_id"]
    )
    # One frozen snapshot per signed encounter (minimal in slice 1; full
    # freeze hardening is slice 3).
    op.create_table(
        "signed_snapshots",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("encounter_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("snapshot_hash", sa.Text(), nullable=False),
        sa.Column("signer_id", sa.Uuid(), nullable=True),
        sa.Column(
            "signed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("encounter_revision", sa.Integer(), nullable=True),
        sa.Column("secondary_plan_revision", sa.Integer(), nullable=True),
        sa.UniqueConstraint("encounter_id", name="uq_signed_snapshots_encounter_id"),
    )
    op.create_index(
        "ix_signed_snapshots_encounter_id", "signed_snapshots", ["encounter_id"]
    )
    # Attributed corrections to signed encounters (written in slice 4).
    op.create_table(
        "encounter_addenda",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("encounter_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correction_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_encounter_addenda_encounter_id", "encounter_addenda", ["encounter_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_encounter_addenda_encounter_id", table_name="encounter_addenda")
    op.drop_table("encounter_addenda")
    op.drop_index("ix_signed_snapshots_encounter_id", table_name="signed_snapshots")
    op.drop_table("signed_snapshots")
    op.drop_index(
        "ix_secondary_plan_encounter_id", table_name="secondary_plan_revisions"
    )
    op.drop_table("secondary_plan_revisions")
