"""Immutable DDI dataset releases (S18 slice 1: publish/import + list).

Only the release-provenance table lands here. Evidence and coverage
tables follow in slices 2-4.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ddi_dataset_releases",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("version", sa.Text(), nullable=False, unique=True),
        sa.Column("dataset_hash", sa.Text(), nullable=False),
        sa.Column("source_inventory", JSONB(), nullable=False),
        sa.Column("terminology_provenance", JSONB(), nullable=True),
        sa.Column("review_record", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("ddi_dataset_releases")
