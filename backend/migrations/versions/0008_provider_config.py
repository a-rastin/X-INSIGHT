"""Provider configuration storage (S42 slices 1-4)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_configs",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("revision", sa.Integer(), nullable=False, unique=True),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("key_ciphertext", sa.Text(), nullable=True),
        sa.Column(
            "key_present",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "test_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'untested'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "test_status IN ('untested', 'verified', 'failed')",
            name="ck_provider_configs_test_status",
        ),
    )
    # The active pointer is a logical reference, not a database FOREIGN KEY:
    # the S42 contract truncates provider% tables one by one in disposable
    # tests, and a formal FK would make TRUNCATE of the referenced table fail.
    # Application code maintains the reference; the singleton CHECK remains.
    op.create_table(
        "provider_config_pointer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("active_config_id", sa.Uuid(), nullable=True),
        sa.Column("active_revision", sa.Integer(), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_provider_config_pointer_singleton"),
    )


def downgrade() -> None:
    op.drop_table("provider_config_pointer")
    op.drop_table("provider_configs")
