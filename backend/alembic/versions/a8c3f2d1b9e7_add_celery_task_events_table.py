"""add celery_task_events table

Revision ID: a8c3f2d1b9e7
Revises: 594a4a87dbd1
Create Date: 2026-02-13 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a8c3f2d1b9e7'
down_revision: Union[str, Sequence[str], None] = '594a4a87dbd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create celery_task_events table with indices."""
    op.create_table(
        'celery_task_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('task_id', sa.String(length=255), nullable=False, comment='UUID atribuido pelo Celery'),
        sa.Column('task_name', sa.String(length=255), nullable=False, comment='Full dotted path da task'),
        sa.Column('status', sa.String(length=20), nullable=False, comment='STARTED|SUCCESS|FAILURE|RETRY'),
        sa.Column('args_summary', sa.String(length=500), nullable=True, comment='str(args)[:500] sanitizado'),
        sa.Column('result_summary', sa.String(length=500), nullable=True, comment='str(retval)[:500]'),
        sa.Column('error', sa.Text(), nullable=True, comment='Traceback completo (truncado a 2000 chars)'),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('duration_ms', sa.Float(), nullable=True),
        sa.Column('worker', sa.String(length=100), nullable=True, comment='Hostname do worker Celery'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_celery_task_events_id'), 'celery_task_events', ['id'], unique=False)
    op.create_index(op.f('ix_celery_task_events_task_id'), 'celery_task_events', ['task_id'], unique=False)
    op.create_index(op.f('ix_celery_task_events_task_name'), 'celery_task_events', ['task_name'], unique=False)
    op.create_index(op.f('ix_celery_task_events_status'), 'celery_task_events', ['status'], unique=False)
    op.create_index(op.f('ix_celery_task_events_started_at'), 'celery_task_events', ['started_at'], unique=False)


def downgrade() -> None:
    """Drop celery_task_events table."""
    op.drop_index(op.f('ix_celery_task_events_started_at'), table_name='celery_task_events')
    op.drop_index(op.f('ix_celery_task_events_status'), table_name='celery_task_events')
    op.drop_index(op.f('ix_celery_task_events_task_name'), table_name='celery_task_events')
    op.drop_index(op.f('ix_celery_task_events_task_id'), table_name='celery_task_events')
    op.drop_index(op.f('ix_celery_task_events_id'), table_name='celery_task_events')
    op.drop_table('celery_task_events')
