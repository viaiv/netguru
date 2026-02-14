"""
Cancellation behavior tests for chat service and WS endpoint.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import ws_chat
from app.main import app
from app.services.chat_service import ChatService, ChatServiceError


class FakeChatDbSession:
    """Minimal async DB session stub for ChatService unit tests."""

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
async def test_chat_service_cancellation_rolls_back_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    ChatService must rollback and avoid commit when stream task is cancelled.
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

    async def _fake_load_history(  # noqa: ANN202
        _self: ChatService, _conversation_id
    ):
        return [{"role": "user", "content": "Diagnose this issue"}]

    class FakeNetworkEngineerAgent:
        def __init__(self, **_kwargs) -> None:  # noqa: ANN003
            pass

        async def stream_response(self, _messages):  # noqa: ANN001, ANN202
            yield {"type": "text", "content": "partial reply"}
            await asyncio.sleep(30)

    monkeypatch.setattr(ChatService, "_get_owned_conversation", _fake_get_owned_conversation)
    monkeypatch.setattr(ChatService, "_load_history", _fake_load_history)
    monkeypatch.setattr("app.services.chat_service.decrypt_api_key", lambda _value: "plain-key")
    monkeypatch.setattr("app.services.chat_service.get_agent_tools", lambda **_kwargs: [])
    monkeypatch.setattr(
        "app.services.chat_service.NetworkEngineerAgent",
        FakeNetworkEngineerAgent,
    )

    stream = service.process_user_message(
        user=user,
        conversation_id=conversation_id,
        content="Diagnose this issue",
    )

    start_event = await anext(stream)
    assert start_event["type"] == "stream_start"

    second_event = await anext(stream)
    if second_event["type"] == "title_updated":
        chunk_event = await anext(stream)
    else:
        chunk_event = second_event
    assert chunk_event == {"type": "stream_chunk", "content": "partial reply"}

    next_event_task = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    next_event_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await next_event_task

    assert fake_db.rollback_calls == 1
    assert fake_db.commit_calls == 0


class FakeWsDbSession:
    """Minimal DB stub for WS cancellation integration test."""

    def __init__(self) -> None:
        self.rollback_calls = 0

    async def rollback(self) -> None:
        self.rollback_calls += 1


class FakeAsyncSessionContext:
    """Async context wrapper used to patch AsyncSessionLocal."""

    def __init__(self, db: FakeWsDbSession) -> None:
        self._db = db

    async def __aenter__(self) -> FakeWsDbSession:
        return self._db

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


def test_websocket_cancel_rolls_back_and_keeps_connection_usable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    WS cancel path must rollback DB state and allow subsequent messages.
    """
    fake_db = FakeWsDbSession()

    async def _fake_authenticate(_websocket, _token, _db):  # noqa: ANN001, ANN202
        return SimpleNamespace(id=uuid4(), is_active=True)

    class FakeChatService:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def process_user_message(self, **_kwargs):  # noqa: ANN003, ANN202
            yield {"type": "stream_start", "message_id": "msg-1"}
            await asyncio.sleep(30)

    monkeypatch.setattr(
        ws_chat,
        "AsyncSessionLocal",
        lambda: FakeAsyncSessionContext(fake_db),
    )
    monkeypatch.setattr(ws_chat, "_authenticate_websocket", _fake_authenticate)
    monkeypatch.setattr(ws_chat, "ChatService", FakeChatService)

    conversation_id = uuid4()
    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/ws/chat/{conversation_id}?token=fake") as websocket:
            websocket.send_json({"type": "message", "content": "first run"})
            assert websocket.receive_json()["type"] == "stream_start"

            websocket.send_json({"type": "cancel"})
            cancel_event = websocket.receive_json()
            assert cancel_event["type"] == "stream_cancelled"
            assert cancel_event["reason"] == "cancelled_by_user"

            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}

            websocket.send_json({"type": "message", "content": "second run"})
            assert websocket.receive_json()["type"] == "stream_start"

            websocket.send_json({"type": "cancel"})
            second_cancel_event = websocket.receive_json()
            assert second_cancel_event["type"] == "stream_cancelled"

    assert fake_db.rollback_calls >= 2


def test_websocket_streams_normal_flow_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    WS endpoint must emit stream_start -> stream_chunk -> stream_end on success.
    """
    fake_db = FakeWsDbSession()

    async def _fake_authenticate(_websocket, _token, _db):  # noqa: ANN001, ANN202
        return SimpleNamespace(id=uuid4(), is_active=True)

    class FakeChatService:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def process_user_message(self, **_kwargs):  # noqa: ANN003, ANN202
            yield {"type": "stream_start", "message_id": "msg-123"}
            yield {"type": "stream_chunk", "content": "hello "}
            yield {"type": "stream_chunk", "content": "world"}
            yield {"type": "stream_end", "message_id": "msg-123", "tokens_used": 42}

    monkeypatch.setattr(
        ws_chat,
        "AsyncSessionLocal",
        lambda: FakeAsyncSessionContext(fake_db),
    )
    monkeypatch.setattr(ws_chat, "_authenticate_websocket", _fake_authenticate)
    monkeypatch.setattr(ws_chat, "ChatService", FakeChatService)

    conversation_id = uuid4()
    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/ws/chat/{conversation_id}?token=fake") as websocket:
            websocket.send_json({"type": "message", "content": "normal"})

            assert websocket.receive_json() == {"type": "stream_start", "message_id": "msg-123"}
            assert websocket.receive_json() == {"type": "stream_chunk", "content": "hello "}
            assert websocket.receive_json() == {"type": "stream_chunk", "content": "world"}
            assert websocket.receive_json() == {
                "type": "stream_end",
                "message_id": "msg-123",
                "tokens_used": 42,
            }

            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}


def test_websocket_streams_tool_state_progression_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    WS endpoint must stream queued/running/progress/completed states for long jobs.
    """
    fake_db = FakeWsDbSession()

    async def _fake_authenticate(_websocket, _token, _db):  # noqa: ANN001, ANN202
        return SimpleNamespace(id=uuid4(), is_active=True)

    class FakeChatService:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def process_user_message(self, **_kwargs):  # noqa: ANN003, ANN202
            yield {"type": "stream_start", "message_id": "msg-555"}
            yield {
                "type": "tool_call_start",
                "tool_call_id": "tc-555",
                "tool_name": "analyze_pcap",
                "tool_input": "{'document_id': 'abc'}",
            }
            yield {
                "type": "tool_call_state",
                "tool_call_id": "tc-555",
                "tool_name": "analyze_pcap",
                "status": "queued",
            }
            yield {
                "type": "tool_call_state",
                "tool_call_id": "tc-555",
                "tool_name": "analyze_pcap",
                "status": "running",
            }
            yield {
                "type": "tool_call_state",
                "tool_call_id": "tc-555",
                "tool_name": "analyze_pcap",
                "status": "progress",
                "progress_pct": 45,
                "elapsed_ms": 12000,
                "eta_ms": 14000,
            }
            yield {
                "type": "tool_call_end",
                "tool_call_id": "tc-555",
                "tool_name": "analyze_pcap",
                "result_preview": "done",
                "duration_ms": 26000,
            }
            yield {
                "type": "tool_call_state",
                "tool_call_id": "tc-555",
                "tool_name": "analyze_pcap",
                "status": "completed",
                "duration_ms": 26000,
                "progress_pct": 100,
            }
            yield {"type": "stream_end", "message_id": "msg-555", "tokens_used": 10}

    monkeypatch.setattr(
        ws_chat,
        "AsyncSessionLocal",
        lambda: FakeAsyncSessionContext(fake_db),
    )
    monkeypatch.setattr(ws_chat, "_authenticate_websocket", _fake_authenticate)
    monkeypatch.setattr(ws_chat, "ChatService", FakeChatService)

    conversation_id = uuid4()
    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/ws/chat/{conversation_id}?token=fake") as websocket:
            websocket.send_json({"type": "message", "content": "analyze pcap"})
            assert websocket.receive_json() == {"type": "stream_start", "message_id": "msg-555"}
            assert websocket.receive_json()["type"] == "tool_call_start"

            queued = websocket.receive_json()
            running = websocket.receive_json()
            progress = websocket.receive_json()
            assert queued["status"] == "queued"
            assert running["status"] == "running"
            assert progress["status"] == "progress"
            assert progress["progress_pct"] == 45

            assert websocket.receive_json()["type"] == "tool_call_end"
            completed = websocket.receive_json()
            assert completed["type"] == "tool_call_state"
            assert completed["status"] == "completed"
            assert websocket.receive_json() == {
                "type": "stream_end",
                "message_id": "msg-555",
                "tokens_used": 10,
            }


def test_websocket_surfaces_chat_service_error_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    WS endpoint must convert ChatServiceError into protocol error event.
    """
    fake_db = FakeWsDbSession()

    async def _fake_authenticate(_websocket, _token, _db):  # noqa: ANN001, ANN202
        return SimpleNamespace(id=uuid4(), is_active=True)

    class FakeChatService:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def process_user_message(self, **_kwargs):  # noqa: ANN003, ANN202
            if False:
                yield {}
            raise ChatServiceError("stream failed", code="stream_failed")

    monkeypatch.setattr(
        ws_chat,
        "AsyncSessionLocal",
        lambda: FakeAsyncSessionContext(fake_db),
    )
    monkeypatch.setattr(ws_chat, "_authenticate_websocket", _fake_authenticate)
    monkeypatch.setattr(ws_chat, "ChatService", FakeChatService)

    conversation_id = uuid4()
    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/ws/chat/{conversation_id}?token=fake") as websocket:
            websocket.send_json({"type": "message", "content": "error path"})
            assert websocket.receive_json() == {
                "type": "error",
                "code": "stream_failed",
                "detail": "stream failed",
            }

            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}
