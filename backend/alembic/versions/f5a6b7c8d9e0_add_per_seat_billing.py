"""add per-seat billing columns to plans and subscriptions

Revision ID: f5a6b7c8d9e0
Revises: e2a3b4c5d6f7
Create Date: 2026-02-15 22:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f5a6b7c8d9e0"
down_revision = "e2a3b4c5d6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Plan: seat limits ---
    op.add_column(
        "plans",
        sa.Column(
            "max_members",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Seats included in base price",
        ),
    )
    op.add_column(
        "plans",
        sa.Column(
            "price_per_extra_seat_cents",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Price per extra seat in cents (informational)",
        ),
    )

    # --- Subscription: seat quantity ---
    op.add_column(
        "subscriptions",
        sa.Column(
            "seat_quantity",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Quantity billed on Stripe",
        ),
    )

    # --- Backfill plan defaults ---
    # team: 3 seats included, R$33/extra seat
    op.execute(
        "UPDATE plans SET max_members = 3, price_per_extra_seat_cents = 3300 "
        "WHERE name = 'team'"
    )
    # enterprise: 10 seats included, R$25/extra seat
    op.execute(
        "UPDATE plans SET max_members = 10, price_per_extra_seat_cents = 2500 "
        "WHERE name = 'enterprise'"
    )
    # solo and free stay at defaults (1 seat, 0 extra cost)


def downgrade() -> None:
    op.drop_column("subscriptions", "seat_quantity")
    op.drop_column("plans", "price_per_extra_seat_cents")
    op.drop_column("plans", "max_members")
