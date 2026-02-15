"""
LLMModelResolverService — resolve default model names per provider from system settings.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.system_settings_service import SystemSettingsService

if TYPE_CHECKING:
    from app.models.plan import Plan


class LLMModelResolverService:
    """
    Resolve model defaults for supported providers with DB-backed overrides.
    """

    PROVIDER_SETTING_KEYS: dict[str, str] = {
        "openai": "llm_default_model_openai",
        "anthropic": "llm_default_model_anthropic",
        "azure": "llm_default_model_azure",
        "google": "llm_default_model_google",
        "groq": "llm_default_model_groq",
        "deepseek": "llm_default_model_deepseek",
        "openrouter": "llm_default_model_openrouter",
    }

    @staticmethod
    def normalize_provider(provider_name: str | None, *, default: str = "google") -> str:
        """Return a supported provider slug (fallbacks to default)."""
        normalized = (provider_name or "").lower().strip()
        if normalized in LLMModelResolverService.PROVIDER_SETTING_KEYS:
            return normalized
        return default

    @staticmethod
    def default_model_for_provider(provider_name: str | None) -> str:
        """Return code-level provider default from app settings."""
        provider = LLMModelResolverService.normalize_provider(provider_name)
        mapping = {
            "openai": settings.DEFAULT_LLM_MODEL_OPENAI,
            "anthropic": settings.DEFAULT_LLM_MODEL_ANTHROPIC,
            "azure": settings.DEFAULT_LLM_MODEL_AZURE,
            "google": settings.DEFAULT_LLM_MODEL_GOOGLE,
            "groq": settings.DEFAULT_LLM_MODEL_GROQ,
            "deepseek": settings.DEFAULT_LLM_MODEL_DEEPSEEK,
            "openrouter": settings.DEFAULT_LLM_MODEL_OPENROUTER,
        }
        return mapping.get(provider, settings.DEFAULT_LLM_MODEL_GOOGLE)

    @staticmethod
    async def resolve_model(
        db: AsyncSession,
        provider_name: str | None,
        *,
        legacy_keys: tuple[str, ...] = (),
    ) -> str:
        """
        Resolve model for provider with precedence:
        1) provider-specific system setting
        2) legacy keys (optional)
        3) code default
        """
        provider = LLMModelResolverService.normalize_provider(provider_name)
        setting_key = LLMModelResolverService.PROVIDER_SETTING_KEYS.get(provider)
        if setting_key:
            value = await LLMModelResolverService._safe_get_setting(db, setting_key)
            if value and value.strip():
                return value.strip()

        for legacy_key in legacy_keys:
            value = await LLMModelResolverService._safe_get_setting(db, legacy_key)
            if value and value.strip():
                return value.strip()

        return LLMModelResolverService.default_model_for_provider(provider)

    @staticmethod
    async def resolve_plan_model(
        db: AsyncSession,
        plan: Plan,
    ) -> tuple[str, str] | None:
        """
        Resolve provider + model_id from the plan's default LLM model.

        Args:
            db: Async database session.
            plan: The Plan instance (may have default_llm_model_id set).

        Returns:
            (provider, model_id) or None if not configured / inactive.
        """
        if not plan.default_llm_model_id:
            return None

        from app.models.llm_model import LlmModel

        model = await db.get(LlmModel, plan.default_llm_model_id)
        if model and model.is_active:
            return (model.provider, model.model_id)
        return None

    @staticmethod
    async def _safe_get_setting(db: AsyncSession, key: str) -> str | None:
        try:
            return await SystemSettingsService.get(db, key)
        except Exception:
            return None

