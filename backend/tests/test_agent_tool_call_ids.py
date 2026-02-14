"""
Agent tool-call event correlation tests.
"""
from __future__ import annotations

import asyncio

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


class FakeCompiledGraphWithDelay:
    """Fake compiled graph that delays tool end to trigger progress events."""

    async def astream_events(self, _state, **_kwargs):  # noqa: ANN001, ANN202
        yield {
            "event": "on_tool_start",
            "name": "analyze_pcap",
            "run_id": "tc-delay",
            "data": {"input": {"document_id": "abc"}},
        }
        await asyncio.sleep(1.2)
        yield {
            "event": "on_tool_end",
            "name": "analyze_pcap",
            "run_id": "tc-delay",
            "data": {"output": "done"},
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


@pytest.mark.asyncio
async def test_agent_emits_progress_events_for_long_running_tools() -> None:
    """
    Long-running tool calls should emit periodic progress events while running.
    """
    agent = object.__new__(NetworkEngineerAgent)
    agent._compiled = FakeCompiledGraphWithDelay()  # type: ignore[attr-defined]
    agent._recursion_limit = 11  # type: ignore[attr-defined]

    events = []
    async for event in agent.stream_response([{"role": "user", "content": "analyze"}]):
        events.append(event)

    progress_events = [e for e in events if e["type"] == "tool_call_progress"]
    end_events = [e for e in events if e["type"] == "tool_call_end"]

    assert progress_events
    assert progress_events[0]["tool_call_id"] == "tc-delay"
    assert progress_events[0]["tool_name"] == "analyze_pcap"
    assert "elapsed_ms" in progress_events[0]
    assert end_events[-1]["tool_call_id"] == "tc-delay"
