"""add BYO-LLM discount columns to plans and subscriptions

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-02-15 23:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a6b7c8d9e0f1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plans: discount amount and Stripe coupon ID
    op.add_column(
        "plans",
        sa.Column(
            "byollm_discount_cents",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="BYO-LLM discount in cents (BRL)",
        ),
    )
    op.add_column(
        "plans",
        sa.Column(
            "stripe_byollm_coupon_id",
            sa.String(255),
            nullable=True,
            comment="Stripe Coupon ID for BYO-LLM discount",
        ),
    )

    # Subscriptions: whether BYO-LLM discount was applied
    op.add_column(
        "subscriptions",
        sa.Column(
            "byollm_discount_applied",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True if BYO-LLM coupon was applied at checkout",
        ),
    )

    # Backfill discount values for solo and team
    op.execute("UPDATE plans SET byollm_discount_cents = 1500 WHERE name = 'solo'")
    op.execute("UPDATE plans SET byollm_discount_cents = 4500 WHERE name = 'team'")


def downgrade() -> None:
    op.drop_column("subscriptions", "byollm_discount_applied")
    op.drop_column("plans", "stripe_byollm_coupon_id")
    op.drop_column("plans", "byollm_discount_cents")
