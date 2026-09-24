"""Restore commit metadata on recovery_jobs (S56 slice 1: commit gate).

Adds the columns the restore-commit flow stores on its ``kind='restore'``
rows: the pre-restore backup job id and the commit error text. All nullable
so S54/S55 rows are unaffected. Status CHECK is untouched: committing maps
to running observably via the manifest marker, committed maps to succeeded.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recovery_jobs", sa.Column("pre_restore_backup_id", sa.Text(), nullable=True)
    )
    op.add_column(
        "recovery_jobs", sa.Column("commit_error", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("recovery_jobs", "commit_error")
    op.drop_column("recovery_jobs", "pre_restore_backup_id")
