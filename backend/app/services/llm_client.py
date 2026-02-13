"""
LLM provider abstraction for BYO-LLM architecture.

Supports OpenAI, Anthropic, and Azure OpenAI providers with
unified streaming interface.
"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator

from app.core.config import settings
from app.core.security import decrypt_api_key
from app.models.user import User


class LLMProviderError(Exception):
    """Base error for LLM provider operations."""
    pass


class BaseLLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat completion tokens.

        Args:
            messages: List of {"role": str, "content": str} dicts.
            model: Model name override.
            temperature: Sampling temperature override.
            max_tokens: Max output tokens override.

        Yields:
            Text chunks as they arrive from the provider.
        """
        ...  # pragma: no cover


class OpenAIProvider(BaseLLMProvider):
    """OpenAI chat completion provider."""

    def __init__(self, api_key: str) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise LLMProviderError("openai package not installed") from exc
        self._client = AsyncOpenAI(api_key=api_key)

    async def stream_chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        resolved_model = model or settings.DEFAULT_LLM_MODEL_OPENAI
        resolved_temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        resolved_max = max_tokens or settings.LLM_MAX_TOKENS

        try:
            stream = await self._client.chat.completions.create(
                model=resolved_model,
                messages=messages,
                temperature=resolved_temp,
                max_tokens=resolved_max,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:
            raise LLMProviderError(f"OpenAI error: {exc}") from exc


class AnthropicProvider(BaseLLMProvider):
    """Anthropic chat completion provider."""

    def __init__(self, api_key: str) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise LLMProviderError("anthropic package not installed") from exc
        self._client = AsyncAnthropic(api_key=api_key)

    async def stream_chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        resolved_model = model or settings.DEFAULT_LLM_MODEL_ANTHROPIC
        resolved_temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        resolved_max = max_tokens or settings.LLM_MAX_TOKENS

        # Anthropic requires system prompt separated from messages
        system_text = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"] + "\n"
            else:
                chat_messages.append({"role": msg["role"], "content": msg["content"]})

        try:
            async with self._client.messages.stream(
                model=resolved_model,
                messages=chat_messages,
                system=system_text.strip() or None,
                temperature=resolved_temp,
                max_tokens=resolved_max,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            raise LLMProviderError(f"Anthropic error: {exc}") from exc


class AzureOpenAIProvider(BaseLLMProvider):
    """Azure OpenAI chat completion provider."""

    def __init__(self, api_key: str) -> None:
        try:
            from openai import AsyncAzureOpenAI
        except ImportError as exc:
            raise LLMProviderError("openai package not installed") from exc

        if not settings.AZURE_OPENAI_ENDPOINT:
            raise LLMProviderError("AZURE_OPENAI_ENDPOINT not configured")

        self._client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version="2024-02-01",
        )

    async def stream_chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        resolved_model = model or settings.DEFAULT_LLM_MODEL_AZURE
        resolved_temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        resolved_max = max_tokens or settings.LLM_MAX_TOKENS

        try:
            stream = await self._client.chat.completions.create(
                model=resolved_model,
                messages=messages,
                temperature=resolved_temp,
                max_tokens=resolved_max,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:
            raise LLMProviderError(f"Azure OpenAI error: {exc}") from exc


_PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "azure": AzureOpenAIProvider,
}


def create_llm_provider(provider_name: str, api_key: str) -> BaseLLMProvider:
    """
    Factory to create an LLM provider instance.

    Args:
        provider_name: One of "openai", "anthropic", "azure".
        api_key: Plaintext API key.

    Returns:
        Configured provider instance.

    Raises:
        LLMProviderError: If provider is unsupported or key is missing.
    """
    provider_name = provider_name.lower().strip()
    provider_cls = _PROVIDERS.get(provider_name)
    if provider_cls is None:
        raise LLMProviderError(
            f"Unsupported provider '{provider_name}'. "
            f"Choose from: {', '.join(_PROVIDERS)}"
        )
    if not api_key:
        raise LLMProviderError("API key is required")
    return provider_cls(api_key=api_key)


def get_user_llm_provider(user: User) -> BaseLLMProvider:
    """
    Build an LLM provider from a user's stored configuration.

    Args:
        user: User with llm_provider and encrypted_api_key fields.

    Returns:
        Configured provider instance.

    Raises:
        LLMProviderError: If user has no provider/key configured.
    """
    if not user.llm_provider:
        raise LLMProviderError(
            "Nenhum provedor LLM configurado. "
            "Atualize seu perfil com llm_provider e api_key."
        )
    if not user.encrypted_api_key:
        raise LLMProviderError(
            "Nenhuma API key configurada. "
            "Atualize seu perfil com sua chave de API."
        )

    plaintext_key = decrypt_api_key(user.encrypted_api_key)
    return create_llm_provider(user.llm_provider, plaintext_key)
