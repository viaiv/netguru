"""
ChatService tests for automatic provider/model fallback flow.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.services.attachment_context_service import AttachmentContextResolution
from app.services.chat_service import ChatService
from app.services.llm_client import LLMProviderError
from app.services.memory_service import MemoryContextResolution


class FakeChatDbSession:
    """Minimal async DB session stub for ChatService fallback tests."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flush_calls += 1
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                setattr(obj, "id", uuid4())

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


def patch_chat_primitives(
    *,
    monkeypatch: pytest.MonkeyPatch,
    conversation: SimpleNamespace,
) -> None:
    """Apply common dependency patches for ChatService unit tests."""

    async def _fake_get_owned_conversation(  # noqa: ANN202
        _self: ChatService, _conversation_id, _user_id
    ):
        return conversation

    async def _fake_load_history(  # noqa: ANN202
        _self: ChatService, _conversation_id
    ):
        return [{"role": "user", "content": "teste de fallback"}]

    async def _fake_resolve_attachment_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        conversation_id: UUID,  # noqa: ARG001
        content: str,
        attachment_document_ids,  # noqa: ANN001, ARG001
    ):
        return AttachmentContextResolution(content_for_agent=content)

    async def _fake_resolve_memory_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        content_for_agent: str,  # noqa: ARG001
        preferred_vendor: str | None = None,  # noqa: ARG001
        allow_vendor_prompt: bool = True,  # noqa: ARG001
    ):
        return MemoryContextResolution(
            entries=[],
            context_block=None,
            vendor_ambiguity_prompt=None,
            ambiguous_vendors=[],
        )

    async def _fake_increment_messages(_db, _user_id, _count=1):  # noqa: ANN001, ANN202
        return None

    monkeypatch.setattr(ChatService, "_get_owned_conversation", _fake_get_owned_conversation)
    monkeypatch.setattr(ChatService, "_load_history", _fake_load_history)
    monkeypatch.setattr(ChatService, "_resolve_attachment_context", _fake_resolve_attachment_context)
    monkeypatch.setattr(ChatService, "_resolve_memory_context", _fake_resolve_memory_context)
    monkeypatch.setattr(
        "app.services.chat_service.UsageTrackingService.increment_messages",
        _fake_increment_messages,
    )
    monkeypatch.setattr("app.services.chat_service.decrypt_api_key", lambda _value: "plain-key")
    monkeypatch.setattr("app.services.chat_service.get_agent_tools", lambda **_kwargs: [])
    monkeypatch.setattr(
        ChatService,
        "_fallback_delay_seconds",
        staticmethod(lambda _idx: 0.0),
    )


@pytest.mark.asyncio
async def test_chat_service_fallbacks_to_secondary_attempt_on_transient_llm_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Transient failure on primary attempt should switch to secondary provider/model.
    """
    fake_db = FakeChatDbSession()
    service = ChatService(fake_db)  # type: ignore[arg-type]
    conversation_id = uuid4()
    user_id = uuid4()
    attempted: list[tuple[str, str | None]] = []

    user = SimpleNamespace(
        id=user_id,
        llm_provider="openai",
        encrypted_api_key="encrypted",
    )
    conversation = SimpleNamespace(
        id=conversation_id,
        model_used="gpt-4o-mini",
        title="Conversa em andamento",
        updated_at=None,
    )

    patch_chat_primitives(monkeypatch=monkeypatch, conversation=conversation)

    async def _fake_build_attempt_chain(  # noqa: ANN202
        _self: ChatService,
        *,
        primary_provider: str,  # noqa: ARG001
        primary_api_key: str,  # noqa: ARG001
        primary_model: str | None,  # noqa: ARG001
        using_free_llm: bool,  # noqa: ARG001
    ):
        return [
            {
                "provider_name": "openai",
                "api_key": "primary-key",
                "model": "gpt-4o-mini",
                "source": "primary",
            },
            {
                "provider_name": "google",
                "api_key": "free-key",
                "model": "gemini-2.0-flash",
                "source": "fallback_free_primary",
            },
        ]

    class FakeNetworkEngineerAgent:
        def __init__(  # noqa: ANN003
            self,
            provider_name: str,
            api_key: str,  # noqa: ARG002
            model: str | None = None,
            tools=None,  # noqa: ANN001, ARG002
        ) -> None:
            attempted.append((provider_name, model))
            self._provider_name = provider_name

        async def stream_response(self, _messages):  # noqa: ANN001, ANN202
            if self._provider_name == "openai":
                raise LLMProviderError("Rate limit exceeded (429)")
            yield {"type": "text", "content": "fallback ok"}

    monkeypatch.setattr(ChatService, "_build_llm_attempt_chain", _fake_build_attempt_chain)
    monkeypatch.setattr(
        "app.services.chat_service.NetworkEngineerAgent",
        FakeNetworkEngineerAgent,
    )

    events: list[dict] = []
    async for event in service.process_user_message(
        user=user,
        conversation_id=conversation_id,
        content="teste de fallback",
    ):
        events.append(event)

    assert attempted == [
        ("openai", "gpt-4o-mini"),
        ("google", "gemini-2.0-flash"),
    ]
    stream_end = next(event for event in events if event["type"] == "stream_end")
    metadata = stream_end["metadata"]
    execution = metadata["llm_execution"]
    assert execution["selected_provider"] == "google"
    assert execution["selected_model"] == "gemini-2.0-flash"
    assert execution["fallback_triggered"] is True
    assert execution["attempt_count"] == 2
    assert execution["attempts"][0]["status"] == "failed_stream"
    assert execution["attempts"][1]["status"] == "success"
    assert any(event["type"] == "stream_chunk" and event["content"] == "fallback ok" for event in events)


@pytest.mark.asyncio
async def test_chat_service_does_not_fallback_on_non_eligible_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Non-eligible errors (invalid API key/config) must stop immediately.
    """
    fake_db = FakeChatDbSession()
    service = ChatService(fake_db)  # type: ignore[arg-type]
    conversation_id = uuid4()
    user_id = uuid4()
    attempted: list[tuple[str, str | None]] = []

    user = SimpleNamespace(
        id=user_id,
        llm_provider="openai",
        encrypted_api_key="encrypted",
    )
    conversation = SimpleNamespace(
        id=conversation_id,
        model_used="gpt-4o-mini",
        title="Conversa em andamento",
        updated_at=None,
    )

    patch_chat_primitives(monkeypatch=monkeypatch, conversation=conversation)

    async def _fake_build_attempt_chain(  # noqa: ANN202
        _self: ChatService,
        *,
        primary_provider: str,  # noqa: ARG001
        primary_api_key: str,  # noqa: ARG001
        primary_model: str | None,  # noqa: ARG001
        using_free_llm: bool,  # noqa: ARG001
    ):
        return [
            {
                "provider_name": "openai",
                "api_key": "primary-key",
                "model": "gpt-4o-mini",
                "source": "primary",
            },
            {
                "provider_name": "google",
                "api_key": "free-key",
                "model": "gemini-2.0-flash",
                "source": "fallback_free_primary",
            },
        ]

    class FakeNetworkEngineerAgent:
        def __init__(  # noqa: ANN003
            self,
            provider_name: str,
            api_key: str,  # noqa: ARG002
            model: str | None = None,
            tools=None,  # noqa: ANN001, ARG002
        ) -> None:
            attempted.append((provider_name, model))

        async def stream_response(self, _messages):  # noqa: ANN001, ANN202
            raise LLMProviderError("Invalid API key")
            if False:  # pragma: no cover - force async-generator semantics for the test double
                yield {}

    monkeypatch.setattr(ChatService, "_build_llm_attempt_chain", _fake_build_attempt_chain)
    monkeypatch.setattr(
        "app.services.chat_service.NetworkEngineerAgent",
        FakeNetworkEngineerAgent,
    )

    events: list[dict] = []
    async for event in service.process_user_message(
        user=user,
        conversation_id=conversation_id,
        content="teste de fallback",
    ):
        events.append(event)

    assert attempted == [("openai", "gpt-4o-mini")]
    assert any(event["type"] == "error" and event["code"] == "llm_error" for event in events)
    assert not any(event["type"] == "stream_end" for event in events)
    assert fake_db.rollback_calls == 1
