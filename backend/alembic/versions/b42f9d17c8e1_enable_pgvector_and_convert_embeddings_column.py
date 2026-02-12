"""Enable pgvector and convert embeddings column to vector(384)

Revision ID: b42f9d17c8e1
Revises: 9f1c2a7b6d44
Create Date: 2026-02-12 19:58:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b42f9d17c8e1"
down_revision: Union[str, Sequence[str], None] = "9f1c2a7b6d44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("ALTER TABLE embeddings ADD COLUMN embedding_vector vector(384)")
    op.execute(
        """
        UPDATE embeddings
        SET embedding_vector = embedding::text::vector
        WHERE embedding IS NOT NULL
        """
    )
    op.execute("ALTER TABLE embeddings DROP COLUMN embedding")
    op.execute("ALTER TABLE embeddings RENAME COLUMN embedding_vector TO embedding")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_embeddings_vector_cosine
        ON embeddings USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE embeddings ADD COLUMN embedding_json JSON")
    op.execute(
        """
        UPDATE embeddings
        SET embedding_json = to_json(embedding::real[])
        WHERE embedding IS NOT NULL
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_embeddings_vector_cosine")
    op.execute("ALTER TABLE embeddings DROP COLUMN embedding")
    op.execute("ALTER TABLE embeddings RENAME COLUMN embedding_json TO embedding")
