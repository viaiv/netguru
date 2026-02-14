"""add network_memories table

Revision ID: d6f3b1c9a8e2
Revises: b1d4e7f8a2c3
Create Date: 2026-02-14 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d6f3b1c9a8e2"
down_revision: Union[str, Sequence[str], None] = "b1d4e7f8a2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create network_memories table with scope constraints and indices."""
    op.create_table(
        "network_memories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False, comment="global|site|device"),
        sa.Column("scope_name", sa.String(length=120), nullable=True),
        sa.Column("memory_key", sa.String(length=120), nullable=False),
        sa.Column("memory_value", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("ttl_seconds", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "scope IN ('global', 'site', 'device')",
            name="ck_network_memories_scope_valid",
        ),
        sa.CheckConstraint(
            "(scope = 'global' AND scope_name IS NULL) OR "
            "(scope IN ('site', 'device') AND scope_name IS NOT NULL)",
            name="ck_network_memories_scope_name_required",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_network_memories_id"), "network_memories", ["id"], unique=False)
    op.create_index(op.f("ix_network_memories_user_id"), "network_memories", ["user_id"], unique=False)
    op.create_index(op.f("ix_network_memories_scope_name"), "network_memories", ["scope_name"], unique=False)
    op.create_index(op.f("ix_network_memories_memory_key"), "network_memories", ["memory_key"], unique=False)
    op.create_index(op.f("ix_network_memories_expires_at"), "network_memories", ["expires_at"], unique=False)
    op.create_index(op.f("ix_network_memories_is_active"), "network_memories", ["is_active"], unique=False)
    op.create_index(
        "ix_network_memories_user_scope_lookup",
        "network_memories",
        ["user_id", "scope", "scope_name", "memory_key"],
        unique=False,
    )


def downgrade() -> None:
    """Drop network_memories table and its indices."""
    op.drop_index("ix_network_memories_user_scope_lookup", table_name="network_memories")
    op.drop_index(op.f("ix_network_memories_is_active"), table_name="network_memories")
    op.drop_index(op.f("ix_network_memories_expires_at"), table_name="network_memories")
    op.drop_index(op.f("ix_network_memories_memory_key"), table_name="network_memories")
    op.drop_index(op.f("ix_network_memories_scope_name"), table_name="network_memories")
    op.drop_index(op.f("ix_network_memories_user_id"), table_name="network_memories")
    op.drop_index(op.f("ix_network_memories_id"), table_name="network_memories")
    op.drop_table("network_memories")
