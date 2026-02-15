"""
Topology generation service — builds graph nodes/edges from parsed network data.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from app.services.config_parser_service import ConfigParserService, ParsedConfig

logger = logging.getLogger(__name__)


@dataclass
class TopologyNode:
    """A device node in the topology graph."""
    id: str
    label: str
    device_type: str  # router, switch, firewall, unknown
    vendor: str
    interfaces: list[dict]
    ip_addresses: list[str]
    routing_protocols: list[str]

    def to_react_flow(self, x: float = 0, y: float = 0) -> dict:
        return {
            "id": self.id,
            "type": "device",
            "position": {"x": x, "y": y},
            "data": {
                "label": self.label,
                "deviceType": self.device_type,
                "vendor": self.vendor,
                "interfaceCount": len(self.interfaces),
                "ipAddresses": self.ip_addresses[:5],
                "routingProtocols": self.routing_protocols,
            },
        }


@dataclass
class TopologyEdge:
    """A link between two device nodes."""
    source: str
    target: str
    source_interface: str
    target_interface: str
    protocol: str  # ospf, bgp, direct, cdp

    def to_react_flow(self) -> dict:
        edge_id = f"e-{self.source}-{self.target}-{self.protocol}"
        return {
            "id": edge_id,
            "source": self.source,
            "target": self.target,
            "label": self.protocol.upper(),
            "data": {
                "sourceInterface": self.source_interface,
                "targetInterface": self.target_interface,
                "protocol": self.protocol,
            },
        }


class TopologyService:
    """Generates topology graph from parsed network configurations."""

    @staticmethod
    def generate_from_configs(configs: list[ParsedConfig]) -> dict:
        """
        Build topology nodes and edges from one or more parsed configurations.

        Returns:
            dict with keys: nodes, edges, summary, metadata
        """
        nodes: dict[str, TopologyNode] = {}
        edges: list[TopologyEdge] = []
        seen_edges: set[str] = set()

        for config in configs:
            node = TopologyService._config_to_node(config)
            nodes[node.id] = node

            # Extract neighbor relationships
            for rp in config.routing_protocols:
                for neighbor_ip in rp.neighbors:
                    neighbor_id = TopologyService._ip_to_node_id(neighbor_ip)

                    # Create placeholder neighbor node if not seen
                    if neighbor_id not in nodes:
                        nodes[neighbor_id] = TopologyNode(
                            id=neighbor_id,
                            label=neighbor_ip,
                            device_type="router",
                            vendor="unknown",
                            interfaces=[],
                            ip_addresses=[neighbor_ip],
                            routing_protocols=[rp.protocol],
                        )
                    else:
                        if rp.protocol not in nodes[neighbor_id].routing_protocols:
                            nodes[neighbor_id].routing_protocols.append(rp.protocol)

                    # Add edge
                    edge_key = tuple(sorted([node.id, neighbor_id])) + (rp.protocol.lower(),)
                    edge_key_str = str(edge_key)
                    if edge_key_str not in seen_edges:
                        seen_edges.add(edge_key_str)
                        edges.append(TopologyEdge(
                            source=node.id,
                            target=neighbor_id,
                            source_interface="",
                            target_interface="",
                            protocol=rp.protocol.lower(),
                        ))

        # Layout nodes in a grid
        rf_nodes = []
        cols = max(3, int(len(nodes) ** 0.5) + 1)
        for idx, node in enumerate(nodes.values()):
            x = (idx % cols) * 250
            y = (idx // cols) * 200
            rf_nodes.append(node.to_react_flow(x, y))

        rf_edges = [e.to_react_flow() for e in edges]

        device_count = len(nodes)
        link_count = len(edges)
        vendors = list({n.vendor for n in nodes.values() if n.vendor != "unknown"})

        summary = (
            f"Topologia com {device_count} dispositivo(s) e {link_count} link(s)."
        )
        if vendors:
            summary += f" Vendors: {', '.join(vendors)}."

        return {
            "nodes": rf_nodes,
            "edges": rf_edges,
            "summary": summary,
            "metadata": {
                "device_count": device_count,
                "link_count": link_count,
                "vendors": vendors,
            },
        }

    @staticmethod
    def generate_from_config_text(config_text: str) -> dict:
        """
        Parse raw config text and generate topology.

        Args:
            config_text: One or more device configurations separated by '---' or '!'

        Returns:
            dict with nodes, edges, summary, metadata
        """
        parser = ConfigParserService()

        # Split multiple configs if delimited
        config_blocks = TopologyService._split_configs(config_text)
        parsed_configs: list[ParsedConfig] = []

        for block in config_blocks:
            block = block.strip()
            if not block:
                continue
            try:
                parsed = parser.parse(block)
                parsed_configs.append(parsed)
            except Exception as exc:
                logger.warning("Falha ao parsear bloco de config: %s", exc)

        if not parsed_configs:
            return {
                "nodes": [],
                "edges": [],
                "summary": "Nenhuma configuracao valida encontrada para gerar topologia.",
                "metadata": {"device_count": 0, "link_count": 0, "vendors": []},
            }

        return TopologyService.generate_from_configs(parsed_configs)

    @staticmethod
    def _config_to_node(config: ParsedConfig) -> TopologyNode:
        """Convert a ParsedConfig into a TopologyNode."""
        hostname = config.hostname or "unknown-device"
        node_id = TopologyService._hostname_to_id(hostname)

        ip_addresses = [
            iface.ip_address
            for iface in config.interfaces
            if iface.ip_address
        ]

        interfaces = [
            {
                "name": iface.name,
                "ip": iface.ip_address,
                "status": "down" if iface.shutdown else "up",
            }
            for iface in config.interfaces
        ]

        routing_protocols = list({rp.protocol for rp in config.routing_protocols})

        device_type = TopologyService._detect_device_type(config)

        return TopologyNode(
            id=node_id,
            label=hostname,
            device_type=device_type,
            vendor=config.vendor,
            interfaces=interfaces,
            ip_addresses=ip_addresses,
            routing_protocols=routing_protocols,
        )

    @staticmethod
    def _detect_device_type(config: ParsedConfig) -> str:
        """Infer device type from config characteristics."""
        has_routing = bool(config.routing_protocols)
        has_vlans = bool(config.vlans)
        has_acls = bool(config.acls)

        if has_acls and not has_routing and not has_vlans:
            return "firewall"
        if has_vlans and not has_routing:
            return "switch"
        if has_routing:
            return "router"
        return "unknown"

    @staticmethod
    def _hostname_to_id(hostname: str) -> str:
        """Generate stable node ID from hostname."""
        clean = hostname.lower().strip().replace(" ", "-")
        return f"dev-{clean}"

    @staticmethod
    def _ip_to_node_id(ip: str) -> str:
        """Generate node ID from IP address (for placeholder neighbors)."""
        short = hashlib.md5(ip.encode()).hexdigest()[:8]
        return f"peer-{short}"

    @staticmethod
    def _split_configs(text: str) -> list[str]:
        """Split text into multiple config blocks."""
        # Try separator '---'
        if "\n---\n" in text:
            return text.split("\n---\n")
        # Try separator '==='
        if "\n===\n" in text:
            return text.split("\n===\n")
        # Single config
        return [text]
