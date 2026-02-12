"""Add chat and RAG foundation tables

Revision ID: 9f1c2a7b6d44
Revises: 8e7b9c2f1a4d
Create Date: 2026-02-12 19:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f1c2a7b6d44"
down_revision: Union[str, Sequence[str], None] = "8e7b9c2f1a4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("model_used", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conversations_id"), "conversations", ["id"], unique=False)
    op.create_index("idx_conversations_user_id", "conversations", ["user_id"], unique=False)
    op.create_index(
        "idx_conversations_updated_at",
        "conversations",
        ["updated_at"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, comment="user|assistant|system"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_messages_role",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_id"), "messages", ["id"], unique=False)
    op.create_index(
        "idx_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index("idx_messages_created_at", "messages", ["created_at"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column(
            "file_type",
            sa.String(length=50),
            nullable=False,
            comment="pcap|pcapng|txt|conf|cfg|log|pdf",
        ),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            comment="uploaded|processing|completed|failed",
        ),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('uploaded', 'processing', 'completed', 'failed')",
            name="ck_documents_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_id"), "documents", ["id"], unique=False)
    op.create_index("idx_documents_user_id", "documents", ["user_id"], unique=False)
    op.create_index("idx_documents_type", "documents", ["file_type"], unique=False)
    op.create_index("idx_documents_status", "documents", ["status"], unique=False)

    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_embeddings_id"), "embeddings", ["id"], unique=False)
    op.create_index("idx_embeddings_user_id", "embeddings", ["user_id"], unique=False)
    op.create_index("idx_embeddings_document_id", "embeddings", ["document_id"], unique=False)
    op.create_index(
        "idx_embeddings_document_chunk",
        "embeddings",
        ["document_id", "chunk_index"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_embeddings_document_chunk", table_name="embeddings")
    op.drop_index("idx_embeddings_document_id", table_name="embeddings")
    op.drop_index("idx_embeddings_user_id", table_name="embeddings")
    op.drop_index(op.f("ix_embeddings_id"), table_name="embeddings")
    op.drop_table("embeddings")

    op.drop_index("idx_documents_status", table_name="documents")
    op.drop_index("idx_documents_type", table_name="documents")
    op.drop_index("idx_documents_user_id", table_name="documents")
    op.drop_index(op.f("ix_documents_id"), table_name="documents")
    op.drop_table("documents")

    op.drop_index("idx_messages_created_at", table_name="messages")
    op.drop_index("idx_messages_conversation_id_created_at", table_name="messages")
    op.drop_index(op.f("ix_messages_id"), table_name="messages")
    op.drop_table("messages")

    op.drop_index("idx_conversations_updated_at", table_name="conversations")
    op.drop_index("idx_conversations_user_id", table_name="conversations")
    op.drop_index(op.f("ix_conversations_id"), table_name="conversations")
    op.drop_table("conversations")
