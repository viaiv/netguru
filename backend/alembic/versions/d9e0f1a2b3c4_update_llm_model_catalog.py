"""update llm_models catalog with latest models per provider

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-02-15 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4

# revision identifiers, used by Alembic.
revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
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
    # 1. Remove outdated seed models
    # ----------------------------------------------------------------
    outdated = [
        ("openai", "gpt-4o"),
        ("openai", "gpt-4o-mini"),
        ("anthropic", "claude-sonnet-4-20250514"),
        ("anthropic", "claude-opus-4-20250514"),
        ("google", "gemini-2.0-flash"),
        ("google", "gemini-2.5-pro-preview-06-05"),
        ("groq", "llama-3.3-70b-versatile"),
        ("deepseek", "deepseek-chat"),
        ("openrouter", "google/gemini-2.0-flash-001"),
    ]
    for provider, model_id in outdated:
        op.execute(
            llm_models.delete().where(
                sa.and_(
                    llm_models.c.provider == provider,
                    llm_models.c.model_id == model_id,
                )
            )
        )

    # ----------------------------------------------------------------
    # 2. Insert current models (Feb 2026)
    # ----------------------------------------------------------------
    new_models = [
        # OpenAI — GPT-5 (latest generation)
        ("openai", "gpt-5.2", "GPT-5.2", 0),
        ("openai", "gpt-5.1", "GPT-5.1", 1),
        ("openai", "gpt-5", "GPT-5", 2),
        ("openai", "gpt-5-mini", "GPT-5 Mini", 3),
        ("openai", "gpt-5-nano", "GPT-5 Nano", 4),
        # OpenAI — GPT-4.1 (previous generation)
        ("openai", "gpt-4.1", "GPT-4.1", 5),
        ("openai", "gpt-4.1-mini", "GPT-4.1 Mini", 6),
        ("openai", "gpt-4.1-nano", "GPT-4.1 Nano", 7),
        # OpenAI — Reasoning (o-series)
        ("openai", "o3", "o3 (reasoning)", 8),
        ("openai", "o3-pro", "o3-pro (reasoning)", 9),
        ("openai", "o4-mini", "o4-mini (reasoning)", 10),
        # Anthropic
        ("anthropic", "claude-opus-4-6", "Claude Opus 4.6", 20),
        ("anthropic", "claude-sonnet-4-5-20250929", "Claude Sonnet 4.5", 21),
        ("anthropic", "claude-haiku-4-5-20251001", "Claude Haiku 4.5", 22),
        ("anthropic", "claude-opus-4-5-20251101", "Claude Opus 4.5", 23),
        # Google
        ("google", "gemini-2.5-pro", "Gemini 2.5 Pro", 30),
        ("google", "gemini-2.5-flash", "Gemini 2.5 Flash", 31),
        ("google", "gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite", 32),
        ("google", "gemini-3-pro-preview", "Gemini 3 Pro (Preview)", 33),
        ("google", "gemini-3-flash-preview", "Gemini 3 Flash (Preview)", 34),
        # Groq
        ("groq", "llama-3.3-70b-versatile", "Llama 3.3 70B", 40),
        ("groq", "llama-3.1-8b-instant", "Llama 3.1 8B Instant", 41),
        # DeepSeek
        ("deepseek", "deepseek-chat", "DeepSeek V3 Chat", 50),
        ("deepseek", "deepseek-reasoner", "DeepSeek R1 Reasoner", 51),
        # OpenRouter (popular cross-provider picks)
        ("openrouter", "anthropic/claude-sonnet-4.5", "Claude Sonnet 4.5 (OpenRouter)", 60),
        ("openrouter", "google/gemini-2.5-flash", "Gemini 2.5 Flash (OpenRouter)", 61),
        ("openrouter", "deepseek/deepseek-chat-v3-0324", "DeepSeek V3 Chat (OpenRouter)", 62),
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
    )

    # Remove new models
    new_model_ids = [
        ("openai", "gpt-4.1"),
        ("openai", "gpt-4.1-mini"),
        ("openai", "gpt-4.1-nano"),
        ("openai", "o3"),
        ("openai", "o4-mini"),
        ("anthropic", "claude-opus-4-6"),
        ("anthropic", "claude-sonnet-4-5-20250929"),
        ("anthropic", "claude-haiku-4-5-20251001"),
        ("anthropic", "claude-opus-4-5-20251101"),
        ("google", "gemini-2.5-pro"),
        ("google", "gemini-2.5-flash"),
        ("google", "gemini-2.5-flash-lite"),
        ("google", "gemini-3-pro-preview"),
        ("google", "gemini-3-flash-preview"),
        ("groq", "llama-3.3-70b-versatile"),
        ("groq", "llama-3.1-8b-instant"),
        ("deepseek", "deepseek-chat"),
        ("deepseek", "deepseek-reasoner"),
        ("openrouter", "anthropic/claude-sonnet-4.5"),
        ("openrouter", "google/gemini-2.5-flash"),
        ("openrouter", "deepseek/deepseek-chat-v3-0324"),
    ]
    for provider, model_id in new_model_ids:
        op.execute(
            llm_models.delete().where(
                sa.and_(
                    llm_models.c.provider == provider,
                    llm_models.c.model_id == model_id,
                )
            )
        )

    # Re-insert original seed models
    from uuid import uuid4 as _uuid4
    llm_insert = sa.table(
        "llm_models",
        sa.column("id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.column("provider", sa.String),
        sa.column("model_id", sa.String),
        sa.column("display_name", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    originals = [
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
    for provider, model_id, display_name, sort_order in originals:
        op.execute(
            llm_insert.insert().values(
                id=_uuid4(),
                provider=provider,
                model_id=model_id,
                display_name=display_name,
                is_active=True,
                sort_order=sort_order,
            )
        )
