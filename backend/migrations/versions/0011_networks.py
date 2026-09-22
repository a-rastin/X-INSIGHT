"""Network registry storage (S24 slice 1: import/versioning)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "networks",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
    )
    # network_id is a logical reference, not a database FOREIGN KEY: the
    # S24 contract truncates network% tables one by one in disposable
    # tests, and a formal FK would make TRUNCATE of the referenced table
    # fail. Application code maintains the reference (see provider_config
    # pointer precedent); the UNIQUE(network_id, version) invariant stays
    # in the database.
    op.create_table(
        "network_versions",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("network_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("xml", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("xsd_report", JSONB(), nullable=False),
        sa.Column("semantic_report", JSONB(), nullable=False),
        sa.Column("admission_report", JSONB(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("network_id", "version", name="uq_network_versions_id_v"),
    )


def downgrade() -> None:
    op.drop_table("network_versions")
    op.drop_table("networks")
