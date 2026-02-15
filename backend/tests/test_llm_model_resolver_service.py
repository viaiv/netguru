"""
Tests for LLMModelResolverService precedence rules.
"""
from __future__ import annotations

import pytest

from app.services.llm_model_resolver_service import LLMModelResolverService


@pytest.mark.asyncio
async def test_resolve_model_prefers_provider_specific_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider-specific setting must win over legacy/default values."""

    async def _fake_get(_db, key: str) -> str | None:  # noqa: ANN001
        values = {
            "llm_default_model_openai": "gpt-4.1",
            "free_llm_model": "gpt-4o-mini",
        }
        return values.get(key)

    monkeypatch.setattr(
        "app.services.llm_model_resolver_service.SystemSettingsService.get",
        _fake_get,
    )

    resolved = await LLMModelResolverService.resolve_model(
        db=None,  # type: ignore[arg-type]
        provider_name="openai",
        legacy_keys=("free_llm_model",),
    )
    assert resolved == "gpt-4.1"


@pytest.mark.asyncio
async def test_resolve_model_uses_legacy_when_provider_setting_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy key is used when provider-specific key is absent."""

    async def _fake_get(_db, key: str) -> str | None:  # noqa: ANN001
        values = {
            "free_llm_model": "gemini-2.0-flash",
        }
        return values.get(key)

    monkeypatch.setattr(
        "app.services.llm_model_resolver_service.SystemSettingsService.get",
        _fake_get,
    )

    resolved = await LLMModelResolverService.resolve_model(
        db=None,  # type: ignore[arg-type]
        provider_name="google",
        legacy_keys=("free_llm_model",),
    )
    assert resolved == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_resolve_model_falls_back_to_code_default_when_no_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Code default is returned when no DB setting exists."""

    async def _fake_get(_db, _key: str) -> str | None:  # noqa: ANN001
        return None

    monkeypatch.setattr(
        "app.services.llm_model_resolver_service.SystemSettingsService.get",
        _fake_get,
    )

    resolved = await LLMModelResolverService.resolve_model(
        db=None,  # type: ignore[arg-type]
        provider_name="deepseek",
    )
    assert resolved == LLMModelResolverService.default_model_for_provider("deepseek")


def test_default_model_for_unknown_provider_uses_google_default() -> None:
    """Unsupported provider slugs should fall back to Google defaults."""
    resolved = LLMModelResolverService.default_model_for_provider("unknown-provider")
    assert resolved == LLMModelResolverService.default_model_for_provider("google")

