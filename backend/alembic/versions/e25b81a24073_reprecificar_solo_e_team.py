"""reprecificar_solo_e_team

Revision ID: e25b81a24073
Revises: f35b15860e40
Create Date: 2026-02-15 12:00:00.000000

Solo: R$79,00 -> R$49,90
Team: R$349,00 -> R$99,90
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e25b81a24073"
down_revision: str = "bbc424c7b63f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

plans_table = sa.table(
    "plans",
    sa.column("name", sa.String),
    sa.column("price_cents", sa.Integer),
)


def upgrade() -> None:
    """Atualiza precos: Solo R$49,90, Team R$99,90."""
    op.execute(
        plans_table.update()
        .where(plans_table.c.name == "solo")
        .values(price_cents=4990)
    )
    op.execute(
        plans_table.update()
        .where(plans_table.c.name == "team")
        .values(price_cents=9990)
    )


def downgrade() -> None:
    """Reverte para precos anteriores: Solo R$79,00, Team R$349,00."""
    op.execute(
        plans_table.update()
        .where(plans_table.c.name == "solo")
        .values(price_cents=7900)
    )
    op.execute(
        plans_table.update()
        .where(plans_table.c.name == "team")
        .values(price_cents=34900)
    )
