"""Identity tables: users/sessions + singleton admin (S03)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "username", sa.Text(), nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "credential_revision",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("theme", sa.Text(), nullable=False, server_default="'light'"),
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
        sa.CheckConstraint("role IN ('admin','physician')", name="ck_users_role"),
        sa.CheckConstraint("theme IN ('light','dark')", name="ck_users_theme"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    # Singleton admin: only one row may carry role='admin'.
    op.execute("CREATE UNIQUE INDEX one_admin_only ON users (role) WHERE role = 'admin'")

    op.create_table(
        "sessions",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("csrf_token", sa.Text(), nullable=False),
        sa.Column("credential_revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("sessions")
    op.execute("DROP INDEX IF EXISTS one_admin_only")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
