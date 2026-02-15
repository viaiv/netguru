"""promo_pricing_solo

Revision ID: a7f3c9d2b1e4
Revises: e25b81a24073
Create Date: 2026-02-15 13:00:00.000000

Adiciona campos de promocao ao Plan e promo_applied ao Subscription.
Configura Solo com promo R$19,90 por 3 meses.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7f3c9d2b1e4"
down_revision: str = "e25b81a24073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

plans_table = sa.table(
    "plans",
    sa.column("name", sa.String),
    sa.column("promo_price_cents", sa.Integer),
    sa.column("promo_months", sa.Integer),
)


def upgrade() -> None:
    """Adiciona campos promo no Plan e Subscription, configura promo Solo."""
    # Plan: promo fields
    op.add_column("plans", sa.Column("promo_price_cents", sa.Integer(), nullable=True))
    op.add_column("plans", sa.Column("promo_months", sa.Integer(), nullable=True))
    op.add_column("plans", sa.Column("stripe_promo_coupon_id", sa.String(255), nullable=True))

    # Subscription: promo_applied flag
    op.add_column(
        "subscriptions",
        sa.Column("promo_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # Solo promo: R$19,90 por 3 meses
    op.execute(
        plans_table.update()
        .where(plans_table.c.name == "solo")
        .values(promo_price_cents=1990, promo_months=3)
    )


def downgrade() -> None:
    """Remove campos promo."""
    op.drop_column("subscriptions", "promo_applied")
    op.drop_column("plans", "stripe_promo_coupon_id")
    op.drop_column("plans", "promo_months")
    op.drop_column("plans", "promo_price_cents")
