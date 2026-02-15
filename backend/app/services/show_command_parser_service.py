"""
ShowCommandParserService — Parse saida de show commands usando textfsm inline.

Templates inline para Cisco IOS/Arista EOS e Juniper JunOS.
Fallback com regex para comandos nao mapeados.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import textfsm


# ─────────────────────────────────────────────────────────
#  TextFSM Templates (inline, sem arquivos externos)
# ─────────────────────────────────────────────────────────

_TEMPLATE_SHOW_IP_INTERFACE_BRIEF = """\
Value INTERFACE (\\S+)
Value IP_ADDRESS (\\S+)
Value OK (\\S+)
Value METHOD (\\S+)
Value STATUS (.+?)
Value PROTOCOL (\\S+)

Start
  ^Interface\\s+IP-Address -> Header

Header
  ^${INTERFACE}\\s+${IP_ADDRESS}\\s+${OK}\\s+${METHOD}\\s+${STATUS}\\s+${PROTOCOL}\\s*$$ -> Record
"""

_TEMPLATE_SHOW_IP_ROUTE = """\
Value PROTOCOL (\\S)
Value PREFIX (\\d+\\.\\d+\\.\\d+\\.\\d+)
Value MASK (\\d+)
Value DISTANCE (\\d+)
Value METRIC (\\d+)
Value NEXT_HOP (\\d+\\.\\d+\\.\\d+\\.\\d+)
Value INTERFACE (\\S+)

Start
  ^${PROTOCOL}\\s+${PREFIX}/${MASK}\\s+\\[${DISTANCE}/${METRIC}\\]\\s+via\\s+${NEXT_HOP}(?:,\\s+${INTERFACE})? -> Record
  ^${PROTOCOL}\\s+${PREFIX}/${MASK}\\s+is directly connected,\\s+${INTERFACE} -> Record
"""

_TEMPLATE_SHOW_IP_OSPF_NEIGHBOR = """\
Value NEIGHBOR_ID (\\d+\\.\\d+\\.\\d+\\.\\d+)
Value PRIORITY (\\d+)
Value STATE (\\S+/\\s*\\S+)
Value DEAD_TIME (\\S+)
Value ADDRESS (\\d+\\.\\d+\\.\\d+\\.\\d+)
Value INTERFACE (\\S+)

Start
  ^${NEIGHBOR_ID}\\s+${PRIORITY}\\s+${STATE}\\s+${DEAD_TIME}\\s+${ADDRESS}\\s+${INTERFACE} -> Record
"""

_TEMPLATE_SHOW_IP_BGP_SUMMARY = """\
Value NEIGHBOR (\\d+\\.\\d+\\.\\d+\\.\\d+)
Value VERSION (\\d+)
Value AS (\\d+)
Value MSG_RCVD (\\d+)
Value MSG_SENT (\\d+)
Value UP_DOWN (\\S+)
Value STATE_PFXRCD (\\S+)

Start
  ^${NEIGHBOR}\\s+${VERSION}\\s+${AS}\\s+${MSG_RCVD}\\s+${MSG_SENT}\\s+\\S+\\s+\\S+\\s+\\S+\\s+${UP_DOWN}\\s+${STATE_PFXRCD} -> Record
"""

_TEMPLATE_SHOW_VLAN_BRIEF = """\
Value VLAN_ID (\\d+)
Value NAME (\\S+)
Value STATUS (\\S+)
Value PORTS (.*)

Start
  ^${VLAN_ID}\\s+${NAME}\\s+${STATUS}\\s+${PORTS} -> Record
"""

_TEMPLATE_SHOW_INTERFACES = """\
Value Required INTERFACE (\\S+)
Value LINK_STATUS (\\S+.*)
Value PROTOCOL_STATUS (\\S+)
Value HARDWARE (\\S+)
Value ADDRESS ([a-fA-F0-9.]+)
Value MTU (\\d+)
Value BANDWIDTH (\\d+)
Value INPUT_ERRORS (\\d+)
Value OUTPUT_ERRORS (\\d+)
Value CRC (\\d+)
Value INPUT_PACKETS (\\d+)
Value OUTPUT_PACKETS (\\d+)

Start
  ^${INTERFACE} is ${LINK_STATUS}, line protocol is ${PROTOCOL_STATUS}
  ^\\s+Hardware is ${HARDWARE}.*address is ${ADDRESS}
  ^\\s+MTU ${MTU}.*BW ${BANDWIDTH}
  ^\\s+${INPUT_PACKETS} packets input
  ^\\s+${INPUT_ERRORS} input errors, ${CRC} CRC
  ^\\s+${OUTPUT_PACKETS} packets output
  ^\\s+${OUTPUT_ERRORS} output errors -> Record
"""


# ─────────────────────────────────────────────────────────
#  Juniper JunOS TextFSM Templates
# ─────────────────────────────────────────────────────────

_TEMPLATE_JUNIPER_SHOW_ROUTE = """\
Value PROTOCOL (\\S+)
Value PREFIX (\\S+)
Value PREFERENCE (\\d+)
Value NEXT_HOP (\\S+)
Value INTERFACE (\\S+)

Start
  ^${PROTOCOL}\\s+\\*?${PREFIX}\\s+\\[${PREFERENCE}/\\d+\\]
  ^\\s+>\\s+to\\s+${NEXT_HOP}\\s+via\\s+${INTERFACE} -> Record
"""

_TEMPLATE_JUNIPER_SHOW_OSPF_NEIGHBOR = """\
Value NEIGHBOR_ADDRESS (\\d+\\.\\d+\\.\\d+\\.\\d+)
Value INTERFACE (\\S+)
Value STATE (\\S+)
Value NEIGHBOR_ID (\\d+\\.\\d+\\.\\d+\\.\\d+)
Value PRIORITY (\\d+)
Value DEAD_TIME (\\S+)

Start
  ^${NEIGHBOR_ADDRESS}\\s+${INTERFACE}\\s+${STATE}\\s+${NEIGHBOR_ID}\\s+${PRIORITY}\\s+${DEAD_TIME} -> Record
"""

_TEMPLATE_JUNIPER_SHOW_BGP_SUMMARY = """\
Value PEER (\\d+\\.\\d+\\.\\d+\\.\\d+)
Value AS (\\d+)
Value INPUT_MESSAGES (\\d+)
Value OUTPUT_MESSAGES (\\d+)
Value ROUTE_QUEUE (\\d+)
Value FLAPS (\\d+)
Value STATE (\\S+)

Start
  ^${PEER}\\s+${AS}\\s+${INPUT_MESSAGES}\\s+${OUTPUT_MESSAGES}\\s+${ROUTE_QUEUE}\\s+${FLAPS}\\s+.*\\s+${STATE}\\s*$$ -> Record
"""

_TEMPLATE_JUNIPER_SHOW_INTERFACES_TERSE = """\
Value INTERFACE (\\S+)
Value ADMIN (\\S+)
Value LINK (\\S+)
Value PROTO (\\S+)
Value LOCAL (\\S+)
Value REMOTE (\\S*)

Start
  ^${INTERFACE}\\s+${ADMIN}\\s+${LINK}\\s+${PROTO}\\s+${LOCAL}\\s*${REMOTE}\\s*$$ -> Record
"""


@dataclass
class ParsedShowCommand:
    """Resultado do parsing de um show command."""

    command: str
    headers: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    raw_output: str = ""
    parse_method: str = "textfsm"  # "textfsm" | "regex" | "raw"


# Mapa: pattern de deteccao → (template textfsm, nome do comando)
_COMMAND_TEMPLATES: list[tuple[str, str, str]] = [
    # (regex para detectar no output, template, nome do comando)
    (
        r"Interface\s+IP-Address\s+OK\?\s+Method\s+Status\s+Protocol",
        _TEMPLATE_SHOW_IP_INTERFACE_BRIEF,
        "show ip interface brief",
    ),
    (
        r"Neighbor\s+V\s+AS\s+MsgRcvd\s+MsgSent",
        _TEMPLATE_SHOW_IP_BGP_SUMMARY,
        "show ip bgp summary",
    ),
    (
        r"Neighbor ID\s+Pri\s+State\s+Dead Time\s+Address\s+Interface",
        _TEMPLATE_SHOW_IP_OSPF_NEIGHBOR,
        "show ip ospf neighbor",
    ),
    (
        r"VLAN\s+Name\s+Status\s+Ports",
        _TEMPLATE_SHOW_VLAN_BRIEF,
        "show vlan brief",
    ),
    (
        r"is\s+(up|down|administratively down),\s+line protocol is",
        _TEMPLATE_SHOW_INTERFACES,
        "show interfaces",
    ),
    (
        r"via\s+\d+\.\d+\.\d+\.\d+",
        _TEMPLATE_SHOW_IP_ROUTE,
        "show ip route",
    ),
    # Juniper JunOS
    (
        r"Interface\s+Admin\s+Link\s+Proto\s+Local\s+Remote",
        _TEMPLATE_JUNIPER_SHOW_INTERFACES_TERSE,
        "show interfaces terse",
    ),
    (
        r"Address\s+Interface\s+State\s+ID\s+Pri\s+Dead",
        _TEMPLATE_JUNIPER_SHOW_OSPF_NEIGHBOR,
        "show ospf neighbor",
    ),
    (
        r"Peer\s+AS\s+InPkt\s+OutPkt",
        _TEMPLATE_JUNIPER_SHOW_BGP_SUMMARY,
        "show bgp summary",
    ),
]

# Mapa de command hint → template
_HINT_TEMPLATES: dict[str, tuple[str, str]] = {
    "show ip interface brief": (_TEMPLATE_SHOW_IP_INTERFACE_BRIEF, "show ip interface brief"),
    "show ip int brief": (_TEMPLATE_SHOW_IP_INTERFACE_BRIEF, "show ip interface brief"),
    "sh ip int br": (_TEMPLATE_SHOW_IP_INTERFACE_BRIEF, "show ip interface brief"),
    "show ip route": (_TEMPLATE_SHOW_IP_ROUTE, "show ip route"),
    "sh ip route": (_TEMPLATE_SHOW_IP_ROUTE, "show ip route"),
    "show ip ospf neighbor": (_TEMPLATE_SHOW_IP_OSPF_NEIGHBOR, "show ip ospf neighbor"),
    "sh ip ospf nei": (_TEMPLATE_SHOW_IP_OSPF_NEIGHBOR, "show ip ospf neighbor"),
    "show ip bgp summary": (_TEMPLATE_SHOW_IP_BGP_SUMMARY, "show ip bgp summary"),
    "sh ip bgp sum": (_TEMPLATE_SHOW_IP_BGP_SUMMARY, "show ip bgp summary"),
    "show vlan brief": (_TEMPLATE_SHOW_VLAN_BRIEF, "show vlan brief"),
    "sh vlan br": (_TEMPLATE_SHOW_VLAN_BRIEF, "show vlan brief"),
    "show interfaces": (_TEMPLATE_SHOW_INTERFACES, "show interfaces"),
    "sh int": (_TEMPLATE_SHOW_INTERFACES, "show interfaces"),
    # Juniper JunOS hints
    "show route": (_TEMPLATE_JUNIPER_SHOW_ROUTE, "show route"),
    "show ospf neighbor": (_TEMPLATE_JUNIPER_SHOW_OSPF_NEIGHBOR, "show ospf neighbor"),
    "show bgp summary": (_TEMPLATE_JUNIPER_SHOW_BGP_SUMMARY, "show bgp summary"),
    "show interfaces terse": (_TEMPLATE_JUNIPER_SHOW_INTERFACES_TERSE, "show interfaces terse"),
    "sh int terse": (_TEMPLATE_JUNIPER_SHOW_INTERFACES_TERSE, "show interfaces terse"),
}


class ShowCommandParserService:
    """Parse saida de show commands usando textfsm com templates inline."""

    def detect_command(self, output: str) -> tuple[str | None, str | None]:
        """Detecta qual show command gerou o output baseado em padroes.

        Returns:
            Tupla (template_text, command_name) ou (None, None).
        """
        for pattern, template, cmd_name in _COMMAND_TEMPLATES:
            if re.search(pattern, output, re.IGNORECASE):
                return template, cmd_name
        return None, None

    def parse(self, output: str, command_hint: str | None = None) -> ParsedShowCommand:
        """Parse output com template textfsm ou regex fallback.

        Args:
            output: Saida do show command colada pelo usuario.
            command_hint: Nome do comando (ex: "show ip ospf neighbor").

        Returns:
            ParsedShowCommand com dados estruturados.
        """
        template_text: str | None = None
        cmd_name: str | None = None

        # 1. Tenta usar command_hint
        if command_hint:
            hint_lower = command_hint.strip().lower()
            if hint_lower in _HINT_TEMPLATES:
                template_text, cmd_name = _HINT_TEMPLATES[hint_lower]

        # 2. Auto-detect pelo conteudo
        if not template_text:
            template_text, cmd_name = self.detect_command(output)

        # 3. Se tem template, usa textfsm
        if template_text and cmd_name:
            return self._parse_with_textfsm(output, template_text, cmd_name)

        # 4. Fallback: retorna output com heuristicas basicas
        return self._fallback_parse(output, command_hint)

    def _parse_with_textfsm(
        self, output: str, template_text: str, cmd_name: str
    ) -> ParsedShowCommand:
        """Aplica template textfsm ao output."""
        try:
            template_fh = io.StringIO(template_text)
            fsm = textfsm.TextFSM(template_fh)
            rows_raw = fsm.ParseText(output)

            headers = [h for h in fsm.header]
            rows = []
            for row in rows_raw:
                row_dict = {}
                for i, header in enumerate(headers):
                    row_dict[header] = row[i] if i < len(row) else ""
                rows.append(row_dict)

            return ParsedShowCommand(
                command=cmd_name,
                headers=headers,
                rows=rows,
                raw_output=output,
                parse_method="textfsm",
            )
        except Exception:
            return self._fallback_parse(output, cmd_name)

    def _fallback_parse(
        self, output: str, command_hint: str | None
    ) -> ParsedShowCommand:
        """Fallback: retorna output cru com analise basica."""
        cmd_name = command_hint or "unknown command"

        # Tenta detectar linhas tabulares
        lines = output.strip().splitlines()
        rows: list[dict] = []
        headers: list[str] = []

        # Heuristica: se primeira linha nao-vazia parece header (todas palavras uppercase)
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                words = stripped.split()
                if len(words) >= 2 and all(
                    w.replace("-", "").replace("_", "").isalpha() for w in words[:3]
                ):
                    headers = [w.upper() for w in words]
                break

        return ParsedShowCommand(
            command=cmd_name,
            headers=headers,
            rows=rows,
            raw_output=output,
            parse_method="raw",
        )

    def format_parsed(self, parsed: ParsedShowCommand) -> str:
        """Formata resultado para o LLM.

        Args:
            parsed: Resultado do parsing.

        Returns:
            Texto formatado com tabela e analise.
        """
        parts: list[str] = [f"## Parsed Output: `{parsed.command}`"]
        parts.append(f"Parse method: {parsed.parse_method}")

        if parsed.rows:
            parts.append(f"\n**{len(parsed.rows)} entries found:**\n")

            # Tabela markdown
            if parsed.headers:
                parts.append("| " + " | ".join(parsed.headers) + " |")
                parts.append("| " + " | ".join("---" for _ in parsed.headers) + " |")
                for row in parsed.rows[:50]:  # Limita a 50 linhas
                    values = [str(row.get(h, "")) for h in parsed.headers]
                    parts.append("| " + " | ".join(values) + " |")
                if len(parsed.rows) > 50:
                    parts.append(f"\n... and {len(parsed.rows) - 50} more entries")

            # Analise rapida baseada no comando
            parts.append(self._quick_analysis(parsed))
        elif parsed.parse_method == "raw":
            parts.append("\nCould not parse output into structured data.")
            parts.append("Raw output (first 2000 chars):")
            parts.append(f"```\n{parsed.raw_output[:2000]}\n```")
        else:
            parts.append("\nNo entries found in the output.")

        return "\n".join(parts)

    def _quick_analysis(self, parsed: ParsedShowCommand) -> str:
        """Gera analise rapida baseada nos dados parsed."""
        notes: list[str] = []

        if parsed.command == "show ip interface brief":
            down_intfs = [
                r for r in parsed.rows
                if r.get("STATUS", "").lower() != "up"
                or r.get("PROTOCOL", "").lower() != "up"
            ]
            if down_intfs:
                names = [r.get("INTERFACE", "?") for r in down_intfs[:5]]
                notes.append(
                    f"\n**Note:** {len(down_intfs)} interface(s) not fully up: "
                    f"{', '.join(names)}"
                )

        elif parsed.command == "show ip ospf neighbor":
            non_full = [
                r for r in parsed.rows
                if "FULL" not in r.get("STATE", "").upper()
            ]
            if non_full:
                notes.append(
                    f"\n**Note:** {len(non_full)} OSPF neighbor(s) not in FULL state."
                )

        elif parsed.command == "show ip bgp summary":
            down_peers = [
                r for r in parsed.rows
                if not r.get("STATE_PFXRCD", "0").isdigit()
            ]
            if down_peers:
                names = [r.get("NEIGHBOR", "?") for r in down_peers[:5]]
                notes.append(
                    f"\n**Note:** {len(down_peers)} BGP peer(s) not established: "
                    f"{', '.join(names)}"
                )

        elif parsed.command == "show interfaces":
            err_intfs = [
                r for r in parsed.rows
                if int(r.get("INPUT_ERRORS", "0") or "0") > 0
                or int(r.get("CRC", "0") or "0") > 0
            ]
            if err_intfs:
                names = [r.get("INTERFACE", "?") for r in err_intfs[:5]]
                notes.append(
                    f"\n**Note:** {len(err_intfs)} interface(s) with errors: "
                    f"{', '.join(names)}"
                )

        # Juniper
        elif parsed.command == "show interfaces terse":
            down_intfs = [
                r for r in parsed.rows
                if r.get("LINK", "").lower() != "up"
                or r.get("ADMIN", "").lower() != "up"
            ]
            if down_intfs:
                names = [r.get("INTERFACE", "?") for r in down_intfs[:5]]
                notes.append(
                    f"\n**Note:** {len(down_intfs)} interface(s) not fully up: "
                    f"{', '.join(names)}"
                )

        elif parsed.command == "show ospf neighbor":
            non_full = [
                r for r in parsed.rows
                if "Full" not in r.get("STATE", "")
            ]
            if non_full:
                notes.append(
                    f"\n**Note:** {len(non_full)} OSPF neighbor(s) not in Full state."
                )

        return "\n".join(notes)
