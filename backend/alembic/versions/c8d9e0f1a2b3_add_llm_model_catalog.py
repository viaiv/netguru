"""add llm_models catalog and plan.default_llm_model_id

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-02-15 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4

# revision identifiers, used by Alembic.
revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create llm_models table
    op.create_table(
        "llm_models",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model_id", sa.String(150), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "model_id", name="uq_llm_models_provider_model"),
    )
    op.create_index("ix_llm_models_id", "llm_models", ["id"])

    # 2. Add default_llm_model_id FK to plans
    op.add_column(
        "plans",
        sa.Column(
            "default_llm_model_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llm_models.id", ondelete="SET NULL"),
            nullable=True,
            comment="Default LLM model for this plan (from catalog)",
        ),
    )

    # 3. Seed catalog with common models
    llm_models = sa.table(
        "llm_models",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("provider", sa.String),
        sa.column("model_id", sa.String),
        sa.column("display_name", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )

    seeds = [
        ("openai", "gpt-4o", "GPT-4o", 0),
        ("openai", "gpt-4o-mini", "GPT-4o Mini", 1),
        ("anthropic", "claude-sonnet-4-20250514", "Claude Sonnet 4", 10),
        ("anthropic", "claude-opus-4-20250514", "Claude Opus 4", 11),
        ("google", "gemini-2.0-flash", "Gemini 2.0 Flash", 20),
        ("google", "gemini-2.5-pro-preview-06-05", "Gemini 2.5 Pro", 21),
        ("groq", "llama-3.3-70b-versatile", "Llama 3.3 70B", 30),
        ("deepseek", "deepseek-chat", "DeepSeek Chat", 40),
        ("openrouter", "google/gemini-2.0-flash-001", "Gemini 2.0 Flash (OpenRouter)", 50),
    ]

    for provider, model_id, display_name, sort_order in seeds:
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
    op.drop_column("plans", "default_llm_model_id")
    op.drop_index("ix_llm_models_id", table_name="llm_models")
    op.drop_table("llm_models")
