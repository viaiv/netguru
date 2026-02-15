"""add allow_system_fallback feature to plans

Revision ID: d1f2a3b4c5e6
Revises: c9e5f2a1b3d4
Create Date: 2026-02-15 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1f2a3b4c5e6"
down_revision: Union[str, None] = "c9e5f2a1b3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adiciona allow_system_fallback ao features JSON dos planos.

    Politica:
    - free: allow_system_fallback=true (usuarios usam fallback sem API key)
    - solo: allow_system_fallback=true (BYO primario, fallback como backup)
    - team: allow_system_fallback=false (BYO obrigatorio, sem fallback)
    - enterprise: allow_system_fallback=false (BYO obrigatorio, sem fallback)
    """
    # Free e Solo: fallback permitido
    op.execute(
        """
        UPDATE plans
        SET features = (features::jsonb || '{"allow_system_fallback": true}'::jsonb)::json
        WHERE features IS NOT NULL
          AND name IN ('free', 'solo')
        """
    )

    # Team e Enterprise: fallback nao permitido (BYO obrigatorio)
    op.execute(
        """
        UPDATE plans
        SET features = (features::jsonb || '{"allow_system_fallback": false}'::jsonb)::json
        WHERE features IS NOT NULL
          AND name IN ('team', 'enterprise')
        """
    )

    # Planos sem features (NULL) — default conservador
    op.execute(
        """
        UPDATE plans
        SET features = '{"allow_system_fallback": false}'::json
        WHERE features IS NULL
        """
    )


def downgrade() -> None:
    """Remove allow_system_fallback do features JSON dos planos."""
    op.execute(
        """
        UPDATE plans
        SET features = (features::jsonb - 'allow_system_fallback')::json
        WHERE features IS NOT NULL
          AND features::jsonb ? 'allow_system_fallback'
        """
    )
