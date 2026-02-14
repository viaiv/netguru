"""
ChatService integration tests for persistent memory context injection.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.services.attachment_context_service import AttachmentContextResolution
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
