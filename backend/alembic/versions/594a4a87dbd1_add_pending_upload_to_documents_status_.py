"""add pending_upload to documents status check

Revision ID: 594a4a87dbd1
Revises: f7a2b3c4d5e6
Create Date: 2026-02-13 18:26:20.563071

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '594a4a87dbd1'
down_revision: Union[str, Sequence[str], None] = 'f7a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adiciona 'pending_upload' ao CHECK constraint de status dos documentos."""
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_status",
        "documents",
        "status IN ('pending_upload', 'uploaded', 'processing', 'completed', 'failed')",
    )


def downgrade() -> None:
    """Remove 'pending_upload' do CHECK constraint de status dos documentos."""
    op.execute("DELETE FROM documents WHERE status = 'pending_upload'")
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_status",
        "documents",
        "status IN ('uploaded', 'processing', 'completed', 'failed')",
    )
