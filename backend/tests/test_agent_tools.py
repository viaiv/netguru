"""
Tests for advanced agent tools wrappers.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.tools import config_tools, pcap_tools, show_command_tools


@pytest.mark.asyncio
async def test_parse_config_tool_returns_formatted_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """parse_config tool should call parser service and return formatted output."""

    class FakeParserService:
        def parse(self, config_text: str):  # noqa: ANN201
            assert config_text == "hostname R1"
            return {"vendor": "cisco"}

        def format_analysis(self, parsed):  # noqa: ANN001, ANN201
            assert parsed == {"vendor": "cisco"}
            return "formatted parse result"

    monkeypatch.setattr(config_tools, "ConfigParserService", FakeParserService)

    tool = config_tools.create_parse_config_tool()
    result = await tool.ainvoke({"config_text": "hostname R1"})
    assert result == "formatted parse result"


@pytest.mark.asyncio
async def test_validate_config_tool_returns_validation_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_config tool should detect vendor and return validator report."""

    class FakeParserService:
        def detect_vendor(self, config_text: str) -> str:
            assert config_text == "router ospf 1"
            return "cisco"

    class FakeValidatorService:
        def validate(self, config_text: str, vendor: str):  # noqa: ANN201
            assert config_text == "router ospf 1"
            assert vendor == "cisco"
            return ["issue-1"]

        def format_report(self, issues):  # noqa: ANN001, ANN201
            assert issues == ["issue-1"]
            return "formatted validation report"

    monkeypatch.setattr(config_tools, "ConfigParserService", FakeParserService)
    monkeypatch.setattr(config_tools, "ConfigValidatorService", FakeValidatorService)

    tool = config_tools.create_validate_config_tool()
    result = await tool.ainvoke({"config_text": "router ospf 1"})
    assert result == "formatted validation report"


@pytest.mark.asyncio
async def test_parse_show_commands_tool_returns_formatted_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """parse_show_commands tool should route output through parser service."""

    class FakeShowParserService:
        def parse(self, output: str, command_hint: str | None = None):  # noqa: ANN201
            assert output == "show ip route output"
            assert command_hint == "show ip route"
            return {"rows": 2}

        def format_parsed(self, parsed):  # noqa: ANN001, ANN201
            assert parsed == {"rows": 2}
            return "formatted show output"

    monkeypatch.setattr(show_command_tools, "ShowCommandParserService", FakeShowParserService)

    tool = show_command_tools.create_parse_show_commands_tool()
    result = await tool.ainvoke(
        {"output": "show ip route output", "command_hint": "show ip route"},
    )
    assert result == "formatted show output"


@pytest.mark.asyncio
async def test_analyze_pcap_tool_rejects_invalid_uuid() -> None:
    """analyze_pcap tool should validate document_id format."""

    class FakeDbSession:
        async def execute(self, _stmt):  # noqa: ANN001
            raise AssertionError("DB should not be queried for invalid UUID")

    tool = pcap_tools.create_analyze_pcap_tool(FakeDbSession(), uuid4())
    result = await tool.ainvoke({"document_id": "not-a-uuid"})
    assert "Invalid document ID" in result


@pytest.mark.asyncio
async def test_analyze_pcap_tool_returns_worker_formatted_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """analyze_pcap tool should return formatted result from Celery worker."""
    user_id = uuid4()
    document_id = uuid4()
    document = SimpleNamespace(
        id=document_id,
        user_id=user_id,
        file_type="pcap",
        original_filename="capture.pcap",
        storage_path="uploads/test/capture.pcap",
    )

    class FakeResult:
        def scalar_one_or_none(self):  # noqa: ANN201
            return document

    class FakeDbSession:
        async def execute(self, _stmt):  # noqa: ANN001, ANN201
            return FakeResult()

    class FakeTaskResult:
        def get(self, timeout: int):  # noqa: ANN001, ANN201
            assert timeout > 0
            return {
                "formatted": "pcap analysis summary",
                "data": {"total_packets": 123},
            }

    class FakeAnalyzePcapTask:
        @staticmethod
        def delay(storage_path: str, max_packets: int):  # noqa: ANN201
            assert storage_path == "uploads/test/capture.pcap"
            assert max_packets > 0
            return FakeTaskResult()

    import app.workers.tasks.pcap_tasks as pcap_tasks_module

    monkeypatch.setattr(pcap_tasks_module, "analyze_pcap", FakeAnalyzePcapTask())

    tool = pcap_tools.create_analyze_pcap_tool(FakeDbSession(), user_id)
    result = await tool.ainvoke({"document_id": str(document_id)})
    assert result.startswith("pcap analysis summary")
    assert "<!-- PCAP_DATA:" in result
    assert '"total_packets": 123' in result
