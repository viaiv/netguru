"""
ConfigParserService — Parse e analisa configuracoes de rede.

Suporta Cisco IOS/IOS-XE/NX-OS, Arista EOS (via ciscoconfparse)
e Juniper JunOS (regex-based).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ciscoconfparse import CiscoConfParse


@dataclass
class ParsedInterface:
    """Interface extraida de uma configuracao."""

    name: str
    ip_address: str | None = None
    subnet_mask: str | None = None
    description: str | None = None
    shutdown: bool = False
    vlan: int | None = None
    acl_in: str | None = None
    acl_out: str | None = None


@dataclass
class ParsedRoutingProtocol:
    """Protocolo de roteamento extraido."""

    protocol: str
    process_id: str | None = None
    router_id: str | None = None
    networks: list[str] = field(default_factory=list)
    neighbors: list[str] = field(default_factory=list)
    areas: list[str] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)


@dataclass
class ParsedACL:
    """Access-list extraida."""

    name: str
    acl_type: str  # "standard" | "extended" | "named"
    entries: list[str] = field(default_factory=list)


@dataclass
class ParsedConfig:
    """Resultado completo do parsing de uma configuracao."""

    vendor: str
    hostname: str | None = None
    interfaces: list[ParsedInterface] = field(default_factory=list)
    routing_protocols: list[ParsedRoutingProtocol] = field(default_factory=list)
    acls: list[ParsedACL] = field(default_factory=list)
    vlans: list[dict] = field(default_factory=list)
    general: dict = field(default_factory=dict)
    raw_sections: dict[str, list[str]] = field(default_factory=dict)


class ConfigParserService:
    """Parse e analisa configuracoes de rede (Cisco IOS/NX-OS, Arista EOS, Juniper)."""

    def detect_vendor(self, config_text: str) -> str:
        """Detecta o vendor baseado em padroes da configuracao.

        Returns:
            "cisco" | "arista" | "juniper" | "unknown"
        """
        lines = config_text.strip().splitlines()
        text_lower = config_text.lower()

        # Juniper: blocos hierarquicos com {} ou comandos 'set'
        set_count = sum(1 for l in lines if l.strip().startswith("set "))
        if set_count > 3:
            return "juniper"
        if "{" in config_text and "}" in config_text and "interfaces {" in text_lower:
            return "juniper"

        # Arista EOS: detectar antes de Cisco pois compartilha sintaxe '!'
        # Padroes exclusivos do Arista EOS:
        arista_patterns = [
            r"! device:\s*eos",
            r"! Arista",
            r"switchport port-security",
            r"management api ",
            r"daemon ",
            r"ip routing vrf ",
            r"vrf instance ",
            r"ip virtual-router ",
            r"hardware tcam",
            r"monitor session .+ source",
            r"platform\s+sand\b",
        ]
        arista_score = sum(
            1 for p in arista_patterns
            if re.search(p, config_text, re.IGNORECASE | re.MULTILINE)
        )
        if arista_score >= 2:
            return "arista"

        # Cisco: linhas com '!' e keywords tipicas
        bang_count = sum(1 for l in lines if l.strip() == "!")
        if bang_count >= 2 or "interface " in text_lower or "router " in text_lower:
            return "cisco"

        return "unknown"

    def parse(self, config_text: str, vendor: str | None = None) -> ParsedConfig:
        """Parse configuracao com deteccao automatica de vendor.

        Args:
            config_text: Texto da configuracao.
            vendor: Vendor forcado (None = auto-detect).

        Returns:
            ParsedConfig com estrutura extraida.
        """
        if not vendor:
            vendor = self.detect_vendor(config_text)

        if vendor == "juniper":
            return self.parse_juniper_config(config_text)
        if vendor in ("cisco", "arista"):
            return self._parse_ios_style_config(config_text, vendor)

        # Fallback: tenta Cisco-style parser (mais tolerante)
        return self._parse_ios_style_config(config_text, "cisco")

    def _parse_ios_style_config(self, config_text: str, vendor: str) -> ParsedConfig:
        """Parse Cisco IOS ou Arista EOS (mesma sintaxe CLI)."""
        return self.parse_cisco_config(config_text, vendor=vendor)

    def parse_cisco_config(self, config_text: str, vendor: str = "cisco") -> ParsedConfig:
        """Usa ciscoconfparse para extrair estrutura de config Cisco/Arista."""
        lines = config_text.strip().splitlines()
        parse = CiscoConfParse(lines)
        result = ParsedConfig(vendor=vendor)

        # --- Hostname ---
        hostname_objs = parse.find_objects(r"^hostname\s+")
        if hostname_objs:
            result.hostname = hostname_objs[0].text.split(None, 1)[1]

        # --- Interfaces ---
        result.interfaces = self._parse_cisco_interfaces(parse)

        # --- Routing Protocols ---
        result.routing_protocols = self._parse_cisco_routing(parse)

        # --- ACLs ---
        result.acls = self._parse_cisco_acls(parse)

        # --- VLANs ---
        result.vlans = self._parse_cisco_vlans(parse)

        # --- General ---
        result.general = self._parse_cisco_general(parse)

        return result

    def _parse_cisco_interfaces(self, parse: CiscoConfParse) -> list[ParsedInterface]:
        """Extrai interfaces da config Cisco."""
        interfaces: list[ParsedInterface] = []

        for intf_obj in parse.find_objects(r"^interface\s+"):
            intf = ParsedInterface(name=intf_obj.text.split(None, 1)[1])

            for child in intf_obj.children:
                text = child.text.strip()

                # IP address
                ip_match = re.match(
                    r"ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)",
                    text,
                )
                if ip_match:
                    intf.ip_address = ip_match.group(1)
                    intf.subnet_mask = ip_match.group(2)

                # Description
                if text.startswith("description "):
                    intf.description = text.split(None, 1)[1]

                # Shutdown
                if text == "shutdown":
                    intf.shutdown = True

                # Access group (ACL)
                acl_match = re.match(r"ip access-group\s+(\S+)\s+(in|out)", text)
                if acl_match:
                    if acl_match.group(2) == "in":
                        intf.acl_in = acl_match.group(1)
                    else:
                        intf.acl_out = acl_match.group(1)

                # Switchport VLAN
                vlan_match = re.match(r"switchport access vlan\s+(\d+)", text)
                if vlan_match:
                    intf.vlan = int(vlan_match.group(1))

            interfaces.append(intf)

        return interfaces

    def _parse_cisco_routing(self, parse: CiscoConfParse) -> list[ParsedRoutingProtocol]:
        """Extrai protocolos de roteamento."""
        protocols: list[ParsedRoutingProtocol] = []

        # OSPF
        for obj in parse.find_objects(r"^router ospf\s+"):
            match = re.match(r"router ospf\s+(\d+)", obj.text)
            proto = ParsedRoutingProtocol(
                protocol="OSPF",
                process_id=match.group(1) if match else None,
            )
            for child in obj.children:
                text = child.text.strip()
                if text.startswith("router-id"):
                    proto.router_id = text.split()[-1]
                elif text.startswith("network "):
                    proto.networks.append(text)
                    area_match = re.search(r"area\s+(\S+)", text)
                    if area_match and area_match.group(1) not in proto.areas:
                        proto.areas.append(area_match.group(1))
                proto.raw_lines.append(text)
            protocols.append(proto)

        # BGP
        for obj in parse.find_objects(r"^router bgp\s+"):
            match = re.match(r"router bgp\s+(\d+)", obj.text)
            proto = ParsedRoutingProtocol(
                protocol="BGP",
                process_id=match.group(1) if match else None,
            )
            for child in obj.children:
                text = child.text.strip()
                if text.startswith("router-id") or text.startswith("bgp router-id"):
                    proto.router_id = text.split()[-1]
                elif text.startswith("neighbor "):
                    parts = text.split()
                    if len(parts) >= 2:
                        neighbor_ip = parts[1]
                        if neighbor_ip not in proto.neighbors:
                            proto.neighbors.append(neighbor_ip)
                elif text.startswith("network "):
                    proto.networks.append(text)
                proto.raw_lines.append(text)
            protocols.append(proto)

        # EIGRP
        for obj in parse.find_objects(r"^router eigrp\s+"):
            match = re.match(r"router eigrp\s+(\S+)", obj.text)
            proto = ParsedRoutingProtocol(
                protocol="EIGRP",
                process_id=match.group(1) if match else None,
            )
            for child in obj.children:
                text = child.text.strip()
                if text.startswith("network "):
                    proto.networks.append(text)
                proto.raw_lines.append(text)
            protocols.append(proto)

        # Static routes
        static_routes = parse.find_objects(r"^ip route\s+")
        if static_routes:
            proto = ParsedRoutingProtocol(protocol="Static")
            for obj in static_routes:
                proto.networks.append(obj.text.strip())
                proto.raw_lines.append(obj.text.strip())
            protocols.append(proto)

        return protocols

    def _parse_cisco_acls(self, parse: CiscoConfParse) -> list[ParsedACL]:
        """Extrai ACLs da config Cisco."""
        acls: list[ParsedACL] = []

        # Named ACLs
        for obj in parse.find_objects(r"^ip access-list\s+"):
            match = re.match(r"ip access-list\s+(extended|standard)\s+(\S+)", obj.text)
            if match:
                acl = ParsedACL(
                    name=match.group(2),
                    acl_type=match.group(1),
                )
                for child in obj.children:
                    acl.entries.append(child.text.strip())
                acls.append(acl)

        # Numbered ACLs
        for obj in parse.find_objects(r"^access-list\s+\d+"):
            match = re.match(r"access-list\s+(\d+)\s+(.*)", obj.text)
            if match:
                acl_num = match.group(1)
                # Agrupa entradas com mesmo numero
                existing = next((a for a in acls if a.name == acl_num), None)
                if existing:
                    existing.entries.append(match.group(2))
                else:
                    acl_type = "standard" if int(acl_num) < 100 else "extended"
                    acls.append(
                        ParsedACL(
                            name=acl_num,
                            acl_type=acl_type,
                            entries=[match.group(2)],
                        )
                    )

        return acls

    def _parse_cisco_vlans(self, parse: CiscoConfParse) -> list[dict]:
        """Extrai VLANs."""
        vlans: list[dict] = []
        for obj in parse.find_objects(r"^vlan\s+\d+"):
            match = re.match(r"vlan\s+(\d+)", obj.text)
            if match:
                vlan_info: dict = {"id": int(match.group(1))}
                for child in obj.children:
                    text = child.text.strip()
                    if text.startswith("name "):
                        vlan_info["name"] = text.split(None, 1)[1]
                vlans.append(vlan_info)
        return vlans

    def _parse_cisco_general(self, parse: CiscoConfParse) -> dict:
        """Extrai informacoes gerais da config."""
        general: dict = {}

        # Services
        services = []
        for obj in parse.find_objects(r"^service\s+"):
            services.append(obj.text.strip())
        if services:
            general["services"] = services

        # SSH
        ssh_objs = parse.find_objects(r"^ip ssh\s+")
        if ssh_objs:
            general["ssh"] = [o.text.strip() for o in ssh_objs]

        # NTP
        ntp_objs = parse.find_objects(r"^ntp\s+")
        if ntp_objs:
            general["ntp"] = [o.text.strip() for o in ntp_objs]

        # Logging
        log_objs = parse.find_objects(r"^logging\s+")
        if log_objs:
            general["logging"] = [o.text.strip() for o in log_objs]

        # SNMP
        snmp_objs = parse.find_objects(r"^snmp-server\s+")
        if snmp_objs:
            general["snmp"] = [o.text.strip() for o in snmp_objs]

        # Spanning-tree
        stp_objs = parse.find_objects(r"^spanning-tree\s+")
        if stp_objs:
            general["spanning_tree"] = [o.text.strip() for o in stp_objs]

        return general

    def parse_juniper_config(self, config_text: str) -> ParsedConfig:
        """Parse basico de Juniper (set commands ou hierarquico)."""
        result = ParsedConfig(vendor="juniper")
        lines = config_text.strip().splitlines()

        # Detectar formato: 'set' commands vs hierarquico
        set_lines = [l.strip() for l in lines if l.strip().startswith("set ")]

        if set_lines:
            return self._parse_juniper_set(set_lines, result)
        return self._parse_juniper_hierarchical(config_text, result)

    def _parse_juniper_set(
        self, set_lines: list[str], result: ParsedConfig
    ) -> ParsedConfig:
        """Parse Juniper 'set' format."""
        for line in set_lines:
            # Hostname
            match = re.match(r"set system host-name\s+(\S+)", line)
            if match:
                result.hostname = match.group(1)

            # Interfaces
            match = re.match(
                r"set interfaces\s+(\S+)\s+unit\s+(\d+)\s+family inet address\s+(\S+)",
                line,
            )
            if match:
                name = f"{match.group(1)}.{match.group(2)}"
                existing = next(
                    (i for i in result.interfaces if i.name == name), None
                )
                if not existing:
                    result.interfaces.append(
                        ParsedInterface(name=name, ip_address=match.group(3))
                    )
                else:
                    existing.ip_address = match.group(3)

            # Interface description
            match = re.match(
                r"set interfaces\s+(\S+)\s+description\s+\"?(.+?)\"?\s*$",
                line,
            )
            if match:
                intf_name = match.group(1)
                existing = next(
                    (i for i in result.interfaces if i.name.startswith(intf_name)),
                    None,
                )
                if existing:
                    existing.description = match.group(2)

            # OSPF
            match = re.match(
                r"set protocols ospf area\s+(\S+)\s+interface\s+(\S+)", line
            )
            if match:
                ospf = next(
                    (p for p in result.routing_protocols if p.protocol == "OSPF"),
                    None,
                )
                if not ospf:
                    ospf = ParsedRoutingProtocol(protocol="OSPF")
                    result.routing_protocols.append(ospf)
                area = match.group(1)
                if area not in ospf.areas:
                    ospf.areas.append(area)
                ospf.raw_lines.append(line)

            # BGP
            match = re.match(r"set protocols bgp group\s+(\S+)\s+neighbor\s+(\S+)", line)
            if match:
                bgp = next(
                    (p for p in result.routing_protocols if p.protocol == "BGP"),
                    None,
                )
                if not bgp:
                    bgp = ParsedRoutingProtocol(protocol="BGP")
                    result.routing_protocols.append(bgp)
                neighbor = match.group(2)
                if neighbor not in bgp.neighbors:
                    bgp.neighbors.append(neighbor)
                bgp.raw_lines.append(line)

        return result

    def _parse_juniper_hierarchical(
        self, config_text: str, result: ParsedConfig
    ) -> ParsedConfig:
        """Parse Juniper hierarchical (curly-brace) format (basico)."""
        # Hostname
        match = re.search(r"host-name\s+(\S+);", config_text)
        if match:
            result.hostname = match.group(1)

        # Interfaces (basico)
        for m in re.finditer(
            r"(\S+)\s*\{\s*unit\s+(\d+)\s*\{[^}]*family inet\s*\{[^}]*address\s+(\S+)",
            config_text,
            re.DOTALL,
        ):
            result.interfaces.append(
                ParsedInterface(
                    name=f"{m.group(1)}.{m.group(2)}",
                    ip_address=m.group(3).rstrip(";"),
                )
            )

        return result

    def format_analysis(self, parsed: ParsedConfig) -> str:
        """Formata ParsedConfig como texto estruturado para o LLM."""
        parts: list[str] = []

        parts.append(f"## Configuration Analysis (Vendor: {parsed.vendor.upper()})")

        if parsed.hostname:
            parts.append(f"**Hostname:** {parsed.hostname}")

        # Interfaces
        if parsed.interfaces:
            parts.append(f"\n### Interfaces ({len(parsed.interfaces)} found)")
            for intf in parsed.interfaces:
                status = "shutdown" if intf.shutdown else "active"
                ip_info = f" — {intf.ip_address}" if intf.ip_address else " — no IP"
                if intf.subnet_mask:
                    ip_info += f" / {intf.subnet_mask}"
                desc = f' "{intf.description}"' if intf.description else ""
                acl_info = ""
                if intf.acl_in or intf.acl_out:
                    acl_parts = []
                    if intf.acl_in:
                        acl_parts.append(f"ACL in: {intf.acl_in}")
                    if intf.acl_out:
                        acl_parts.append(f"ACL out: {intf.acl_out}")
                    acl_info = f" [{', '.join(acl_parts)}]"
                parts.append(f"- **{intf.name}** ({status}){ip_info}{desc}{acl_info}")

        # Routing
        if parsed.routing_protocols:
            parts.append(f"\n### Routing Protocols ({len(parsed.routing_protocols)} found)")
            for proto in parsed.routing_protocols:
                header = f"- **{proto.protocol}**"
                if proto.process_id:
                    header += f" (process/AS: {proto.process_id})"
                if proto.router_id:
                    header += f" — router-id: {proto.router_id}"
                parts.append(header)
                if proto.neighbors:
                    parts.append(f"  - Neighbors: {', '.join(proto.neighbors)}")
                if proto.networks:
                    for net in proto.networks[:10]:  # Limita a 10
                        parts.append(f"  - {net}")
                    if len(proto.networks) > 10:
                        parts.append(f"  - ... and {len(proto.networks) - 10} more")
                if proto.areas:
                    parts.append(f"  - Areas: {', '.join(proto.areas)}")

        # ACLs
        if parsed.acls:
            parts.append(f"\n### Access Control Lists ({len(parsed.acls)} found)")
            for acl in parsed.acls:
                parts.append(f"- **{acl.name}** ({acl.acl_type}) — {len(acl.entries)} entries")
                for entry in acl.entries[:5]:
                    parts.append(f"  - {entry}")
                if len(acl.entries) > 5:
                    parts.append(f"  - ... and {len(acl.entries) - 5} more")

        # VLANs
        if parsed.vlans:
            parts.append(f"\n### VLANs ({len(parsed.vlans)} found)")
            for v in parsed.vlans:
                name_str = f' — {v["name"]}' if "name" in v else ""
                parts.append(f"- VLAN {v['id']}{name_str}")

        # General
        if parsed.general:
            parts.append("\n### General Settings")
            for key, values in parsed.general.items():
                parts.append(f"- **{key.replace('_', ' ').title()}:** {len(values)} entries")

        return "\n".join(parts)
