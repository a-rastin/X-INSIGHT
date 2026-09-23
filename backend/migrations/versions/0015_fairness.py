"""Fair scheduling state for queue rotation (S44 slice 3)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "queue_fairness",
        sa.Column("physician_id", sa.Uuid(), primary_key=True),
        sa.Column("last_granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "granted_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_table("queue_fairness")
