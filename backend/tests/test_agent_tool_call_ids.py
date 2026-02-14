"""
Agent tool-call event correlation tests.
"""
from __future__ import annotations

import pytest

from app.agents.network_engineer_agent import NetworkEngineerAgent


class FakeCompiledGraph:
    """Fake compiled graph that emits interleaved tool events."""

    async def astream_events(self, _state, **_kwargs):  # noqa: ANN001, ANN202
        yield {
            "event": "on_tool_start",
            "name": "parse_config",
            "run_id": "tc-1",
            "data": {"input": {"config_text": "A"}},
        }
        yield {
            "event": "on_tool_start",
            "name": "parse_config",
            "run_id": "tc-2",
            "data": {"input": {"config_text": "B"}},
        }
        yield {
            "event": "on_tool_end",
            "name": "parse_config",
            "run_id": "tc-2",
            "data": {"output": "result B"},
        }
        yield {
            "event": "on_tool_end",
            "name": "parse_config",
            "run_id": "tc-1",
            "data": {"output": "result A"},
        }


@pytest.mark.asyncio
async def test_agent_emits_tool_call_ids_for_repeated_tool_names() -> None:
    """
    Tool events must carry unique IDs so start/end pairs can be matched reliably.
    """
    agent = object.__new__(NetworkEngineerAgent)
    agent._compiled = FakeCompiledGraph()  # type: ignore[attr-defined]
    agent._recursion_limit = 11  # type: ignore[attr-defined]

    events = []
    async for event in agent.stream_response([{"role": "user", "content": "analyze"}]):
        events.append(event)

    starts = [e for e in events if e["type"] == "tool_call_start"]
    ends = [e for e in events if e["type"] == "tool_call_end"]

    assert [e["tool_call_id"] for e in starts] == ["tc-1", "tc-2"]
    assert [e["tool_call_id"] for e in ends] == ["tc-2", "tc-1"]
    assert [e["result_preview"] for e in ends] == ["result B", "result A"]
