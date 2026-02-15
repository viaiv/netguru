"""add GPT-5 family and o3-pro to llm_models catalog

Revision ID: e3f4a5b6c7d8
Revises: d9e0f1a2b3c4
Create Date: 2026-02-15 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4

# revision identifiers, used by Alembic.
revision = "e3f4a5b6c7d8"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    llm_models = sa.table(
        "llm_models",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("provider", sa.String),
        sa.column("model_id", sa.String),
        sa.column("display_name", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )

    # ----------------------------------------------------------------
    # 1. Reorder existing OpenAI models to make room for GPT-5 family
    # ----------------------------------------------------------------
    reorder = [
        ("gpt-4.1", 5),
        ("gpt-4.1-mini", 6),
        ("gpt-4.1-nano", 7),
        ("o3", 8),
        ("o4-mini", 10),
    ]
    for model_id, new_order in reorder:
        op.execute(
            llm_models.update()
            .where(
                sa.and_(
                    llm_models.c.provider == "openai",
                    llm_models.c.model_id == model_id,
                )
            )
            .values(sort_order=new_order)
        )

    # ----------------------------------------------------------------
    # 2. Insert GPT-5 family + o3-pro
    # ----------------------------------------------------------------
    new_models = [
        ("openai", "gpt-5.2", "GPT-5.2", 0),
        ("openai", "gpt-5.1", "GPT-5.1", 1),
        ("openai", "gpt-5", "GPT-5", 2),
        ("openai", "gpt-5-mini", "GPT-5 Mini", 3),
        ("openai", "gpt-5-nano", "GPT-5 Nano", 4),
        ("openai", "o3-pro", "o3-pro (reasoning)", 9),
    ]
    for provider, model_id, display_name, sort_order in new_models:
        op.execute(
            llm_models.insert().values(
                id=uuid4(),
                provider=provider,
                model_id=model_id,
                display_name=display_name,
                is_active=True,
                sort_order=sort_order,
            )
        )


def downgrade() -> None:
    llm_models = sa.table(
        "llm_models",
        sa.column("provider", sa.String),
        sa.column("model_id", sa.String),
        sa.column("sort_order", sa.Integer),
    )

    # Remove GPT-5 family + o3-pro
    for model_id in ("gpt-5.2", "gpt-5.1", "gpt-5", "gpt-5-mini", "gpt-5-nano", "o3-pro"):
        op.execute(
            llm_models.delete().where(
                sa.and_(
                    llm_models.c.provider == "openai",
                    llm_models.c.model_id == model_id,
                )
            )
        )

    # Restore original sort_order
    restore = [
        ("gpt-4.1", 0),
        ("gpt-4.1-mini", 1),
        ("gpt-4.1-nano", 2),
        ("o3", 3),
        ("o4-mini", 4),
    ]
    for model_id, old_order in restore:
        op.execute(
            llm_models.update()
            .where(
                sa.and_(
                    llm_models.c.provider == "openai",
                    llm_models.c.model_id == model_id,
                )
            )
            .values(sort_order=old_order)
        )
