"""Add role column to users for RBAC

Revision ID: 6c5b4b9f5f2b
Revises: e58580971ef4
Create Date: 2026-02-12 19:39:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6c5b4b9f5f2b"
down_revision: Union[str, Sequence[str], None] = "e58580971ef4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="member",
            comment="owner|admin|member|viewer",
        ),
    )
    op.alter_column("users", "role", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "role")
