"""Encounter page notes (S13 slice 1-2)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "encounter_notes",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("encounter_id", sa.Uuid(), nullable=False),
        sa.Column("page", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("author_display", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("char_length(page) > 0", name="ck_notes_page_nonempty"),
        sa.CheckConstraint("char_length(text) > 0", name="ck_notes_text_nonempty"),
        sa.ForeignKeyConstraint(
            ["encounter_id"], ["encounters.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_encounter_notes_encounter_created",
        "encounter_notes",
        ["encounter_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_encounter_notes_encounter_created", table_name="encounter_notes")
    op.drop_table("encounter_notes")
