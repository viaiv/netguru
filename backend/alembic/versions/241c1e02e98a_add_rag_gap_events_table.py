"""add rag_gap_events table

Revision ID: 241c1e02e98a
Revises: f4b6c2d9e7a1
Create Date: 2026-02-14 12:00:00.000000

Rastreia queries RAG que nao retornaram documentacao relevante,
permitindo ao admin identificar lacunas e priorizar ingestion.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "241c1e02e98a"
down_revision: Union[str, Sequence[str], None] = "f4b6c2d9e7a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rag_gap_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tool_name", sa.String(50), nullable=False, index=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("gap_type", sa.String(30), nullable=False, index=True),
        sa.Column("result_preview", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("rag_gap_events")
