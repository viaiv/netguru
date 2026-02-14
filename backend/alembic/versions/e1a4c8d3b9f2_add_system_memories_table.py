"""add system_memories table

Revision ID: e1a4c8d3b9f2
Revises: d6f3b1c9a8e2
Create Date: 2026-02-14 11:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e1a4c8d3b9f2"
down_revision: Union[str, Sequence[str], None] = "d6f3b1c9a8e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create system_memories table with scope constraints and indices."""
    op.create_table(
        "system_memories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False, comment="global|site|device"),
        sa.Column("scope_name", sa.String(length=120), nullable=True),
        sa.Column("memory_key", sa.String(length=120), nullable=False),
        sa.Column("memory_value", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("ttl_seconds", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "scope IN ('global', 'site', 'device')",
            name="ck_system_memories_scope_valid",
        ),
        sa.CheckConstraint(
            "(scope = 'global' AND scope_name IS NULL) OR "
            "(scope IN ('site', 'device') AND scope_name IS NOT NULL)",
            name="ck_system_memories_scope_name_required",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_system_memories_id"), "system_memories", ["id"], unique=False)
    op.create_index(op.f("ix_system_memories_scope_name"), "system_memories", ["scope_name"], unique=False)
    op.create_index(op.f("ix_system_memories_memory_key"), "system_memories", ["memory_key"], unique=False)
    op.create_index(op.f("ix_system_memories_expires_at"), "system_memories", ["expires_at"], unique=False)
    op.create_index(op.f("ix_system_memories_is_active"), "system_memories", ["is_active"], unique=False)
    op.create_index(op.f("ix_system_memories_created_by"), "system_memories", ["created_by"], unique=False)
    op.create_index(op.f("ix_system_memories_updated_by"), "system_memories", ["updated_by"], unique=False)
    op.create_index(
        "ix_system_memories_scope_lookup",
        "system_memories",
        ["scope", "scope_name", "memory_key"],
        unique=False,
    )


def downgrade() -> None:
    """Drop system_memories table and its indices."""
    op.drop_index("ix_system_memories_scope_lookup", table_name="system_memories")
    op.drop_index(op.f("ix_system_memories_updated_by"), table_name="system_memories")
    op.drop_index(op.f("ix_system_memories_created_by"), table_name="system_memories")
    op.drop_index(op.f("ix_system_memories_is_active"), table_name="system_memories")
    op.drop_index(op.f("ix_system_memories_expires_at"), table_name="system_memories")
    op.drop_index(op.f("ix_system_memories_memory_key"), table_name="system_memories")
    op.drop_index(op.f("ix_system_memories_scope_name"), table_name="system_memories")
    op.drop_index(op.f("ix_system_memories_id"), table_name="system_memories")
    op.drop_table("system_memories")
