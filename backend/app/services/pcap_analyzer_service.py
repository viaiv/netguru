"""
PcapAnalyzerService — Analise de PCAPs com scapy.

Usa asyncio.to_thread() para rodar scapy (blocking) sem travar o event loop.
"""
from __future__ import annotations

import asyncio
import os
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document


@dataclass
class PcapSummary:
    """Resultado da analise de um PCAP."""

    total_packets: int = 0
    duration_seconds: float = 0.0
    protocols: dict[str, int] = field(default_factory=dict)
    top_talkers: list[dict] = field(default_factory=list)
    conversations: list[dict] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    dns_queries: list[str] = field(default_factory=list)
    tcp_issues: list[dict] = field(default_factory=list)
    network_protocols: list[str] = field(default_factory=list)


class PcapAnalyzerService:
    """Analise de PCAPs com scapy."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_document(self, document_id: UUID, user_id: UUID) -> Document | None:
        """Busca e valida documento pertence ao usuario.

        Args:
            document_id: UUID do documento.
            user_id: UUID do usuario autenticado.

        Returns:
            Document se encontrado e pertence ao usuario, None caso contrario.
        """
        result = await self._db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def analyze(
        self, file_path: str, max_packets: int | None = None
    ) -> PcapSummary:
        """Analisa PCAP em thread separada (scapy e blocking).

        Args:
            file_path: Caminho do arquivo PCAP no disco.
            max_packets: Maximo de pacotes a analisar.

        Returns:
            PcapSummary com estatisticas e anomalias.
        """
        max_packets = max_packets or settings.PCAP_MAX_PACKETS
        return await asyncio.to_thread(self._analyze_sync, file_path, max_packets)

    def _analyze_sync(self, file_path: str, max_packets: int) -> PcapSummary:
        """Analise sincrona com scapy.rdpcap()."""
        from scapy.all import (  # type: ignore[import-untyped]
            DNSQR,
            ICMP,
            IP,
            TCP,
            UDP,
            DNS,
            rdpcap,
        )

        summary = PcapSummary()

        packets = rdpcap(file_path, count=max_packets)
        summary.total_packets = len(packets)

        if not packets:
            return summary

        # Duracao
        timestamps = [float(p.time) for p in packets]
        if len(timestamps) >= 2:
            summary.duration_seconds = round(
                max(timestamps) - min(timestamps), 3
            )

        # Contadores
        proto_counter: Counter[str] = Counter()
        src_counter: Counter[str] = Counter()
        dst_counter: Counter[str] = Counter()
        conversations_counter: Counter[tuple[str, str]] = Counter()
        dns_queries: list[str] = []
        tcp_seqs: dict[tuple, list[int]] = {}
        tcp_rst_count = 0
        icmp_unreachable = 0
        dns_nxdomain = 0
        network_protos: set[str] = set()

        for pkt in packets:
            # Protocolo de alto nivel
            proto = self._get_protocol_name(pkt)
            proto_counter[proto] += 1

            # IP stats
            if pkt.haslayer(IP):
                ip_layer = pkt[IP]
                src_counter[ip_layer.src] += 1
                dst_counter[ip_layer.dst] += 1

                pair = tuple(sorted([ip_layer.src, ip_layer.dst]))
                conversations_counter[pair] += 1  # type: ignore[arg-type]

            # TCP issues
            if pkt.haslayer(TCP):
                tcp_layer = pkt[TCP]

                # RST floods
                if tcp_layer.flags & 0x04:  # RST flag
                    tcp_rst_count += 1

                # Retransmissions (seq tracking simplificado)
                if pkt.haslayer(IP):
                    key = (pkt[IP].src, pkt[IP].dst, tcp_layer.sport, tcp_layer.dport)
                    seq = tcp_layer.seq
                    if key not in tcp_seqs:
                        tcp_seqs[key] = []
                    if seq in tcp_seqs[key]:
                        summary.tcp_issues.append({
                            "type": "possible_retransmission",
                            "src": pkt[IP].src,
                            "dst": pkt[IP].dst,
                            "seq": seq,
                        })
                    else:
                        tcp_seqs[key].append(seq)
                        # Limita memoria
                        if len(tcp_seqs[key]) > 1000:
                            tcp_seqs[key] = tcp_seqs[key][-500:]

            # DNS queries
            if pkt.haslayer(DNS) and pkt.haslayer(DNSQR):
                qname = pkt[DNSQR].qname
                if isinstance(qname, bytes):
                    qname = qname.decode("utf-8", errors="ignore")
                qname = qname.rstrip(".")
                if qname and qname not in dns_queries:
                    dns_queries.append(qname)

                # NXDOMAIN
                dns_layer = pkt[DNS]
                if dns_layer.rcode == 3:  # NXDOMAIN
                    dns_nxdomain += 1

            # ICMP unreachable
            if pkt.haslayer(ICMP):
                icmp_layer = pkt[ICMP]
                if icmp_layer.type == 3:  # Destination Unreachable
                    icmp_unreachable += 1

            # Protocolos de rede (OSPF, BGP, STP, HSRP)
            if pkt.haslayer(IP):
                if pkt[IP].proto == 89:
                    network_protos.add("OSPF")
                elif pkt[IP].proto == 88:
                    network_protos.add("EIGRP")
            if pkt.haslayer(TCP):
                if pkt[TCP].dport == 179 or pkt[TCP].sport == 179:
                    network_protos.add("BGP")
            if pkt.haslayer(UDP):
                if pkt[UDP].dport == 1985 or pkt[UDP].sport == 1985:
                    network_protos.add("HSRP")
                if pkt[UDP].dport == 3222 or pkt[UDP].sport == 3222:
                    network_protos.add("GLBP")

        # Preenche summary
        summary.protocols = dict(proto_counter.most_common(20))

        # Top talkers (src + dst combinado)
        all_ips = src_counter + dst_counter
        summary.top_talkers = [
            {"ip": ip, "packets": count}
            for ip, count in all_ips.most_common(10)
        ]

        # Conversations
        summary.conversations = [
            {"src": pair[0], "dst": pair[1], "packets": count}
            for pair, count in conversations_counter.most_common(10)
        ]

        # DNS
        summary.dns_queries = dns_queries[:50]

        # Network protocols
        summary.network_protocols = sorted(network_protos)

        # Anomalias
        retrans_count = len(summary.tcp_issues)
        if retrans_count > 0:
            # Limita log de retransmissions
            summary.tcp_issues = summary.tcp_issues[:20]
            summary.anomalies.append(
                f"TCP: {retrans_count} possible retransmission(s) detected"
            )

        if tcp_rst_count > summary.total_packets * 0.05:
            summary.anomalies.append(
                f"TCP: High RST count ({tcp_rst_count} packets, "
                f"{tcp_rst_count * 100 // summary.total_packets}% of total)"
            )

        if icmp_unreachable > 10:
            summary.anomalies.append(
                f"ICMP: {icmp_unreachable} Destination Unreachable messages"
            )

        if dns_nxdomain > 5:
            summary.anomalies.append(
                f"DNS: {dns_nxdomain} NXDOMAIN responses (non-existent domains)"
            )

        return summary

    @staticmethod
    def _get_protocol_name(pkt) -> str:  # noqa: ANN001
        """Extrai nome do protocolo de nivel mais alto do pacote."""
        from scapy.all import (  # type: ignore[import-untyped]
            ARP,
            ICMP,
            IP,
            TCP,
            UDP,
            DNS,
            Ether,
        )

        if pkt.haslayer(DNS):
            return "DNS"
        if pkt.haslayer(TCP):
            tcp = pkt[TCP]
            if tcp.dport == 80 or tcp.sport == 80:
                return "HTTP"
            if tcp.dport == 443 or tcp.sport == 443:
                return "HTTPS/TLS"
            if tcp.dport == 179 or tcp.sport == 179:
                return "BGP"
            if tcp.dport == 22 or tcp.sport == 22:
                return "SSH"
            if tcp.dport == 23 or tcp.sport == 23:
                return "Telnet"
            return "TCP"
        if pkt.haslayer(UDP):
            udp = pkt[UDP]
            if udp.dport == 53 or udp.sport == 53:
                return "DNS"
            if udp.dport == 161 or udp.sport == 161:
                return "SNMP"
            if udp.dport == 514 or udp.sport == 514:
                return "Syslog"
            if udp.dport == 123 or udp.sport == 123:
                return "NTP"
            return "UDP"
        if pkt.haslayer(ICMP):
            return "ICMP"
        if pkt.haslayer(ARP):
            return "ARP"
        if pkt.haslayer(IP):
            proto_num = pkt[IP].proto
            proto_map = {89: "OSPF", 88: "EIGRP", 112: "VRRP", 47: "GRE"}
            return proto_map.get(proto_num, f"IP(proto={proto_num})")
        if pkt.haslayer(Ether):
            etype = pkt[Ether].type
            if etype == 0x0806:
                return "ARP"
            if etype == 0x8100:
                return "802.1Q"
        return "Other"

    def format_summary(self, summary: PcapSummary) -> str:
        """Formata PcapSummary como texto para o LLM.

        Args:
            summary: Resultado da analise.

        Returns:
            Texto formatado.
        """
        parts: list[str] = ["## PCAP Analysis Summary"]

        parts.append(f"\n**Total Packets:** {summary.total_packets}")
        parts.append(f"**Duration:** {summary.duration_seconds}s")

        # Protocols
        if summary.protocols:
            parts.append("\n### Protocol Distribution")
            for proto, count in summary.protocols.items():
                pct = count * 100 // max(summary.total_packets, 1)
                parts.append(f"- {proto}: {count} ({pct}%)")

        # Network protocols
        if summary.network_protocols:
            parts.append(
                f"\n### Routing/Switching Protocols Detected: "
                f"{', '.join(summary.network_protocols)}"
            )

        # Top talkers
        if summary.top_talkers:
            parts.append("\n### Top Talkers")
            for t in summary.top_talkers[:10]:
                parts.append(f"- {t['ip']}: {t['packets']} packets")

        # Conversations
        if summary.conversations:
            parts.append("\n### Top Conversations")
            for c in summary.conversations[:10]:
                parts.append(
                    f"- {c['src']} ↔ {c['dst']}: {c['packets']} packets"
                )

        # DNS
        if summary.dns_queries:
            parts.append(f"\n### DNS Queries ({len(summary.dns_queries)} unique)")
            for q in summary.dns_queries[:20]:
                parts.append(f"- {q}")
            if len(summary.dns_queries) > 20:
                parts.append(f"... and {len(summary.dns_queries) - 20} more")

        # Anomalies
        if summary.anomalies:
            parts.append("\n### Anomalies Detected")
            for a in summary.anomalies:
                parts.append(f"- ⚠️ {a}")

        # TCP issues detail
        if summary.tcp_issues:
            parts.append(f"\n### TCP Issues ({len(summary.tcp_issues)} shown)")
            for issue in summary.tcp_issues[:10]:
                parts.append(
                    f"- {issue['type']}: {issue['src']} → {issue['dst']} "
                    f"(seq={issue['seq']})"
                )

        if not summary.anomalies:
            parts.append("\n### No anomalies detected")
            parts.append("The capture appears normal based on automated checks.")

        return "\n".join(parts)
