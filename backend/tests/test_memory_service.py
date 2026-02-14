"""
MemoryService selection tests.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.memory_service import MemoryService, MemoryServiceError


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


def test_select_relevant_candidates_skips_vendor_memory_without_vendor_signal() -> None:
    """
    Vendor-tagged memory should not be applied when user message has no vendor hint.
    """
    cisco_memory = _memory_row(
        scope="system",
        scope_name=None,
        key="uplink_description_pattern",
        value="description UPLINK_TO_<DESTINO>",
        tags=["cisco", "interfaces", "uplink"],
    )

    selected = MemoryService.select_relevant_from_candidates(
        candidates=[(cisco_memory, "system")],
        message_content="gere uma sugestao de descricao de uplink para o RTR002",
        limit=8,
    )
    ambiguous_vendors = MemoryService.detect_ambiguous_vendors_from_candidates(
        candidates=[(cisco_memory, "system")],
        message_content="gere uma sugestao de descricao de uplink para o RTR002",
        limit=8,
    )

    assert selected == []
    assert ambiguous_vendors == ["cisco"]


def test_select_relevant_candidates_applies_vendor_memory_with_vendor_signal() -> None:
    """
    Vendor-tagged memory should be applied when message contains matching vendor hint.
    """
    cisco_memory = _memory_row(
        scope="system",
        scope_name=None,
        key="uplink_description_pattern",
        value="description UPLINK_TO_<DESTINO>",
        tags=["cisco", "interfaces", "uplink"],
    )

    selected = MemoryService.select_relevant_from_candidates(
        candidates=[(cisco_memory, "system")],
        message_content="no Cisco RTR002, gere a descricao de uplink",
        limit=8,
    )
    ambiguous_vendors = MemoryService.detect_ambiguous_vendors_from_candidates(
        candidates=[(cisco_memory, "system")],
        message_content="no Cisco RTR002, gere a descricao de uplink",
        limit=8,
    )

    assert len(selected) == 1
    assert selected[0].memory_key == "uplink_description_pattern"
    assert ambiguous_vendors == []


def test_vendor_ambiguity_detects_singular_plural_and_accents() -> None:
    """
    Ambiguity should trigger even with singular/plural differences and accent variations.
    """
    cisco_memory = _memory_row(
        scope="system",
        scope_name=None,
        key="padrão_naming_interfaces",
        value="description UPLINK_TO_<NOME_DO_DISPOSITIVO_DESTINO>",
        tags=["cisco", "standards", "naming", "interfaces"],
    )

    selected = MemoryService.select_relevant_from_candidates(
        candidates=[(cisco_memory, "system")],
        message_content="gere uma sugestão de descrição para interface de uplink no LDL003",
        limit=8,
    )
    ambiguous_vendors = MemoryService.detect_ambiguous_vendors_from_candidates(
        candidates=[(cisco_memory, "system")],
        message_content="gere uma sugestão de descrição para interface de uplink no LDL003",
        limit=8,
    )

    assert selected == []
    assert ambiguous_vendors == ["cisco"]


def test_select_relevant_candidates_applies_preferred_vendor_without_explicit_signal() -> None:
    """
    Preferred vendor context should allow applying vendor memory even without vendor text in message.
    """
    cisco_memory = _memory_row(
        scope="system",
        scope_name=None,
        key="uplink_description_pattern",
        value="description UPLINK_TO_<DESTINO>",
        tags=["cisco", "interfaces", "uplink"],
    )

    selected = MemoryService.select_relevant_from_candidates(
        candidates=[(cisco_memory, "system")],
        message_content="gere descricao de uplink para RTR002",
        preferred_vendor="cisco",
        limit=8,
    )
    ambiguous_vendors = MemoryService.detect_ambiguous_vendors_from_candidates(
        candidates=[(cisco_memory, "system")],
        message_content="gere descricao de uplink para RTR002",
        preferred_vendor="cisco",
        limit=8,
    )

    assert len(selected) == 1
    assert selected[0].memory_key == "uplink_description_pattern"
    assert ambiguous_vendors == []


def test_build_vendor_ambiguity_prompt_is_neutral_and_lists_supported_vendors() -> None:
    """
    Prompt must ask neutral confirmation and list supported vendor options.
    """
    prompt = MemoryService.build_vendor_ambiguity_prompt(["cisco"])

    assert prompt is not None
    assert "Qual vendor devo considerar?" in prompt
    assert "Cisco" in prompt
    assert "Juniper" in prompt
    assert "Arista" in prompt
    assert "MikroTik" in prompt


def test_vendor_ambiguity_can_be_suppressed_when_vendor_is_unsupported() -> None:
    """
    Vendor ambiguity prompts can be disabled when conversation vendor is unsupported.
    """
    cisco_memory = _memory_row(
        scope="system",
        scope_name=None,
        key="uplink_description_pattern",
        value="description UPLINK_TO_<DESTINO>",
        tags=["cisco", "interfaces", "uplink"],
    )

    selected = MemoryService.select_relevant_from_candidates(
        candidates=[(cisco_memory, "system")],
        message_content="gere uma sugestao de descricao de uplink para o RTR002",
        allow_vendor_prompt=False,
        limit=8,
    )
    ambiguous_vendors = MemoryService.detect_ambiguous_vendors_from_candidates(
        candidates=[(cisco_memory, "system")],
        message_content="gere uma sugestao de descricao de uplink para o RTR002",
        allow_vendor_prompt=False,
        limit=8,
    )

    assert selected == []
    assert ambiguous_vendors == []


def test_raise_if_memory_schema_missing_detects_network_table_error() -> None:
    """
    Missing network_memories relation must map to deterministic domain error.
    """
    with pytest.raises(MemoryServiceError) as exc_info:
        MemoryService._raise_if_memory_schema_missing(
            Exception('UndefinedTableError: relation "network_memories" does not exist')
        )

    assert exc_info.value.code == "memory_schema_missing"
    assert "alembic upgrade head" in exc_info.value.detail


def test_raise_if_memory_schema_missing_detects_system_table_error() -> None:
    """
    Missing system_memories relation must map to deterministic domain error.
    """
    with pytest.raises(MemoryServiceError) as exc_info:
        MemoryService._raise_if_memory_schema_missing(
            Exception('UndefinedTableError: relation "system_memories" does not exist')
        )

    assert exc_info.value.code == "memory_schema_missing"


def test_raise_if_memory_schema_missing_ignores_other_errors() -> None:
    """
    Non-schema errors should pass through unchanged.
    """
    MemoryService._raise_if_memory_schema_missing(Exception("connection timeout"))
