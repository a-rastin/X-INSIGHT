"""Asynchronous full-backup jobs (S54 slice 1: create/poll/download).

One row per requested backup; the archive itself is built by a background
thread into the configured staging directory. No FOREIGN KEYs (TRUNCATE-safe
like 0013/0019/0021); replay uses the partial unique index below.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recovery_jobs",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.Text(), nullable=False, server_default="backup"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("request_hash", sa.Text(), nullable=True),
        sa.Column("archive_path", sa.Text(), nullable=True),
        sa.Column("manifest", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployment_generation", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_recovery_jobs_status",
        ),
    )
    op.create_index(
        "ix_recovery_jobs_idempotency",
        "recovery_jobs",
        ["created_by", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_recovery_jobs_idempotency", table_name="recovery_jobs")
    op.drop_table("recovery_jobs")
