"""Follow-up linkage column (S14 slice 1)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "encounters",
        sa.Column("baseline_encounter_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("encounters", "baseline_encounter_id")
