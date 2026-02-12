"""Bootstrap owner role for pre-RBAC user data

Revision ID: 8e7b9c2f1a4d
Revises: 6c5b4b9f5f2b
Create Date: 2026-02-12 19:43:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8e7b9c2f1a4d"
down_revision: Union[str, Sequence[str], None] = "6c5b4b9f5f2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            """
            UPDATE users
            SET role = 'owner'
            WHERE id = (
                SELECT id
                FROM users
                ORDER BY id ASC
                LIMIT 1
            )
            AND NOT EXISTS (
                SELECT 1
                FROM users
                WHERE role = 'owner'
            )
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Data migration rollback is intentionally a no-op.
    return None
