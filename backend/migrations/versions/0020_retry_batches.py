"""Manual retry batches and stage-resume partial artifacts (S47 slice 2)."""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE reasoning_jobs ADD COLUMN IF NOT EXISTS "
        "retry_batch INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE reasoning_jobs ADD COLUMN IF NOT EXISTS "
        "batch_start_attempt INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE reasoning_jobs ADD COLUMN IF NOT EXISTS "
        "failed_stage TEXT NULL"
    )
    for column in (
        "accepted",
        "effective_xml",
        "effective_hash",
        "query",
        "result",
        "rendered_section",
        "template_version",
    ):
        op.execute(
            f"ALTER TABLE run_question_artifacts ALTER COLUMN {column} DROP NOT NULL"
        )


def downgrade() -> None:
    for column in (
        "template_version",
        "rendered_section",
        "result",
        "query",
        "effective_hash",
        "effective_xml",
        "accepted",
    ):
        op.execute(
            f"ALTER TABLE run_question_artifacts ALTER COLUMN {column} SET NOT NULL"
        )
    op.execute("ALTER TABLE reasoning_jobs DROP COLUMN IF EXISTS failed_stage")
    op.execute("ALTER TABLE reasoning_jobs DROP COLUMN IF EXISTS batch_start_attempt")
    op.execute("ALTER TABLE reasoning_jobs DROP COLUMN IF EXISTS retry_batch")
