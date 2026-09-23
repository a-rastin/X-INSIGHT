"""Question-scoped MCP grants (S41 slice 1)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Logical references only (no FOREIGN KEYs): TRUNCATE-safe like 0013/0014.
    # Application code maintains the run/question/actor/encounter references.
    op.create_table(
        "mcp_question_grants",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("grant_token", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("run_question_id", sa.Uuid(), nullable=True),
        sa.Column("question_key", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("encounter_id", sa.Uuid(), nullable=True),
        sa.Column("snapshot_hash", sa.Text(), nullable=True),
        sa.Column("projection_hash", sa.Text(), nullable=True),
        sa.Column("lease_token", sa.Text(), nullable=True),
        sa.Column(
            "deployment_generation",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("grant_token", name="uq_mcp_question_grants_token"),
    )


def downgrade() -> None:
    op.drop_table("mcp_question_grants")
