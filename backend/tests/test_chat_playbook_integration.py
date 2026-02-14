"""
ChatService integration tests for guided playbooks.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.chat_service import ChatService


class FakeChatDbSession:
    """Minimal async DB session stub for ChatService playbook path tests."""

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


class FakeRedis:
    """Simple async in-memory Redis stub."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


@pytest.mark.asyncio
async def test_chat_service_starts_playbook_from_natural_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    ChatService should start guided playbook without invoking LLM agent.
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

    class AgentMustNotBeCalled:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            raise AssertionError("NetworkEngineerAgent should not be instantiated")

    monkeypatch.setattr(ChatService, "_get_owned_conversation", _fake_get_owned_conversation)
    monkeypatch.setattr(
        "app.services.chat_service.UsageTrackingService.increment_messages",
        _fake_increment_messages,
    )
    monkeypatch.setattr("app.services.chat_service.decrypt_api_key", lambda _value: "plain-key")
    monkeypatch.setattr(
        "app.services.chat_service.NetworkEngineerAgent",
        AgentMustNotBeCalled,
    )
    fake_redis = FakeRedis()
    monkeypatch.setattr(
        "app.services.playbook_service.get_redis_client",
        lambda: fake_redis,
    )

    events: list[dict] = []
    async for event in service.process_user_message(
        user=user,
        conversation_id=conversation_id,
        content="me guia no troubleshooting de OSPF",
    ):
        events.append(event)

    assert [e["type"] for e in events] == [
        "stream_start",
        "title_updated",
        "stream_chunk",
        "stream_end",
    ]
    assert "Playbook iniciado" in events[2]["content"]
    assert "Etapa 1/4" in events[2]["content"]
    assert fake_db.rollback_calls == 0
