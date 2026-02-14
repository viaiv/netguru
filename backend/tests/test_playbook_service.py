"""
Playbook service tests.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.playbook_service import PlaybookService


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


class FailIfUsedRedis:
    """Redis stub that fails the test if accessed."""

    async def get(self, key: str) -> str | None:  # noqa: ARG002
        raise AssertionError("Redis should not be accessed for non-playbook messages")

    async def setex(self, key: str, _ttl: int, value: str) -> None:  # noqa: ARG002
        raise AssertionError("Redis should not be accessed for non-playbook messages")

    async def delete(self, key: str) -> None:  # noqa: ARG002
        raise AssertionError("Redis should not be accessed for non-playbook messages")


@pytest.mark.asyncio
async def test_playbook_ignores_regular_messages_without_redis_access() -> None:
    """
    Playbook service must bypass Redis for regular chat messages.
    """
    service = PlaybookService(redis_client=FailIfUsedRedis())
    response = await service.handle_message(
        conversation_id=uuid4(),
        content="analise este output de interface",
    )
    assert response is None


@pytest.mark.asyncio
async def test_playbook_full_flow_reaches_completion() -> None:
    """
    Playbook must progress through all stages and return final summary.
    """
    service = PlaybookService(redis_client=FakeRedis())
    conversation_id = uuid4()

    start = await service.handle_message(
        conversation_id=conversation_id,
        content="me guia no troubleshooting de ospf",
    )
    assert start is not None
    assert "Playbook iniciado" in start.content
    assert "Etapa 1/4" in start.content

    step2 = await service.handle_message(conversation_id=conversation_id, content="proximo")
    assert step2 is not None
    assert "Etapa 2/4" in step2.content

    step3 = await service.handle_message(conversation_id=conversation_id, content="proximo")
    assert step3 is not None
    assert "Etapa 3/4" in step3.content

    step4 = await service.handle_message(conversation_id=conversation_id, content="proximo")
    assert step4 is not None
    assert "Etapa 4/4" in step4.content

    done = await service.handle_message(conversation_id=conversation_id, content="proximo")
    assert done is not None
    assert "Playbook concluído" in done.content
    assert "Checklist de validação final" in done.content

    no_active = await service.handle_message(
        conversation_id=conversation_id,
        content="status playbook",
    )
    assert no_active is None


@pytest.mark.asyncio
async def test_playbook_pause_and_resume_preserves_stage() -> None:
    """
    Playbook should pause, refuse next while paused, and resume same stage.
    """
    service = PlaybookService(redis_client=FakeRedis())
    conversation_id = uuid4()

    await service.handle_message(
        conversation_id=conversation_id,
        content="quero um playbook de dns",
    )
    await service.handle_message(conversation_id=conversation_id, content="proximo")

    paused = await service.handle_message(
        conversation_id=conversation_id,
        content="pausar playbook",
    )
    assert paused is not None
    assert "pausado" in paused.content.lower()

    blocked_next = await service.handle_message(
        conversation_id=conversation_id,
        content="proximo",
    )
    assert blocked_next is not None
    assert "pausado" in blocked_next.content.lower()

    status = await service.handle_message(
        conversation_id=conversation_id,
        content="status playbook",
    )
    assert status is not None
    assert "Status: **paused**" in status.content
    assert "Etapa atual: **2/4" in status.content

    resumed = await service.handle_message(
        conversation_id=conversation_id,
        content="retomar playbook",
    )
    assert resumed is not None
    assert "Etapa 2/4" in resumed.content
