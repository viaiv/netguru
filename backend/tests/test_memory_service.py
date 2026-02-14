"""
MemoryService selection tests.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from app.services.memory_service import MemoryService


def _memory_row(
    *,
    scope: str,
    scope_name: str | None,
    key: str,
    value: str,
    version: int = 1,
    tags: list[str] | None = None,
) -> SimpleNamespace:
    """
    Build a minimal row-like object compatible with select_relevant_memories.
    """
    now = datetime.utcnow()
    return SimpleNamespace(
        id=uuid4(),
        scope=scope,
        scope_name=scope_name,
        memory_key=key,
        memory_value=value,
        version=version,
        expires_at=None,
        tags=tags,
        updated_at=now,
        created_at=now,
    )


def test_select_relevant_memories_prioritizes_device_scope_over_site_and_global() -> None:
    """
    Same memory key across scopes should prefer device context when mentioned.
    """
    rows = [
        _memory_row(scope="global", scope_name=None, key="asn", value="65000", version=1),
        _memory_row(scope="site", scope_name="dc-sp", key="asn", value="65100", version=2),
        _memory_row(scope="device", scope_name="edge-rtr-01", key="asn", value="65200", version=3),
        _memory_row(scope="global", scope_name=None, key="ntp", value="10.10.10.10"),
    ]

    selected = MemoryService.select_relevant_memories(
        rows=rows,
        message_content="No device edge-rtr-01 do site dc-sp, valide ASN e NTP.",
        limit=8,
    )
    by_key = {entry.memory_key: entry for entry in selected}

    assert by_key["asn"].scope == "device"
    assert by_key["asn"].scope_name == "edge-rtr-01"
    assert by_key["asn"].memory_value == "65200"
    assert by_key["ntp"].scope == "global"


def test_select_relevant_memories_uses_global_when_scope_is_not_mentioned() -> None:
    """
    Without site/device mention, only global context should be injected.
    """
    rows = [
        _memory_row(scope="global", scope_name=None, key="asn", value="65000"),
        _memory_row(scope="site", scope_name="dc-sp", key="asn", value="65100"),
        _memory_row(scope="device", scope_name="edge-rtr-01", key="asn", value="65200"),
    ]

    selected = MemoryService.select_relevant_memories(
        rows=rows,
        message_content="Valide o asn da rede principal.",
        limit=8,
    )

    assert len(selected) == 1
    assert selected[0].scope == "global"
    assert selected[0].memory_value == "65000"


def test_select_relevant_candidates_prefers_user_global_over_system_level() -> None:
    """
    Global user memory should override system-level fallback memory.
    """
    user_row = _memory_row(scope="global", scope_name=None, key="asn", value="65100", version=3)
    system_row = _memory_row(scope="system", scope_name=None, key="asn", value="65000", version=9)

    selected = MemoryService.select_relevant_from_candidates(
        candidates=[(system_row, "system"), (user_row, "user")],
        message_content="valide asn",
        limit=8,
    )

    assert len(selected) == 1
    assert selected[0].origin == "user"
    assert selected[0].memory_value == "65100"


def test_select_relevant_candidates_keeps_global_above_system() -> None:
    """
    Hierarchy must keep global above system (device > site > global > system).
    """
    user_global = _memory_row(scope="global", scope_name=None, key="ntp", value="10.1.1.1")
    system_level = _memory_row(
        scope="system",
        scope_name=None,
        key="ntp",
        value="10.9.9.9",
    )

    selected = MemoryService.select_relevant_from_candidates(
        candidates=[(user_global, "user"), (system_level, "system")],
        message_content="cheque ntp",
        limit=8,
    )

    assert len(selected) == 1
    assert selected[0].origin == "user"
    assert selected[0].scope == "global"
    assert selected[0].memory_value == "10.1.1.1"


def test_select_relevant_candidates_uses_system_when_no_user_context_exists() -> None:
    """
    System-level memory must be applied when no device/site/global memory is present.
    """
    system_level = _memory_row(scope="system", scope_name=None, key="domain", value="corp.example")
    selected = MemoryService.select_relevant_from_candidates(
        candidates=[(system_level, "system")],
        message_content="qual o dominio corporativo?",
        limit=8,
    )

    assert len(selected) == 1
    assert selected[0].origin == "system"
    assert selected[0].scope == "system"
    assert selected[0].memory_value == "corp.example"
