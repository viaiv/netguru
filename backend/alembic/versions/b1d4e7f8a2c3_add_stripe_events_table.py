"""add stripe_events table

Revision ID: b1d4e7f8a2c3
Revises: a8c3f2d1b9e7
Create Date: 2026-02-13 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1d4e7f8a2c3'
down_revision: Union[str, Sequence[str], None] = 'a8c3f2d1b9e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create stripe_events table with indices."""
    op.create_table(
        'stripe_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.String(length=255), nullable=False, comment='evt_xxx do Stripe'),
        sa.Column('event_type', sa.String(length=100), nullable=False, comment='checkout.session.completed|customer.subscription.updated|etc'),
        sa.Column('status', sa.String(length=20), nullable=False, comment='processed|failed|ignored'),
        sa.Column('customer_id', sa.String(length=255), nullable=True, comment='cus_xxx do Stripe'),
        sa.Column('subscription_id', sa.String(length=255), nullable=True, comment='sub_xxx do Stripe'),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('payload_summary', sa.String(length=500), nullable=True, comment='str(data)[:500] truncado'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_stripe_events_id'), 'stripe_events', ['id'], unique=False)
    op.create_index(op.f('ix_stripe_events_event_id'), 'stripe_events', ['event_id'], unique=True)
    op.create_index(op.f('ix_stripe_events_event_type'), 'stripe_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_stripe_events_status'), 'stripe_events', ['status'], unique=False)
    op.create_index(op.f('ix_stripe_events_user_id'), 'stripe_events', ['user_id'], unique=False)
    op.create_index(op.f('ix_stripe_events_created_at'), 'stripe_events', ['created_at'], unique=False)


def downgrade() -> None:
    """Drop stripe_events table."""
    op.drop_index(op.f('ix_stripe_events_created_at'), table_name='stripe_events')
    op.drop_index(op.f('ix_stripe_events_user_id'), table_name='stripe_events')
    op.drop_index(op.f('ix_stripe_events_status'), table_name='stripe_events')
    op.drop_index(op.f('ix_stripe_events_event_type'), table_name='stripe_events')
    op.drop_index(op.f('ix_stripe_events_event_id'), table_name='stripe_events')
    op.drop_index(op.f('ix_stripe_events_id'), table_name='stripe_events')
    op.drop_table('stripe_events')
