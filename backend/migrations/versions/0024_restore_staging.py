"""Restore staging metadata on recovery_jobs (S55 slice 1: validate/stage).

Adds the columns the restore-validation flow stores on its ``kind='restore'``
rows: the isolated staging path, the immutable confirmation digest, and the
staging expiry. All nullable so S54 backup rows are unaffected.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recovery_jobs", sa.Column("staging_path", sa.Text(), nullable=True))
    op.add_column(
        "recovery_jobs",
        sa.Column("confirmation_digest", sa.Text(), nullable=True),
    )
    op.add_column(
        "recovery_jobs",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recovery_jobs", "expires_at")
    op.drop_column("recovery_jobs", "confirmation_digest")
    op.drop_column("recovery_jobs", "staging_path")
