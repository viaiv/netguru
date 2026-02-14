"""add_trial_ends_at_to_users

Revision ID: bbc424c7b63f
Revises: f35b15860e40
Create Date: 2026-02-14 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "bbc424c7b63f"
down_revision: Union[str, Sequence[str], None] = "f35b15860e40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adiciona coluna trial_ends_at na tabela users."""
    op.add_column(
        "users",
        sa.Column("trial_ends_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Remove coluna trial_ends_at da tabela users."""
    op.drop_column("users", "trial_ends_at")
