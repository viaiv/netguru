"""
ChatService integration tests for persistent memory context injection.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.services.attachment_context_service import (
    AttachmentContextResolution,
    ResolvedAttachment,
)
from app.services.chat_service import ChatService
from app.services.memory_service import AppliedMemory, MemoryContextResolution


class FakeChatDbSession:
    """Minimal async DB session stub for ChatService memory path tests."""

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


@pytest.mark.asyncio
async def test_chat_service_injects_memory_context_and_stream_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Memory context should be appended to agent history and exposed on stream_end metadata.
    """
    fake_db = FakeChatDbSession()
    service = ChatService(fake_db)  # type: ignore[arg-type]
    conversation_id = uuid4()
    user_id = uuid4()
    captured_history: dict[str, list[dict]] = {"value": []}

    user = SimpleNamespace(
        id=user_id,
        llm_provider="openai",
        encrypted_api_key="encrypted",
    )
    conversation = SimpleNamespace(
        id=conversation_id,
        model_used=None,
        title="Nova Conversa",
        updated_at=None,
    )

    async def _fake_get_owned_conversation(  # noqa: ANN202
        _self: ChatService, _conversation_id, _user_id
    ):
        return conversation

    async def _fake_load_history(  # noqa: ANN202
        _self: ChatService, _conversation_id
    ):
        return [{"role": "user", "content": "ajuste ospf"}]

    async def _fake_increment_messages(_db, _user_id, _count=1):  # noqa: ANN001, ANN202
        return None

    async def _fake_resolve_attachment_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        conversation_id: UUID,  # noqa: ARG001
        content: str,  # noqa: ARG001
        attachment_document_ids,  # noqa: ANN001, ARG001
    ):
        return AttachmentContextResolution(content_for_agent="ajuste ospf")

    async def _fake_resolve_memory_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        content_for_agent: str,  # noqa: ARG001
        preferred_vendor: str | None = None,  # noqa: ARG001
        allow_vendor_prompt: bool = True,  # noqa: ARG001
    ):
        entry = AppliedMemory(
            memory_id=uuid4(),
            origin="system",
            scope="system",
            scope_name=None,
            memory_key="asn",
            memory_value="65010",
            version=2,
            expires_at=datetime.utcnow(),
        )
        return MemoryContextResolution(
            entries=[entry],
            context_block=(
                "[MEMORIA_PERSISTENTE]\n"
                "- [system][system] asn: 65010\n"
                "[/MEMORIA_PERSISTENTE]"
            ),
        )

    class FakeNetworkEngineerAgent:
        def __init__(self, **_kwargs) -> None:  # noqa: ANN003
            pass

        async def stream_response(self, messages):  # noqa: ANN001, ANN202
            captured_history["value"] = messages
            yield {"type": "text", "content": "ok"}

    monkeypatch.setattr(ChatService, "_get_owned_conversation", _fake_get_owned_conversation)
    monkeypatch.setattr(ChatService, "_load_history", _fake_load_history)
    monkeypatch.setattr(ChatService, "_resolve_attachment_context", _fake_resolve_attachment_context)
    monkeypatch.setattr(ChatService, "_resolve_memory_context", _fake_resolve_memory_context)
    monkeypatch.setattr("app.services.chat_service.decrypt_api_key", lambda _value: "plain-key")
    monkeypatch.setattr("app.services.chat_service.get_agent_tools", lambda **_kwargs: [])
    monkeypatch.setattr(
        "app.services.chat_service.NetworkEngineerAgent",
        FakeNetworkEngineerAgent,
    )
    monkeypatch.setattr(
        "app.services.chat_service.UsageTrackingService.increment_messages",
        _fake_increment_messages,
    )

    events: list[dict] = []
    async for event in service.process_user_message(
        user=user,
        conversation_id=conversation_id,
        content="ajuste ospf",
    ):
        events.append(event)

    assert captured_history["value"]
    assert "[MEMORIA_PERSISTENTE]" in captured_history["value"][-1]["content"]
    assert "[system][system] asn: 65010" in captured_history["value"][-1]["content"]

    stream_end = next(e for e in events if e["type"] == "stream_end")
    assert "metadata" in stream_end
    assert stream_end["metadata"]["memory_context"]["applied_count"] == 1
    assert stream_end["metadata"]["memory_context"]["entries"][0]["memory_key"] == "asn"


@pytest.mark.asyncio
async def test_chat_service_serializes_evidence_and_confidence_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Assistant metadata should expose evidence items and confidence breakdown for UI rendering.
    """
    fake_db = FakeChatDbSession()
    service = ChatService(fake_db)  # type: ignore[arg-type]
    conversation_id = uuid4()
    user_id = uuid4()

    user = SimpleNamespace(
        id=user_id,
        llm_provider="openai",
        encrypted_api_key="encrypted",
    )
    conversation = SimpleNamespace(
        id=conversation_id,
        model_used=None,
        title="Nova Conversa",
        updated_at=None,
    )

    async def _fake_get_owned_conversation(  # noqa: ANN202
        _self: ChatService, _conversation_id, _user_id
    ):
        return conversation

    async def _fake_increment_messages(_db, _user_id, _count=1):  # noqa: ANN001, ANN202
        return None

    async def _fake_load_history(  # noqa: ANN202
        _self: ChatService, _conversation_id
    ):
        return [{"role": "user", "content": "como habilitar autenticacao ospf?"}]

    async def _fake_resolve_attachment_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        conversation_id: UUID,  # noqa: ARG001
        content: str,  # noqa: ARG001
        attachment_document_ids,  # noqa: ANN001, ARG001
    ):
        return AttachmentContextResolution(
            content_for_agent="como habilitar autenticacao ospf?",
            resolved_attachment=ResolvedAttachment(
                document_id=uuid4(),
                filename="core-sw-01-running.cfg",
                file_type="cfg",
                source="explicit",
            ),
        )

    async def _fake_resolve_memory_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        content_for_agent: str,  # noqa: ARG001
        preferred_vendor: str | None = None,  # noqa: ARG001
        allow_vendor_prompt: bool = True,  # noqa: ARG001
    ):
        entry = AppliedMemory(
            memory_id=uuid4(),
            origin="system",
            scope="system",
            scope_name=None,
            memory_key="ospf_auth_profile",
            memory_value="message-digest",
            version=1,
            expires_at=datetime.utcnow(),
        )
        return MemoryContextResolution(
            entries=[entry],
            context_block=(
                "[MEMORIA_PERSISTENTE]\n"
                "- [system][system] ospf_auth_profile: message-digest\n"
                "[/MEMORIA_PERSISTENTE]"
            ),
        )

    class FakeNetworkEngineerAgent:
        def __init__(self, **_kwargs) -> None:  # noqa: ANN003
            pass

        async def stream_response(self, _messages):  # noqa: ANN001, ANN202
            yield {
                "type": "tool_call_start",
                "tool_call_id": "tc-1",
                "tool_name": "search_rag_global",
                "tool_input": "ospf message-digest authentication ios",
            }
            yield {
                "type": "tool_call_end",
                "tool_call_id": "tc-1",
                "tool_name": "search_rag_global",
                "result_preview": "Cisco IOS supports area-level and interface-level OSPF MD5.",
                "duration_ms": 124,
            }
            yield {"type": "text", "content": "Use autenticacao OSPF MD5 na interface de uplink."}

    monkeypatch.setattr(ChatService, "_get_owned_conversation", _fake_get_owned_conversation)
    monkeypatch.setattr(ChatService, "_load_history", _fake_load_history)
    monkeypatch.setattr(ChatService, "_resolve_attachment_context", _fake_resolve_attachment_context)
    monkeypatch.setattr(ChatService, "_resolve_memory_context", _fake_resolve_memory_context)
    monkeypatch.setattr("app.services.chat_service.decrypt_api_key", lambda _value: "plain-key")
    monkeypatch.setattr("app.services.chat_service.get_agent_tools", lambda **_kwargs: [])
    monkeypatch.setattr(
        "app.services.chat_service.NetworkEngineerAgent",
        FakeNetworkEngineerAgent,
    )
    monkeypatch.setattr(
        "app.services.chat_service.UsageTrackingService.increment_messages",
        _fake_increment_messages,
    )

    events: list[dict] = []
    async for event in service.process_user_message(
        user=user,
        conversation_id=conversation_id,
        content="como habilitar autenticacao ospf?",
    ):
        events.append(event)

    stream_end = next(e for e in events if e["type"] == "stream_end")
    metadata = stream_end["metadata"]
    evidence = metadata["evidence"]
    confidence = metadata["confidence"]

    assert evidence["total_count"] == 3
    assert evidence["strong_count"] == 1
    assert evidence["medium_count"] == 1
    assert evidence["weak_count"] == 1
    assert confidence["score"] >= 55
    assert confidence["level"] in {"medium", "high"}
    assert "heuristics" in confidence
    assert any("tool call" in reason for reason in confidence["reasons"])

    tool_item = next(item for item in evidence["items"] if item["type"] == "tool_call")
    assert tool_item["source"] == "search_rag_global"
    assert tool_item["details"]["output"]


@pytest.mark.asyncio
async def test_chat_service_requests_vendor_confirmation_when_memory_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    ChatService should ask vendor confirmation and skip LLM call when memory is vendor-ambiguous.
    """
    fake_db = FakeChatDbSession()
    service = ChatService(fake_db)  # type: ignore[arg-type]
    conversation_id = uuid4()
    user_id = uuid4()

    user = SimpleNamespace(
        id=user_id,
        llm_provider="openai",
        encrypted_api_key="encrypted",
    )
    conversation = SimpleNamespace(
        id=conversation_id,
        model_used=None,
        title="Nova Conversa",
        updated_at=None,
    )

    async def _fake_get_owned_conversation(  # noqa: ANN202
        _self: ChatService, _conversation_id, _user_id
    ):
        return conversation

    async def _fake_increment_messages(_db, _user_id, _count=1):  # noqa: ANN001, ANN202
        return None

    async def _fake_load_history(  # noqa: ANN202
        _self: ChatService, _conversation_id
    ):
        return [{"role": "user", "content": "descricao de uplink"}]

    async def _fake_resolve_attachment_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        conversation_id: UUID,  # noqa: ARG001
        content: str,  # noqa: ARG001
        attachment_document_ids,  # noqa: ANN001, ARG001
    ):
        return AttachmentContextResolution(content_for_agent="descricao de uplink para RTR002")

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
            vendor_ambiguity_prompt=(
                "Antes de aplicar memorias especificas de vendor, preciso confirmar o fabricante "
                "do equipamento. Qual vendor devo considerar? Opcoes suportadas: Cisco, Juniper, "
                "Arista, MikroTik."
            ),
            ambiguous_vendors=["cisco"],
        )

    class AgentMustNotBeCalled:
        def __init__(self, **_kwargs) -> None:  # noqa: ANN003
            raise AssertionError("NetworkEngineerAgent should not be instantiated")

    monkeypatch.setattr(ChatService, "_get_owned_conversation", _fake_get_owned_conversation)
    monkeypatch.setattr(ChatService, "_load_history", _fake_load_history)
    monkeypatch.setattr(ChatService, "_resolve_attachment_context", _fake_resolve_attachment_context)
    monkeypatch.setattr(ChatService, "_resolve_memory_context", _fake_resolve_memory_context)
    monkeypatch.setattr("app.services.chat_service.decrypt_api_key", lambda _value: "plain-key")
    monkeypatch.setattr("app.services.chat_service.get_agent_tools", lambda **_kwargs: [])
    monkeypatch.setattr(
        "app.services.chat_service.NetworkEngineerAgent",
        AgentMustNotBeCalled,
    )
    monkeypatch.setattr(
        "app.services.chat_service.UsageTrackingService.increment_messages",
        _fake_increment_messages,
    )

    events: list[dict] = []
    async for event in service.process_user_message(
        user=user,
        conversation_id=conversation_id,
        content="descricao de uplink para RTR002",
    ):
        events.append(event)

    assert [event["type"] for event in events] == [
        "stream_start",
        "title_updated",
        "stream_chunk",
        "stream_end",
    ]
    assert "Qual vendor devo considerar?" in events[2]["content"]
    stream_end = events[3]
    assert stream_end["metadata"]["memory_context"]["status"] == "vendor_ambiguous"
    assert stream_end["metadata"]["memory_context"]["vendors"] == ["cisco"]
    assert stream_end["metadata"]["memory_context"]["supported_vendors"] == [
        "cisco",
        "juniper",
        "arista",
        "mikrotik",
    ]


@pytest.mark.asyncio
async def test_chat_service_uses_persisted_conversation_vendor_on_next_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Persisted conversation vendor should be forwarded to memory resolution when message is vendor-agnostic.
    """
    fake_db = FakeChatDbSession()
    service = ChatService(fake_db)  # type: ignore[arg-type]
    conversation_id = uuid4()
    user_id = uuid4()
    observed_preferred_vendor: dict[str, str | None] = {"value": None}

    user = SimpleNamespace(
        id=user_id,
        llm_provider="openai",
        encrypted_api_key="encrypted",
    )
    conversation = SimpleNamespace(
        id=conversation_id,
        model_used=None,
        title="Nova Conversa",
        updated_at=None,
    )

    async def _fake_get_owned_conversation(  # noqa: ANN202
        _self: ChatService, _conversation_id, _user_id
    ):
        return conversation

    async def _fake_increment_messages(_db, _user_id, _count=1):  # noqa: ANN001, ANN202
        return None

    async def _fake_load_history(  # noqa: ANN202
        _self: ChatService, _conversation_id
    ):
        return [{"role": "user", "content": "gere descricao de uplink para CRT4877"}]

    async def _fake_resolve_attachment_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        conversation_id: UUID,  # noqa: ARG001
        content: str,  # noqa: ARG001
        attachment_document_ids,  # noqa: ANN001, ARG001
    ):
        return AttachmentContextResolution(content_for_agent="gere descricao de uplink para CRT4877")

    async def _fake_resolve_active_vendor(  # noqa: ANN202
        _self: ChatService,
        *,
        conversation_id: UUID,  # noqa: ARG001
        content: str,  # noqa: ARG001
    ):
        return "mikrotik", "conversation", False, "mikrotik"

    async def _fake_resolve_memory_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        content_for_agent: str,  # noqa: ARG001
        preferred_vendor: str | None = None,
        allow_vendor_prompt: bool = True,
    ):
        observed_preferred_vendor["value"] = preferred_vendor
        assert allow_vendor_prompt is True
        return MemoryContextResolution(
            entries=[],
            context_block=None,
            vendor_ambiguity_prompt=None,
            ambiguous_vendors=[],
        )

    class FakeNetworkEngineerAgent:
        def __init__(self, **_kwargs) -> None:  # noqa: ANN003
            pass

        async def stream_response(self, _messages):  # noqa: ANN001, ANN202
            yield {"type": "text", "content": "ok"}

    monkeypatch.setattr(ChatService, "_get_owned_conversation", _fake_get_owned_conversation)
    monkeypatch.setattr(ChatService, "_load_history", _fake_load_history)
    monkeypatch.setattr(ChatService, "_resolve_attachment_context", _fake_resolve_attachment_context)
    monkeypatch.setattr(ChatService, "_resolve_active_vendor", _fake_resolve_active_vendor)
    monkeypatch.setattr(ChatService, "_resolve_memory_context", _fake_resolve_memory_context)
    monkeypatch.setattr("app.services.chat_service.decrypt_api_key", lambda _value: "plain-key")
    monkeypatch.setattr("app.services.chat_service.get_agent_tools", lambda **_kwargs: [])
    monkeypatch.setattr(
        "app.services.chat_service.NetworkEngineerAgent",
        FakeNetworkEngineerAgent,
    )
    monkeypatch.setattr(
        "app.services.chat_service.UsageTrackingService.increment_messages",
        _fake_increment_messages,
    )

    events: list[dict] = []
    async for event in service.process_user_message(
        user=user,
        conversation_id=conversation_id,
        content="gere descricao de uplink para CRT4877",
    ):
        events.append(event)

    assert observed_preferred_vendor["value"] == "mikrotik"
    assert any(event["type"] == "stream_end" for event in events)
    user_messages = [message for message in fake_db.added if getattr(message, "role", "") == "user"]
    assert user_messages
    metadata = user_messages[-1].message_metadata
    assert metadata["vendor_context"]["active_vendor"] == "mikrotik"
    assert metadata["vendor_context"]["supported"] is True


@pytest.mark.asyncio
async def test_chat_service_does_not_repeat_vendor_prompt_for_unsupported_vendor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Unsupported vendor confirmation should suppress new vendor clarification prompts.
    """
    fake_db = FakeChatDbSession()
    service = ChatService(fake_db)  # type: ignore[arg-type]
    conversation_id = uuid4()
    user_id = uuid4()
    observed_allow_vendor_prompt: dict[str, bool | None] = {"value": None}

    user = SimpleNamespace(
        id=user_id,
        llm_provider="openai",
        encrypted_api_key="encrypted",
    )
    conversation = SimpleNamespace(
        id=conversation_id,
        model_used=None,
        title="Nova Conversa",
        updated_at=None,
    )

    async def _fake_get_owned_conversation(  # noqa: ANN202
        _self: ChatService, _conversation_id, _user_id
    ):
        return conversation

    async def _fake_increment_messages(_db, _user_id, _count=1):  # noqa: ANN001, ANN202
        return None

    async def _fake_load_history(  # noqa: ANN202
        _self: ChatService, _conversation_id
    ):
        return [{"role": "user", "content": "descricao de uplink para CRT4877"}]

    async def _fake_resolve_attachment_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        conversation_id: UUID,  # noqa: ARG001
        content: str,  # noqa: ARG001
        attachment_document_ids,  # noqa: ANN001, ARG001
    ):
        return AttachmentContextResolution(content_for_agent="descricao de uplink para CRT4877")

    async def _fake_resolve_active_vendor(  # noqa: ANN202
        _self: ChatService,
        *,
        conversation_id: UUID,  # noqa: ARG001
        content: str,  # noqa: ARG001
    ):
        return None, "explicit_unsupported", True, "huawei"

    async def _fake_resolve_memory_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        content_for_agent: str,  # noqa: ARG001
        preferred_vendor: str | None = None,
        allow_vendor_prompt: bool = True,
    ):
        observed_allow_vendor_prompt["value"] = allow_vendor_prompt
        assert preferred_vendor is None
        return MemoryContextResolution(
            entries=[],
            context_block=None,
            vendor_ambiguity_prompt=None,
            ambiguous_vendors=[],
        )

    class FakeNetworkEngineerAgent:
        def __init__(self, **_kwargs) -> None:  # noqa: ANN003
            pass

        async def stream_response(self, _messages):  # noqa: ANN001, ANN202
            yield {"type": "text", "content": "ok"}

    monkeypatch.setattr(ChatService, "_get_owned_conversation", _fake_get_owned_conversation)
    monkeypatch.setattr(ChatService, "_load_history", _fake_load_history)
    monkeypatch.setattr(ChatService, "_resolve_attachment_context", _fake_resolve_attachment_context)
    monkeypatch.setattr(ChatService, "_resolve_active_vendor", _fake_resolve_active_vendor)
    monkeypatch.setattr(ChatService, "_resolve_memory_context", _fake_resolve_memory_context)
    monkeypatch.setattr("app.services.chat_service.decrypt_api_key", lambda _value: "plain-key")
    monkeypatch.setattr("app.services.chat_service.get_agent_tools", lambda **_kwargs: [])
    monkeypatch.setattr(
        "app.services.chat_service.NetworkEngineerAgent",
        FakeNetworkEngineerAgent,
    )
    monkeypatch.setattr(
        "app.services.chat_service.UsageTrackingService.increment_messages",
        _fake_increment_messages,
    )

    events: list[dict] = []
    async for event in service.process_user_message(
        user=user,
        conversation_id=conversation_id,
        content="huawei",
    ):
        events.append(event)

    assert observed_allow_vendor_prompt["value"] is False
    assert any(event["type"] == "stream_chunk" and event["content"] == "ok" for event in events)
    user_messages = [message for message in fake_db.added if getattr(message, "role", "") == "user"]
    assert user_messages
    metadata = user_messages[-1].message_metadata
    assert metadata["vendor_context"]["supported"] is False
    assert metadata["vendor_context"]["raw_vendor"] == "huawei"
