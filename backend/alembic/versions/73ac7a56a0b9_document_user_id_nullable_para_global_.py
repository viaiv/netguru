"""document user_id nullable para global rag

Revision ID: 73ac7a56a0b9
Revises: c3f9d2e1a7b6
Create Date: 2026-02-13 02:45:40.857971

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73ac7a56a0b9'
down_revision: Union[str, Sequence[str], None] = 'c3f9d2e1a7b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('documents', 'user_id',
               existing_type=sa.UUID(),
               nullable=True,
               comment='NULL for global vendor docs')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('documents', 'user_id',
               existing_type=sa.UUID(),
               nullable=False,
               comment=None,
               existing_comment='NULL for global vendor docs')
