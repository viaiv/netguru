"""add config_tools feature to plans

Revision ID: c9e5f2a1b3d4
Revises: b8d4e6f1c2a3
Create Date: 2026-02-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e5f2a1b3d4"
down_revision: Union[str, None] = "b8d4e6f1c2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adiciona config_tools: true ao features JSON de todos os planos."""
    # Usa jsonb_set para adicionar a chave sem sobrescrever features existentes.
    # plans.features e JSON; cast para jsonb, set, cast back.
    op.execute(
        """
        UPDATE plans
        SET features = (features::jsonb || '{"config_tools": true}'::jsonb)::json
        WHERE features IS NOT NULL
        """
    )
    # Planos sem features (NULL) — atribuir apenas config_tools
    op.execute(
        """
        UPDATE plans
        SET features = '{"config_tools": true}'::json
        WHERE features IS NULL
        """
    )


def downgrade() -> None:
    """Remove config_tools do features JSON dos planos."""
    op.execute(
        """
        UPDATE plans
        SET features = (features::jsonb - 'config_tools')::json
        WHERE features IS NOT NULL
          AND features::jsonb ? 'config_tools'
        """
    )
