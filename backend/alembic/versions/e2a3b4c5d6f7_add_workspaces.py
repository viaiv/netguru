"""add workspaces and workspace_members tables, backfill existing data

Revision ID: e2a3b4c5d6f7
Revises: d1f2a3b4c5e6
Create Date: 2026-02-15 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "e2a3b4c5d6f7"
down_revision: Union[str, None] = "d1f2a3b4c5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Passo 1: criar tabelas workspaces e workspace_members ──
    op.create_table(
        "workspaces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("plan_tier", sa.String(20), nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "workspace_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("workspace_role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("invited_by", UUID(as_uuid=True), nullable=True),
        sa.Column("joined_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )

    # ── Passo 2: backfill — criar workspace pessoal para cada user existente ──
    # Usa replace(uuid::text, '-', '') como slug para garantir unicidade
    op.execute(
        """
        INSERT INTO workspaces (id, name, slug, owner_id, plan_tier, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            u.email,
            replace(gen_random_uuid()::text, '-', ''),
            u.id,
            COALESCE(u.plan_tier, 'free'),
            u.created_at,
            NOW()
        FROM users u
        """
    )

    # Criar WorkspaceMember (role=owner) para cada user
    op.execute(
        """
        INSERT INTO workspace_members (id, workspace_id, user_id, workspace_role, joined_at)
        SELECT
            gen_random_uuid(),
            w.id,
            w.owner_id,
            'owner',
            w.created_at
        FROM workspaces w
        """
    )

    # ── Passo 3: adicionar active_workspace_id a users ──
    op.add_column(
        "users",
        sa.Column(
            "active_workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )

    # Popular active_workspace_id com workspace pessoal
    op.execute(
        """
        UPDATE users u
        SET active_workspace_id = w.id
        FROM workspaces w
        WHERE w.owner_id = u.id
        """
    )

    # ── Passo 4: adicionar workspace_id a tabelas de conteudo ──

    # -- subscriptions: add workspace_id, popular, drop user_id --
    op.add_column(
        "subscriptions",
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True, index=True),
    )
    op.execute(
        """
        UPDATE subscriptions s
        SET workspace_id = w.id
        FROM workspaces w
        WHERE w.owner_id = s.user_id
        """
    )
    op.alter_column("subscriptions", "workspace_id", nullable=False)
    op.create_foreign_key(
        "fk_subscriptions_workspace_id",
        "subscriptions",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("subscriptions_user_id_fkey", "subscriptions", type_="foreignkey")
    op.drop_column("subscriptions", "user_id")

    # -- documents: add workspace_id (nullable para docs globais) --
    op.add_column(
        "documents",
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True, index=True),
    )
    op.execute(
        """
        UPDATE documents d
        SET workspace_id = w.id
        FROM workspaces w
        WHERE w.owner_id = d.user_id
          AND d.user_id IS NOT NULL
        """
    )
    op.create_foreign_key(
        "fk_documents_workspace_id",
        "documents",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # -- embeddings: add workspace_id (nullable para docs globais) --
    op.add_column(
        "embeddings",
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True, index=True),
    )
    op.execute(
        """
        UPDATE embeddings e
        SET workspace_id = d.workspace_id
        FROM documents d
        WHERE d.id = e.document_id
          AND d.workspace_id IS NOT NULL
        """
    )
    op.create_foreign_key(
        "fk_embeddings_workspace_id",
        "embeddings",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # -- conversations: add workspace_id NOT NULL --
    op.add_column(
        "conversations",
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True, index=True),
    )
    op.execute(
        """
        UPDATE conversations c
        SET workspace_id = w.id
        FROM workspaces w
        WHERE w.owner_id = c.user_id
        """
    )
    op.alter_column("conversations", "workspace_id", nullable=False)
    op.create_foreign_key(
        "fk_conversations_workspace_id",
        "conversations",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # -- usage_metrics: add workspace_id NOT NULL, update unique constraint --
    op.add_column(
        "usage_metrics",
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True, index=True),
    )
    op.execute(
        """
        UPDATE usage_metrics um
        SET workspace_id = w.id
        FROM workspaces w
        WHERE w.owner_id = um.user_id
        """
    )
    op.alter_column("usage_metrics", "workspace_id", nullable=False)
    op.create_foreign_key(
        "fk_usage_metrics_workspace_id",
        "usage_metrics",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Drop old unique constraint and create new one
    op.drop_constraint("uq_usage_user_date", "usage_metrics", type_="unique")
    op.create_unique_constraint(
        "uq_usage_workspace_user_date",
        "usage_metrics",
        ["workspace_id", "user_id", "metric_date"],
    )

    # -- network_memories: add workspace_id NOT NULL --
    op.add_column(
        "network_memories",
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True, index=True),
    )
    op.execute(
        """
        UPDATE network_memories nm
        SET workspace_id = w.id
        FROM workspaces w
        WHERE w.owner_id = nm.user_id
        """
    )
    op.alter_column("network_memories", "workspace_id", nullable=False)
    op.create_foreign_key(
        "fk_network_memories_workspace_id",
        "network_memories",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # -- topologies: add workspace_id NOT NULL --
    op.add_column(
        "topologies",
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True, index=True),
    )
    op.execute(
        """
        UPDATE topologies t
        SET workspace_id = w.id
        FROM workspaces w
        WHERE w.owner_id = t.user_id
        """
    )
    op.alter_column("topologies", "workspace_id", nullable=False)
    op.create_foreign_key(
        "fk_topologies_workspace_id",
        "topologies",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # -- topologies --
    op.drop_constraint("fk_topologies_workspace_id", "topologies", type_="foreignkey")
    op.drop_column("topologies", "workspace_id")

    # -- network_memories --
    op.drop_constraint("fk_network_memories_workspace_id", "network_memories", type_="foreignkey")
    op.drop_column("network_memories", "workspace_id")

    # -- usage_metrics --
    op.drop_constraint("uq_usage_workspace_user_date", "usage_metrics", type_="unique")
    op.create_unique_constraint("uq_usage_user_date", "usage_metrics", ["user_id", "metric_date"])
    op.drop_constraint("fk_usage_metrics_workspace_id", "usage_metrics", type_="foreignkey")
    op.drop_column("usage_metrics", "workspace_id")

    # -- conversations --
    op.drop_constraint("fk_conversations_workspace_id", "conversations", type_="foreignkey")
    op.drop_column("conversations", "workspace_id")

    # -- embeddings --
    op.drop_constraint("fk_embeddings_workspace_id", "embeddings", type_="foreignkey")
    op.drop_column("embeddings", "workspace_id")

    # -- documents --
    op.drop_constraint("fk_documents_workspace_id", "documents", type_="foreignkey")
    op.drop_column("documents", "workspace_id")

    # -- subscriptions: restore user_id, drop workspace_id --
    op.add_column(
        "subscriptions",
        sa.Column("user_id", UUID(as_uuid=True), nullable=True, index=True),
    )
    op.execute(
        """
        UPDATE subscriptions s
        SET user_id = w.owner_id
        FROM workspaces w
        WHERE w.id = s.workspace_id
        """
    )
    op.alter_column("subscriptions", "user_id", nullable=False)
    op.create_foreign_key(
        "subscriptions_user_id_fkey",
        "subscriptions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("fk_subscriptions_workspace_id", "subscriptions", type_="foreignkey")
    op.drop_column("subscriptions", "workspace_id")

    # -- users.active_workspace_id --
    op.drop_column("users", "active_workspace_id")

    # -- workspace_members and workspaces --
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
