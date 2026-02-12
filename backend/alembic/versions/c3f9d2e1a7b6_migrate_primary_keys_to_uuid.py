"""Migrate primary and foreign keys from integer to UUID

Revision ID: c3f9d2e1a7b6
Revises: b42f9d17c8e1
Create Date: 2026-02-12 20:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3f9d2e1a7b6"
down_revision: Union[str, Sequence[str], None] = "b42f9d17c8e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_all_foreign_keys(table_name: str) -> None:
    """Drop every foreign key from a table to allow column swaps."""
    op.execute(
        f"""
        DO $$
        DECLARE
            fk_name text;
        BEGIN
            FOR fk_name IN
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = '{table_name}'::regclass
                  AND contype = 'f'
            LOOP
                EXECUTE format('ALTER TABLE {table_name} DROP CONSTRAINT %I', fk_name);
            END LOOP;
        END $$;
        """
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Add temporary UUID columns.
    op.add_column("users", sa.Column("id_uuid", sa.UUID(), nullable=True))

    op.add_column("conversations", sa.Column("id_uuid", sa.UUID(), nullable=True))
    op.add_column("conversations", sa.Column("user_id_uuid", sa.UUID(), nullable=True))

    op.add_column("messages", sa.Column("id_uuid", sa.UUID(), nullable=True))
    op.add_column("messages", sa.Column("conversation_id_uuid", sa.UUID(), nullable=True))

    op.add_column("documents", sa.Column("id_uuid", sa.UUID(), nullable=True))
    op.add_column("documents", sa.Column("user_id_uuid", sa.UUID(), nullable=True))

    op.add_column("embeddings", sa.Column("id_uuid", sa.UUID(), nullable=True))
    op.add_column("embeddings", sa.Column("user_id_uuid", sa.UUID(), nullable=True))
    op.add_column("embeddings", sa.Column("document_id_uuid", sa.UUID(), nullable=True))

    # Populate UUID primary keys.
    op.execute("UPDATE users SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL")
    op.execute("UPDATE conversations SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL")
    op.execute("UPDATE messages SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL")
    op.execute("UPDATE documents SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL")
    op.execute("UPDATE embeddings SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL")

    # Map all foreign keys to UUID columns.
    op.execute(
        """
        UPDATE conversations AS c
        SET user_id_uuid = u.id_uuid
        FROM users AS u
        WHERE c.user_id = u.id
        """
    )
    op.execute(
        """
        UPDATE messages AS m
        SET conversation_id_uuid = c.id_uuid
        FROM conversations AS c
        WHERE m.conversation_id = c.id
        """
    )
    op.execute(
        """
        UPDATE documents AS d
        SET user_id_uuid = u.id_uuid
        FROM users AS u
        WHERE d.user_id = u.id
        """
    )
    op.execute(
        """
        UPDATE embeddings AS e
        SET user_id_uuid = u.id_uuid
        FROM users AS u
        WHERE e.user_id = u.id
        """
    )
    op.execute(
        """
        UPDATE embeddings AS e
        SET document_id_uuid = d.id_uuid
        FROM documents AS d
        WHERE e.document_id = d.id
        """
    )

    # Required columns cannot be null.
    op.alter_column("users", "id_uuid", nullable=False)

    op.alter_column("conversations", "id_uuid", nullable=False)
    op.alter_column("conversations", "user_id_uuid", nullable=False)

    op.alter_column("messages", "id_uuid", nullable=False)
    op.alter_column("messages", "conversation_id_uuid", nullable=False)

    op.alter_column("documents", "id_uuid", nullable=False)
    op.alter_column("documents", "user_id_uuid", nullable=False)

    op.alter_column("embeddings", "id_uuid", nullable=False)

    # Remove constraints/indexes tied to integer columns.
    for table_name in ("conversations", "messages", "documents", "embeddings"):
        _drop_all_foreign_keys(table_name)

    op.drop_constraint("users_pkey", "users", type_="primary")
    op.drop_constraint("conversations_pkey", "conversations", type_="primary")
    op.drop_constraint("messages_pkey", "messages", type_="primary")
    op.drop_constraint("documents_pkey", "documents", type_="primary")
    op.drop_constraint("embeddings_pkey", "embeddings", type_="primary")

    op.execute("DROP INDEX IF EXISTS ix_users_id")
    op.execute("DROP INDEX IF EXISTS ix_conversations_id")
    op.execute("DROP INDEX IF EXISTS idx_conversations_user_id")
    op.execute("DROP INDEX IF EXISTS ix_messages_id")
    op.execute("DROP INDEX IF EXISTS idx_messages_conversation_id_created_at")
    op.execute("DROP INDEX IF EXISTS ix_documents_id")
    op.execute("DROP INDEX IF EXISTS idx_documents_user_id")
    op.execute("DROP INDEX IF EXISTS ix_embeddings_id")
    op.execute("DROP INDEX IF EXISTS idx_embeddings_user_id")
    op.execute("DROP INDEX IF EXISTS idx_embeddings_document_id")
    op.execute("DROP INDEX IF EXISTS idx_embeddings_document_chunk")

    # Swap old integer columns with UUID columns.
    op.alter_column("users", "id", new_column_name="id_int")
    op.alter_column("users", "id_uuid", new_column_name="id")

    op.alter_column("conversations", "id", new_column_name="id_int")
    op.alter_column("conversations", "id_uuid", new_column_name="id")
    op.alter_column("conversations", "user_id", new_column_name="user_id_int")
    op.alter_column("conversations", "user_id_uuid", new_column_name="user_id")

    op.alter_column("messages", "id", new_column_name="id_int")
    op.alter_column("messages", "id_uuid", new_column_name="id")
    op.alter_column("messages", "conversation_id", new_column_name="conversation_id_int")
    op.alter_column("messages", "conversation_id_uuid", new_column_name="conversation_id")

    op.alter_column("documents", "id", new_column_name="id_int")
    op.alter_column("documents", "id_uuid", new_column_name="id")
    op.alter_column("documents", "user_id", new_column_name="user_id_int")
    op.alter_column("documents", "user_id_uuid", new_column_name="user_id")

    op.alter_column("embeddings", "id", new_column_name="id_int")
    op.alter_column("embeddings", "id_uuid", new_column_name="id")
    op.alter_column("embeddings", "user_id", new_column_name="user_id_int")
    op.alter_column("embeddings", "user_id_uuid", new_column_name="user_id")
    op.alter_column("embeddings", "document_id", new_column_name="document_id_int")
    op.alter_column("embeddings", "document_id_uuid", new_column_name="document_id")

    # UUID defaults for new inserts.
    op.execute("ALTER TABLE users ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE conversations ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE messages ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE documents ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE embeddings ALTER COLUMN id SET DEFAULT gen_random_uuid()")

    # Restore primary keys.
    op.create_primary_key("users_pkey", "users", ["id"])
    op.create_primary_key("conversations_pkey", "conversations", ["id"])
    op.create_primary_key("messages_pkey", "messages", ["id"])
    op.create_primary_key("documents_pkey", "documents", ["id"])
    op.create_primary_key("embeddings_pkey", "embeddings", ["id"])

    # Restore foreign keys.
    op.create_foreign_key(
        "conversations_user_id_fkey",
        "conversations",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "messages_conversation_id_fkey",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "documents_user_id_fkey",
        "documents",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "embeddings_user_id_fkey",
        "embeddings",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "embeddings_document_id_fkey",
        "embeddings",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Rebuild indexes.
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_conversations_id", "conversations", ["id"], unique=False)
    op.create_index("idx_conversations_user_id", "conversations", ["user_id"], unique=False)
    op.create_index("ix_messages_id", "messages", ["id"], unique=False)
    op.create_index(
        "idx_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_documents_id", "documents", ["id"], unique=False)
    op.create_index("idx_documents_user_id", "documents", ["user_id"], unique=False)
    op.create_index("ix_embeddings_id", "embeddings", ["id"], unique=False)
    op.create_index("idx_embeddings_user_id", "embeddings", ["user_id"], unique=False)
    op.create_index("idx_embeddings_document_id", "embeddings", ["document_id"], unique=False)
    op.create_index(
        "idx_embeddings_document_chunk",
        "embeddings",
        ["document_id", "chunk_index"],
        unique=True,
    )

    # Remove backup integer columns.
    op.drop_column("conversations", "user_id_int")
    op.drop_column("messages", "conversation_id_int")
    op.drop_column("documents", "user_id_int")
    op.drop_column("embeddings", "user_id_int")
    op.drop_column("embeddings", "document_id_int")

    op.drop_column("users", "id_int")
    op.drop_column("conversations", "id_int")
    op.drop_column("messages", "id_int")
    op.drop_column("documents", "id_int")
    op.drop_column("embeddings", "id_int")

    # Cleanup legacy serial sequences if they remain.
    op.execute("DROP SEQUENCE IF EXISTS users_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS conversations_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS messages_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS documents_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS embeddings_id_seq")


def downgrade() -> None:
    """Downgrade schema."""
    raise RuntimeError(
        "Downgrade from UUID primary keys to integer IDs is not supported."
    )
