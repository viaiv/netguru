"""
Show command tools para o agent LangGraph — parse_show_commands.

Opera em texto puro (nao precisa de db ou user_id).
"""
from __future__ import annotations

from langchain_core.tools import StructuredTool

from app.services.show_command_parser_service import ShowCommandParserService


def create_parse_show_commands_tool() -> StructuredTool:
    """Cria tool de parsing de saida de show commands."""

    async def _parse_show_commands(
        output: str,
        command_hint: str = "",
    ) -> str:
        """
        Parse the output of a Cisco show command into structured data.
        Supports: show ip interface brief, show ip route, show ip ospf neighbor,
        show ip bgp summary, show vlan brief, show interfaces.

        Use this tool when the user pastes output from a show command and wants
        it analyzed, parsed, or explained.

        Args:
            output: The raw output of the show command as copied from the terminal.
            command_hint: Optional name of the command (e.g. "show ip ospf neighbor").
                         Helps with detection if auto-detect fails.
        """
        try:
            svc = ShowCommandParserService()
            parsed = svc.parse(output, command_hint or None)
            return svc.format_parsed(parsed)
        except Exception as e:
            return f"Error parsing show command output: {e}"

    return StructuredTool.from_function(
        coroutine=_parse_show_commands,
        name="parse_show_commands",
        description=(
            "Parse the output of a Cisco show command into structured data with analysis. "
            "Supports: show ip interface brief, show ip route, show ip ospf neighbor, "
            "show ip bgp summary, show vlan brief, show interfaces. "
            "Use when the user pastes terminal output from a show command. "
            "Provide the raw output text and optionally the command name as hint."
        ),
    )
