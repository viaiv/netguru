"""add_topologies_table

Revision ID: b8d4e6f1c2a3
Revises: a7f3c9d2b1e4
Create Date: 2026-02-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

# revision identifiers, used by Alembic.
revision: str = "b8d4e6f1c2a3"
down_revision: str = "a7f3c9d2b1e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria tabela topologies para persistir grafos de rede gerados."""
    op.create_table(
        "topologies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False, server_default="Topologia de rede"),
        sa.Column("source_type", sa.String(50), nullable=False, server_default="config"),
        sa.Column("nodes", JSON, nullable=False, server_default="[]"),
        sa.Column("edges", JSON, nullable=False, server_default="[]"),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("metadata", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Remove tabela topologies."""
    op.drop_table("topologies")
