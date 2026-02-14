"""add_free_plan_and_update_pricing_tiers

Revision ID: f35b15860e40
Revises: 241c1e02e98a
Create Date: 2026-02-14 15:13:14.466460

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

# revision identifiers, used by Alembic.
revision: str = 'f35b15860e40'
down_revision: Union[str, Sequence[str], None] = '241c1e02e98a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adiciona plano Free e atualiza precos/limites dos planos existentes."""
    plans_table = sa.table(
        "plans",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("display_name", sa.String),
        sa.column("price_cents", sa.Integer),
        sa.column("billing_period", sa.String),
        sa.column("upload_limit_daily", sa.Integer),
        sa.column("max_file_size_mb", sa.Integer),
        sa.column("max_conversations_daily", sa.Integer),
        sa.column("max_tokens_daily", sa.Integer),
        sa.column("features", JSON),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )

    # 1. Inserir plano Free
    op.bulk_insert(
        plans_table,
        [
            {
                "id": uuid4(),
                "name": "free",
                "display_name": "Free",
                "price_cents": 0,
                "billing_period": "monthly",
                "upload_limit_daily": 5,
                "max_file_size_mb": 25,
                "max_conversations_daily": 5,
                "max_tokens_daily": 10000,
                "features": {
                    "rag_global": True,
                    "rag_local": False,
                    "pcap_analysis": False,
                    "topology_generation": False,
                    "custom_tools": False,
                },
                "is_active": True,
                "sort_order": 0,
            },
        ],
    )

    # 2. Atualizar plano Solo: R$ 79/mes, limites ajustados
    op.execute(
        plans_table.update()
        .where(plans_table.c.name == "solo")
        .values(
            price_cents=7900,
            upload_limit_daily=20,
            max_file_size_mb=50,
            max_conversations_daily=50,
            max_tokens_daily=100000,
            sort_order=1,
            features=sa.text(
                """'{"rag_global": true, "rag_local": false, "pcap_analysis": true, "topology_generation": false, "custom_tools": false}'::json"""
            ),
        )
    )

    # 3. Atualizar plano Team: R$ 349/mes, limites ajustados
    op.execute(
        plans_table.update()
        .where(plans_table.c.name == "team")
        .values(
            price_cents=34900,
            upload_limit_daily=100,
            max_file_size_mb=100,
            max_conversations_daily=300,
            max_tokens_daily=500000,
            sort_order=2,
            features=sa.text(
                """'{"rag_global": true, "rag_local": true, "pcap_analysis": true, "topology_generation": true, "custom_tools": false}'::json"""
            ),
        )
    )

    # 4. Atualizar plano Enterprise: garantir features completas
    op.execute(
        plans_table.update()
        .where(plans_table.c.name == "enterprise")
        .values(
            upload_limit_daily=9999,
            max_file_size_mb=500,
            max_conversations_daily=9999,
            max_tokens_daily=9999999,
            sort_order=3,
            features=sa.text(
                """'{"rag_global": true, "rag_local": true, "pcap_analysis": true, "topology_generation": true, "custom_tools": true}'::json"""
            ),
        )
    )

    # 5. Atualizar comment de users.plan_tier
    op.alter_column(
        "users",
        "plan_tier",
        existing_type=sa.VARCHAR(length=20),
        comment="free|solo|team|enterprise",
        existing_comment="solo|team|enterprise",
        existing_nullable=False,
    )


def downgrade() -> None:
    """Reverte: remove plano free e restaura precos originais."""
    plans_table = sa.table(
        "plans",
        sa.column("name", sa.String),
        sa.column("price_cents", sa.Integer),
        sa.column("upload_limit_daily", sa.Integer),
        sa.column("max_file_size_mb", sa.Integer),
        sa.column("max_conversations_daily", sa.Integer),
        sa.column("max_tokens_daily", sa.Integer),
        sa.column("features", JSON),
        sa.column("sort_order", sa.Integer),
    )

    # Remover plano free
    op.execute(
        plans_table.delete().where(plans_table.c.name == "free")
    )

    # Restaurar Solo ao preco original
    op.execute(
        plans_table.update()
        .where(plans_table.c.name == "solo")
        .values(
            price_cents=2900,
            upload_limit_daily=10,
            max_file_size_mb=50,
            max_conversations_daily=30,
            max_tokens_daily=50000,
            sort_order=1,
            features=sa.text(
                """'{"rag_global": true, "rag_local": false, "pcap_analysis": true, "topology_generation": false}'::json"""
            ),
        )
    )

    # Restaurar Team ao preco original
    op.execute(
        plans_table.update()
        .where(plans_table.c.name == "team")
        .values(
            price_cents=19900,
            upload_limit_daily=100,
            max_file_size_mb=100,
            max_conversations_daily=200,
            max_tokens_daily=500000,
            sort_order=2,
            features=sa.text(
                """'{"rag_global": true, "rag_local": true, "pcap_analysis": true, "topology_generation": true}'::json"""
            ),
        )
    )

    # Restaurar comment
    op.alter_column(
        "users",
        "plan_tier",
        existing_type=sa.VARCHAR(length=20),
        comment="solo|team|enterprise",
        existing_comment="free|solo|team|enterprise",
        existing_nullable=False,
    )
