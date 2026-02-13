"""add email_logs table

Revision ID: 46b0f69aa27e
Revises: 7bf3da9f3cca
Create Date: 2026-02-13 17:11:04.866955

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '46b0f69aa27e'
down_revision: Union[str, Sequence[str], None] = '7bf3da9f3cca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'email_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('recipient_email', sa.String(length=255), nullable=False),
        sa.Column('recipient_user_id', sa.UUID(), nullable=True),
        sa.Column('email_type', sa.String(length=50), nullable=False,
                   comment='verification|password_reset|welcome|test'),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False,
                   comment='sent|failed|skipped'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['recipient_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_email_logs_created_at'), 'email_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_email_logs_email_type'), 'email_logs', ['email_type'], unique=False)
    op.create_index(op.f('ix_email_logs_id'), 'email_logs', ['id'], unique=False)
    op.create_index(op.f('ix_email_logs_recipient_email'), 'email_logs', ['recipient_email'], unique=False)
    op.create_index(op.f('ix_email_logs_recipient_user_id'), 'email_logs', ['recipient_user_id'], unique=False)
    op.create_index(op.f('ix_email_logs_status'), 'email_logs', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_email_logs_status'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_recipient_user_id'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_recipient_email'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_id'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_email_type'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_created_at'), table_name='email_logs')
    op.drop_table('email_logs')
