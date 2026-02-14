"""
ChatService integration tests for attachment context resolution.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.services.attachment_context_service import (
    AttachmentContextResolution,
    ResolvedAttachment,
)
from app.services.chat_service import ChatService


class FakeChatDbSession:
    """Minimal async DB session stub for ChatService attachment path tests."""

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
async def test_chat_service_resolves_attachment_and_exposes_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Single resolved attachment should enrich history and metadata in stream_end.
    """
    fake_db = FakeChatDbSession()
    service = ChatService(fake_db)  # type: ignore[arg-type]
    conversation_id = uuid4()
    user_id = uuid4()
    doc_id = uuid4()
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
        return [{"role": "user", "content": "analise este pcap"}]

    async def _fake_increment_messages(_db, _user_id, _count=1):  # noqa: ANN001, ANN202
        return None

    async def _fake_resolve_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        conversation_id: UUID,  # noqa: ARG001
        content: str,  # noqa: ARG001
        attachment_document_ids: list[UUID] | None,  # noqa: ARG001
    ):
        return AttachmentContextResolution(
            content_for_agent=(
                "analise este pcap\n\n"
                "[CONTEXTO_AUTOMATICO_DE_ANEXO]\n"
                f"document_id: {doc_id}\n"
                "filename: capture-1.pcap\n"
                "file_type: pcap\n"
                "Use a tool analyze_pcap com este document_id para analisar a captura."
            ),
            user_message_metadata={
                "attachments": [
                    {
                        "document_id": str(doc_id),
                        "filename": "capture-1.pcap",
                        "file_type": "pcap",
                        "source": "explicit",
                    }
                ],
                "attachment_resolution": {"status": "resolved", "intent": "pcap"},
            },
            resolved_attachment=ResolvedAttachment(
                document_id=doc_id,
                filename="capture-1.pcap",
                file_type="pcap",
                source="explicit",
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
    monkeypatch.setattr(ChatService, "_resolve_attachment_context", _fake_resolve_context)
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
        content="analise este pcap",
        attachment_document_ids=[doc_id],
    ):
        events.append(event)

    stream_end = next(e for e in events if e["type"] == "stream_end")
    assert "metadata" in stream_end
    assert stream_end["metadata"]["attachment_context"]["status"] == "resolved"
    assert (
        stream_end["metadata"]["attachment_context"]["resolved_attachment"]["document_id"]
        == str(doc_id)
    )

    assert captured_history["value"]
    assert str(doc_id) in captured_history["value"][-1]["content"]

    user_messages = [m for m in fake_db.added if getattr(m, "role", None) == "user"]
    assert user_messages
    assert user_messages[0].message_metadata is not None
    assert user_messages[0].message_metadata["attachments"][0]["document_id"] == str(doc_id)


@pytest.mark.asyncio
async def test_chat_service_returns_ambiguity_prompt_without_calling_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ambiguous implicit attachment must short-circuit and request user disambiguation.
    """
    fake_db = FakeChatDbSession()
    service = ChatService(fake_db)  # type: ignore[arg-type]
    conversation_id = uuid4()
    user_id = uuid4()
    doc_a = uuid4()
    doc_b = uuid4()

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

    async def _fake_resolve_context(  # noqa: ANN202
        _self: ChatService,
        *,
        user_id: UUID,  # noqa: ARG001
        conversation_id: UUID,  # noqa: ARG001
        content: str,  # noqa: ARG001
        attachment_document_ids: list[UUID] | None,  # noqa: ARG001
    ):
        return AttachmentContextResolution(
            content_for_agent="analise este pcap",
            user_message_metadata={
                "attachment_resolution": {"status": "ambiguous", "intent": "pcap"}
            },
            ambiguity_prompt=(
                "Encontrei mais de um anexo compatível.\n"
                "1. branch-a.pcap (pcap) — "
                f"{doc_a}\n"
                "2. branch-b.pcap (pcap) — "
                f"{doc_b}"
            ),
            ambiguity_candidates=[
                ResolvedAttachment(
                    document_id=doc_a,
                    filename="branch-a.pcap",
                    file_type="pcap",
                    source="recent",
                ),
                ResolvedAttachment(
                    document_id=doc_b,
                    filename="branch-b.pcap",
                    file_type="pcap",
                    source="recent",
                ),
            ],
        )

    class AgentMustNotBeCalled:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            raise AssertionError("NetworkEngineerAgent should not be instantiated")

    monkeypatch.setattr(ChatService, "_get_owned_conversation", _fake_get_owned_conversation)
    monkeypatch.setattr(ChatService, "_resolve_attachment_context", _fake_resolve_context)
    monkeypatch.setattr("app.services.chat_service.decrypt_api_key", lambda _value: "plain-key")
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
        content="analise este pcap",
    ):
        events.append(event)

    event_types = [e["type"] for e in events]
    assert event_types == [
        "stream_start",
        "title_updated",
        "stream_chunk",
        "stream_end",
    ]
    assert "mais de um anexo" in events[2]["content"].lower()
    assert events[3]["metadata"]["attachment_context"]["status"] == "ambiguous"
