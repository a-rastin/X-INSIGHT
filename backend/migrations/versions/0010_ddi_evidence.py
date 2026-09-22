"""DDI release evidence overlay (S18 slice 3: corrections, coverage, evidence).

Extends ``ddi_dataset_releases`` with three read-only-at-publish JSONB
columns. Sources are never modified; corrections apply as a management
overlay on duplicated evidence rows preserved verbatim.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ddi_dataset_releases",
        sa.Column(
            "corrections",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "ddi_dataset_releases",
        sa.Column("coverage", JSONB(), nullable=True),
    )
    op.add_column(
        "ddi_dataset_releases",
        sa.Column(
            "evidence", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column("ddi_dataset_releases", "evidence")
    op.drop_column("ddi_dataset_releases", "coverage")
    op.drop_column("ddi_dataset_releases", "corrections")
