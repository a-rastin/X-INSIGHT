"""Draft persistence revision column (S07 slice 1)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "encounters",
        sa.Column(
            "draft_data",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_encounters_state",
        "encounters",
        "state IN ('draft','review_ready','signed','discarded')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_encounters_state", "encounters", type_="check")
    op.drop_column("encounters", "draft_data")
