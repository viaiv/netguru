"""
ToolGuardrailService authorization and confirmation tests.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from langchain_core.tools import StructuredTool

from app.services.tool_guardrail_service import ToolGuardrailService


class FakeDbSession:
    """Minimal async DB session stub for guardrail tests."""

    async def flush(self) -> None:
        return None


def _build_tool(tool_name: str, counter: dict[str, int]) -> StructuredTool:
    """Create a simple async tool and count successful executions."""

    async def _tool(payload: str) -> str:
        counter["calls"] += 1
        return f"tool-ok:{payload}"

    return StructuredTool.from_function(
        coroutine=_tool,
        name=tool_name,
        description=f"Test tool {tool_name}",
    )


@pytest.mark.asyncio
async def test_guardrail_denies_tool_by_role_and_logs_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    User with unauthorized role must receive block and audit entry.
    """
    calls = {"calls": 0}
    audit_events: list[dict] = []

    policy = {
        "version": 1,
        "tools": {
            "pre_change_review": {
                "allowed_roles": ["owner", "admin"],
                "allowed_plans": ["solo", "team", "enterprise"],
                "require_confirmation": False,
            }
        },
    }

    async def _fake_get(_db, _key):  # noqa: ANN001, ANN202
        return json.dumps(policy)

    async def _fake_record(_db, **kwargs):  # noqa: ANN001, ANN003, ANN202
        audit_events.append(kwargs)
        return None

    monkeypatch.setattr(
        "app.services.tool_guardrail_service.SystemSettingsService.get",
        _fake_get,
    )
    monkeypatch.setattr(
        "app.services.tool_guardrail_service.AuditLogService.record",
        _fake_record,
    )

    service = ToolGuardrailService(
        db=FakeDbSession(),  # type: ignore[arg-type]
        user_id=uuid4(),
        user_role="viewer",
        plan_tier="enterprise",
        user_message="confirmo executar pre_change_review",
    )
    tool = _build_tool("pre_change_review", calls)
    guarded = service.wrap_tool(tool)

    result = await guarded.ainvoke({"payload": "change xyz"})

    assert result.startswith("BLOCKED_BY_GUARDRAIL:")
    assert "role_denied" in result
    assert calls["calls"] == 0
    assert audit_events
    assert audit_events[0]["action"] == "guardrail.tool_denied"
    assert audit_events[0]["target_id"] == "pre_change_review"


@pytest.mark.asyncio
async def test_guardrail_denies_tool_by_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    User on unauthorized plan must receive a consistent block response.
    """
    calls = {"calls": 0}

    policy = {
        "version": 1,
        "tools": {
            "analyze_pcap": {
                "allowed_roles": ["owner", "admin", "member"],
                "allowed_plans": ["team", "enterprise"],
                "require_confirmation": False,
            }
        },
    }

    async def _fake_get(_db, _key):  # noqa: ANN001, ANN202
        return json.dumps(policy)

    async def _fake_record(_db, **_kwargs):  # noqa: ANN001, ANN003, ANN202
        return None

    monkeypatch.setattr(
        "app.services.tool_guardrail_service.SystemSettingsService.get",
        _fake_get,
    )
    monkeypatch.setattr(
        "app.services.tool_guardrail_service.AuditLogService.record",
        _fake_record,
    )

    service = ToolGuardrailService(
        db=FakeDbSession(),  # type: ignore[arg-type]
        user_id=uuid4(),
        user_role="member",
        plan_tier="solo",
        user_message="confirmo executar analyze_pcap",
    )
    tool = _build_tool("analyze_pcap", calls)
    guarded = service.wrap_tool(tool)

    result = await guarded.ainvoke({"payload": "doc-id-123"})

    assert result.startswith("BLOCKED_BY_GUARDRAIL:")
    assert "plan_denied" in result
    assert calls["calls"] == 0


@pytest.mark.asyncio
async def test_guardrail_requires_explicit_confirmation_for_critical_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Critical tool must not execute without explicit confirmation phrase.
    """
    calls = {"calls": 0}

    policy = {
        "version": 1,
        "confirmation_phrases": ["confirmo"],
        "tools": {
            "pre_change_review": {
                "allowed_roles": ["member"],
                "allowed_plans": ["team"],
                "require_confirmation": True,
            }
        },
    }

    async def _fake_get(_db, _key):  # noqa: ANN001, ANN202
        return json.dumps(policy)

    async def _fake_record(_db, **_kwargs):  # noqa: ANN001, ANN003, ANN202
        return None

    monkeypatch.setattr(
        "app.services.tool_guardrail_service.SystemSettingsService.get",
        _fake_get,
    )
    monkeypatch.setattr(
        "app.services.tool_guardrail_service.AuditLogService.record",
        _fake_record,
    )

    service = ToolGuardrailService(
        db=FakeDbSession(),  # type: ignore[arg-type]
        user_id=uuid4(),
        user_role="member",
        plan_tier="team",
        user_message="analise a mudanca e me diga o risco",
    )
    tool = _build_tool("pre_change_review", calls)
    guarded = service.wrap_tool(tool)

    result = await guarded.ainvoke({"payload": "change xyz"})

    assert result.startswith("BLOCKED_BY_GUARDRAIL:")
    assert "confirmation_required" in result
    assert "confirme digitando" in result
    assert calls["calls"] == 0


@pytest.mark.asyncio
async def test_guardrail_allows_critical_tool_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Critical tool should execute when confirmation is present.
    """
    calls = {"calls": 0}

    policy = {
        "version": 1,
        "confirmation_phrases": ["confirmo"],
        "tools": {
            "pre_change_review": {
                "allowed_roles": ["member"],
                "allowed_plans": ["team"],
                "require_confirmation": True,
            }
        },
    }

    async def _fake_get(_db, _key):  # noqa: ANN001, ANN202
        return json.dumps(policy)

    async def _fake_record(_db, **_kwargs):  # noqa: ANN001, ANN003, ANN202
        return None

    monkeypatch.setattr(
        "app.services.tool_guardrail_service.SystemSettingsService.get",
        _fake_get,
    )
    monkeypatch.setattr(
        "app.services.tool_guardrail_service.AuditLogService.record",
        _fake_record,
    )

    service = ToolGuardrailService(
        db=FakeDbSession(),  # type: ignore[arg-type]
        user_id=uuid4(),
        user_role="member",
        plan_tier="team",
        user_message="confirmo executar pre_change_review para esta alteracao",
    )
    tool = _build_tool("pre_change_review", calls)
    guarded = service.wrap_tool(tool)

    result = await guarded.ainvoke({"payload": "change xyz"})

    assert result == "tool-ok:change xyz"
    assert calls["calls"] == 1
