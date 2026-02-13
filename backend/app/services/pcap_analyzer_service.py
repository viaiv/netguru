"""
PcapAnalyzerService — Analise de PCAPs com scapy.

Usa asyncio.to_thread() para rodar scapy (blocking) sem travar o event loop.
Suporta capturas Ethernet/IP (wired) e 802.11 Wi-Fi (wireless).
"""
from __future__ import annotations

import asyncio
import math
import os
import re
import statistics
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document

# --- Constantes 802.11 ---

DEAUTH_REASON_CODES: dict[int, str] = {
    0: "Reserved",
    1: "Unspecified reason",
    2: "Previous authentication no longer valid",
    3: "Deauthenticated: STA leaving/left IBSS or ESS",
    4: "Disassociated due to inactivity",
    5: "Disassociated: AP unable to handle all associated STAs",
    6: "Class 2 frame received from nonauthenticated STA",
    7: "Class 3 frame received from nonassociated STA",
    8: "Disassociated: STA leaving/left BSS",
    9: "STA requesting (re)association is not authenticated",
    10: "Disassociated: Power Capability element unacceptable",
    11: "Disassociated: Supported Channels element unacceptable",
    12: "Disassociated due to BSS Transition Management",
    13: "Invalid element",
    14: "MIC failure",
    15: "4-Way Handshake timeout",
    16: "Group Key Handshake timeout",
    17: "Element in 4-Way Handshake different from (Re)Association Request",
    18: "Invalid group cipher",
    19: "Invalid pairwise cipher",
    20: "Invalid AKMP",
    21: "Unsupported RSNE version",
    22: "Invalid RSNE capabilities",
    23: "IEEE 802.1X authentication failed",
    24: "Cipher suite rejected: security policy",
    25: "TDLS direct-link teardown: peer unreachable",
    26: "TDLS direct-link teardown: unspecified",
    34: "Disassociated: excessive frames need acknowledgment",
    36: "Requested from peer STA: leaving BSS or resetting",
    37: "Requested from peer STA: does not want mechanism",
    38: "Requested from peer STA: setup required for mechanism",
    39: "Requested from peer STA: timeout",
    45: "Peer STA does not support requested cipher suite",
}

DOT11_FRAME_TYPES: dict[tuple[int, int], str] = {
    # Management (type=0)
    (0, 0): "Association Request",
    (0, 1): "Association Response",
    (0, 2): "Reassociation Request",
    (0, 3): "Reassociation Response",
    (0, 4): "Probe Request",
    (0, 5): "Probe Response",
    (0, 8): "Beacon",
    (0, 9): "ATIM",
    (0, 10): "Disassociation",
    (0, 11): "Authentication",
    (0, 12): "Deauthentication",
    (0, 13): "Action",
    # Control (type=1)
    (1, 8): "Block Ack Request",
    (1, 9): "Block Ack",
    (1, 10): "PS-Poll",
    (1, 11): "RTS",
    (1, 12): "CTS",
    (1, 13): "ACK",
    (1, 14): "CF-End",
    (1, 15): "CF-End + CF-Ack",
    # Data (type=2)
    (2, 0): "Data",
    (2, 4): "Null Data",
    (2, 8): "QoS Data",
    (2, 12): "QoS Null",
}

FREQ_TO_CHANNEL: dict[int, int] = {
    # 2.4 GHz (channels 1-14)
    2412: 1, 2417: 2, 2422: 3, 2427: 4, 2432: 5,
    2437: 6, 2442: 7, 2447: 8, 2452: 9, 2457: 10,
    2462: 11, 2467: 12, 2472: 13, 2484: 14,
    # 5 GHz (common channels)
    5180: 36, 5200: 40, 5220: 44, 5240: 48,
    5260: 52, 5280: 56, 5300: 60, 5320: 64,
    5500: 100, 5520: 104, 5540: 108, 5560: 112,
    5580: 116, 5600: 120, 5620: 124, 5640: 128,
    5660: 132, 5680: 136, 5700: 140, 5720: 144,
    5745: 149, 5765: 153, 5785: 157, 5805: 161, 5825: 165,
}

_TYPE_LABELS = {0: "Management", 1: "Control", 2: "Data"}

# --- Constantes TLS ---

TLS_VERSION_MAP: dict[int, str] = {
    0x0300: "SSL 3.0",
    0x0301: "TLS 1.0",
    0x0302: "TLS 1.1",
    0x0303: "TLS 1.2",
    0x0304: "TLS 1.3",
}

_TLS_DEPRECATED_VERSIONS = {"SSL 3.0", "TLS 1.0", "TLS 1.1"}

_TLS_CIPHER_SUITE_NAMES: dict[int, str] = {
    0x002F: "TLS_RSA_WITH_AES_128_CBC_SHA",
    0x0035: "TLS_RSA_WITH_AES_256_CBC_SHA",
    0x009C: "TLS_RSA_WITH_AES_128_GCM_SHA256",
    0x009D: "TLS_RSA_WITH_AES_256_GCM_SHA384",
    0xC009: "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA",
    0xC00A: "TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA",
    0xC013: "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA",
    0xC014: "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA",
    0xC02B: "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
    0xC02C: "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
    0xC02F: "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
    0xC030: "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
    0x1301: "TLS_AES_128_GCM_SHA256",
    0x1302: "TLS_AES_256_GCM_SHA384",
    0x1303: "TLS_CHACHA20_POLY1305_SHA256",
    0xCCA8: "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256",
    0xCCA9: "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256",
    0xCCAA: "TLS_DHE_RSA_WITH_CHACHA20_POLY1305_SHA256",
    0x003C: "TLS_RSA_WITH_AES_128_CBC_SHA256",
    0x003D: "TLS_RSA_WITH_AES_256_CBC_SHA256",
}

# --- Constantes RTP/SIP ---

RTP_PAYLOAD_CODECS: dict[int, str] = {
    0: "G.711 PCMU",
    3: "GSM",
    4: "G.723",
    8: "G.711 PCMA",
    9: "G.722",
    18: "G.729",
    26: "JPEG",
    31: "H.261",
    32: "MPV (MPEG Video)",
    33: "MP2T (MPEG2 TS)",
    34: "H.263",
    96: "Dynamic (96)",
    97: "Dynamic (97)",
    98: "Dynamic (98)",
    99: "Dynamic (99)",
    100: "Dynamic (100)",
    101: "Dynamic (101) — Telephone-event/DTMF",
    111: "Dynamic (111) — Opus",
}

SIP_RESPONSE_CODES: dict[int, str] = {
    100: "Trying",
    180: "Ringing",
    183: "Session Progress",
    200: "OK",
    202: "Accepted",
    301: "Moved Permanently",
    302: "Moved Temporarily",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    407: "Proxy Authentication Required",
    408: "Request Timeout",
    480: "Temporarily Unavailable",
    481: "Call/Transaction Does Not Exist",
    486: "Busy Here",
    487: "Request Terminated",
    488: "Not Acceptable Here",
    500: "Server Internal Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    600: "Busy Everywhere",
    603: "Decline",
}

_SIP_METHODS = (
    "INVITE", "ACK", "BYE", "CANCEL", "REGISTER", "OPTIONS",
    "PRACK", "SUBSCRIBE", "NOTIFY", "PUBLISH", "INFO",
    "REFER", "MESSAGE", "UPDATE",
)
_SIP_REQUEST_RE = re.compile(
    rb"^(" + b"|".join(m.encode() for m in _SIP_METHODS) + rb")\s+sip:",
    re.MULTILINE,
)
_SIP_RESPONSE_RE = re.compile(
    rb"^SIP/2\.0\s+(\d{3})\s+(.+?)\r?\n",
    re.MULTILINE,
)

# --- Frame size distribution buckets ---

_FRAME_SIZE_BUCKETS = [
    (0, 64, "0-64"),
    (65, 128, "65-128"),
    (129, 256, "129-256"),
    (257, 512, "257-512"),
    (513, 1024, "513-1024"),
    (1025, 1518, "1025-1518"),
    (1519, 9000, "1519-9000 (Jumbo)"),
]


# --- Helpers de formatacao ---

def _format_bytes(num_bytes: int) -> str:
    """Formata bytes em representacao legivel (ex: '4.2 MB', '512 B')."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    for unit in ("KB", "MB", "GB", "TB"):
        num_bytes /= 1024.0
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
    return f"{num_bytes:.1f} PB"


def _format_bps(bps: float) -> str:
    """Formata bits por segundo (ex: '1.82 Mbps', '263 Kbps')."""
    if bps < 1000:
        return f"{bps:.0f} bps"
    if bps < 1_000_000:
        return f"{bps / 1000:.1f} Kbps"
    if bps < 1_000_000_000:
        return f"{bps / 1_000_000:.2f} Mbps"
    return f"{bps / 1_000_000_000:.2f} Gbps"


def _select_bucket_width(duration: float) -> float:
    """Seleciona largura do bucket temporal baseado na duracao da captura.

    Returns:
        Largura em segundos.
    """
    if duration <= 0:
        return 1.0
    if duration < 60:
        width = 1.0
    elif duration < 600:
        width = 5.0
    elif duration < 3600:
        width = 30.0
    else:
        width = 60.0
    # Hard cap: maximo 120 buckets
    num_buckets = math.ceil(duration / width)
    if num_buckets > 120:
        width = math.ceil(duration / 120)
    return width


def _tls_cipher_suite_name(value: int) -> str:
    """Retorna nome legivel de um cipher suite TLS."""
    return _TLS_CIPHER_SUITE_NAMES.get(value, f"Unknown (0x{value:04X})")


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
    # Bandwidth & time-series (Phase A)
    total_bytes: int = 0
    avg_throughput_bps: float = 0.0
    peak_throughput_bps: float = 0.0
    frame_size_stats: dict[str, float] = field(default_factory=dict)
    frame_size_distribution: dict[str, int] = field(default_factory=dict)
    time_buckets: list[dict] = field(default_factory=list)
    bucket_width_seconds: float = 0.0
    # HTTP analysis (Phase B)
    http_methods: dict[str, int] = field(default_factory=dict)
    http_status_codes: dict[str, int] = field(default_factory=dict)
    http_urls: list[str] = field(default_factory=list)
    http_hosts: list[str] = field(default_factory=list)
    http_request_count: int = 0
    http_response_count: int = 0
    # TLS analysis (Phase B)
    tls_versions: dict[str, int] = field(default_factory=dict)
    tls_sni_hosts: list[str] = field(default_factory=list)
    tls_cipher_suites: list[str] = field(default_factory=list)
    tls_handshakes: dict[str, int] = field(default_factory=dict)
    # VoIP/SIP (Phase C)
    voip_sip_methods: dict[str, int] = field(default_factory=dict)
    voip_sip_responses: dict[str, int] = field(default_factory=dict)
    voip_rtp_streams: int = 0
    voip_rtp_codecs: list[str] = field(default_factory=list)
    # Campos wireless (802.11)
    is_wireless: bool = False
    wireless_frame_types: dict[str, int] = field(default_factory=dict)
    deauth_events: list[dict] = field(default_factory=list)
    disassoc_events: list[dict] = field(default_factory=list)
    retry_stats: dict[str, float] = field(default_factory=dict)
    signal_stats: dict[str, float] = field(default_factory=dict)
    channels: dict[int, int] = field(default_factory=dict)
    ssids: list[str] = field(default_factory=list)
    wireless_devices: list[dict] = field(default_factory=list)


# --- Module-level helper functions (Phase B/C) ---

def _extract_tls_info(pkt) -> dict | None:  # noqa: ANN001
    """Extrai informacoes TLS de um pacote TCP via parsing manual de bytes raw.

    Evita dependencia de scapy.layers.tls (incompatibilidade com cryptography).

    Args:
        pkt: Pacote scapy com layer TCP.

    Returns:
        Dict com version, sni, cipher, is_client_hello, is_server_hello, ou None.
    """
    from scapy.all import TCP  # type: ignore[import-untyped]

    if not pkt.haslayer(TCP):
        return None
    try:
        raw = bytes(pkt[TCP].payload)
    except Exception:
        return None

    if len(raw) < 6:
        return None

    # TLS Record: content_type(1) + version(2) + length(2) + fragment
    content_type = raw[0]
    if content_type != 22:  # Handshake
        return None

    record_version = (raw[1] << 8) | raw[2]
    # record_length = (raw[3] << 8) | raw[4]

    if len(raw) < 10:
        return None

    # Handshake header: type(1) + length(3) + version(2)
    hs_type = raw[5]
    # hs_length = (raw[6] << 16) | (raw[7] << 8) | raw[8]
    hs_version = (raw[9] << 8) | raw[10] if len(raw) > 10 else 0

    result: dict = {}

    if hs_type == 1:  # ClientHello
        result["is_client_hello"] = True
        result["is_server_hello"] = False
        version_name = TLS_VERSION_MAP.get(hs_version, f"Unknown (0x{hs_version:04X})")

        # Parse extensions para SNI e supported_versions
        if len(raw) > 43:
            try:
                # Skip: hs header(4) + version(2) + random(32) = offset 38 from hs start
                # Session ID length at offset 43
                offset = 43
                if offset < len(raw):
                    session_id_len = raw[offset]
                    offset += 1 + session_id_len
                    # Cipher suites length (2 bytes)
                    if offset + 2 <= len(raw):
                        cs_len = (raw[offset] << 8) | raw[offset + 1]
                        offset += 2 + cs_len
                        # Compression methods length (1 byte)
                        if offset + 1 <= len(raw):
                            comp_len = raw[offset]
                            offset += 1 + comp_len
                            # Extensions length (2 bytes)
                            if offset + 2 <= len(raw):
                                ext_total_len = (raw[offset] << 8) | raw[offset + 1]
                                offset += 2
                                ext_end = min(offset + ext_total_len, len(raw))
                                while offset + 4 <= ext_end:
                                    ext_type = (raw[offset] << 8) | raw[offset + 1]
                                    ext_len = (raw[offset + 2] << 8) | raw[offset + 3]
                                    offset += 4
                                    ext_data = raw[offset:offset + ext_len]
                                    # SNI (extension type 0x0000)
                                    if ext_type == 0x0000 and len(ext_data) > 5:
                                        # SNI list length(2) + type(1) + name_len(2)
                                        name_len = (ext_data[3] << 8) | ext_data[4]
                                        if len(ext_data) >= 5 + name_len:
                                            sni = ext_data[5:5 + name_len].decode(
                                                "ascii", errors="replace"
                                            )
                                            result["sni"] = sni
                                    # supported_versions (0x002b) — TLS 1.3
                                    if ext_type == 0x002B and len(ext_data) > 1:
                                        sv_len = ext_data[0]
                                        for j in range(1, min(1 + sv_len, len(ext_data)), 2):
                                            if j + 1 < len(ext_data):
                                                sv = (ext_data[j] << 8) | ext_data[j + 1]
                                                if sv == 0x0304:
                                                    version_name = "TLS 1.3"
                                                    break
                                    offset += ext_len
            except (IndexError, struct.error):
                pass

        result["version"] = version_name

    elif hs_type == 2:  # ServerHello
        result["is_client_hello"] = False
        result["is_server_hello"] = True
        version_name = TLS_VERSION_MAP.get(hs_version, f"Unknown (0x{hs_version:04X})")

        # Parse cipher suite (at offset 5+4+2+32 = 43, after session_id)
        if len(raw) > 43:
            try:
                offset = 43
                session_id_len = raw[offset]
                offset += 1 + session_id_len
                if offset + 2 <= len(raw):
                    cipher_val = (raw[offset] << 8) | raw[offset + 1]
                    result["cipher"] = _tls_cipher_suite_name(cipher_val)
                    offset += 2
                    # Skip compression (1 byte)
                    offset += 1
                    # Extensions
                    if offset + 2 <= len(raw):
                        ext_total_len = (raw[offset] << 8) | raw[offset + 1]
                        offset += 2
                        ext_end = min(offset + ext_total_len, len(raw))
                        while offset + 4 <= ext_end:
                            ext_type = (raw[offset] << 8) | raw[offset + 1]
                            ext_len = (raw[offset + 2] << 8) | raw[offset + 3]
                            offset += 4
                            ext_data = raw[offset:offset + ext_len]
                            # supported_versions (0x002b)
                            if ext_type == 0x002B and len(ext_data) >= 2:
                                sv = (ext_data[0] << 8) | ext_data[1]
                                if sv in TLS_VERSION_MAP:
                                    version_name = TLS_VERSION_MAP[sv]
                            offset += ext_len
            except (IndexError, struct.error):
                pass

        result["version"] = version_name

    else:
        return None

    return result


def _extract_sip_info(
    payload: bytes,
    method_counter: Counter[str],
    response_counter: Counter[str],
) -> None:
    """Extrai informacoes SIP de payload raw (UDP/TCP).

    Args:
        payload: Bytes raw do payload.
        method_counter: Counter para metodos SIP (INVITE, BYE, etc).
        response_counter: Counter para respostas SIP ("200 OK", etc).
    """
    # SIP Request
    m = _SIP_REQUEST_RE.match(payload)
    if m:
        method = m.group(1).decode("ascii", errors="replace")
        method_counter[method] += 1
        return

    # SIP Response
    m = _SIP_RESPONSE_RE.match(payload)
    if m:
        code_str = m.group(1).decode("ascii", errors="replace")
        reason = m.group(2).decode("ascii", errors="replace").strip()
        try:
            code_int = int(code_str)
            # Usa lookup table ou o reason do pacote
            display = SIP_RESPONSE_CODES.get(code_int, reason)
            response_counter[f"{code_str} {display}"] += 1
        except ValueError:
            pass


def _extract_rtp_info(
    payload: bytes,
    ssrc_set: set[int],
    payload_types: set[int],
) -> None:
    """Extrai informacoes RTP de payload raw UDP.

    Valida header RTP (version=2, sanity checks) e filtra STUN.

    Args:
        payload: Bytes raw do payload UDP.
        ssrc_set: Set de SSRCs unicos (proxy para stream count).
        payload_types: Set de payload types encontrados.
    """
    if len(payload) < 12:
        return

    first_byte = payload[0]
    version = (first_byte >> 6) & 0x03
    if version != 2:
        return

    second_byte = payload[1]
    pt = second_byte & 0x7F

    # Filtra STUN (binding request/response usam 0x0001/0x0101)
    if payload[:2] in (b'\x00\x01', b'\x01\x01'):
        return

    # PT range valido (0-127, mas valores 72-76 sao RTCP)
    if 72 <= pt <= 76:
        return

    # Extrai SSRC (bytes 8-11)
    ssrc = struct.unpack("!I", payload[8:12])[0]
    ssrc_set.add(ssrc)
    payload_types.add(pt)


class PcapAnalyzerService:
    """Analise de PCAPs com scapy (wired e wireless)."""

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

    # ------------------------------------------------------------------
    # Deteccao wired vs wireless
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_wireless(file_path: str, sample: int = 20) -> bool:
        """Le amostra inicial do PCAP e retorna True se contem frames 802.11.

        Args:
            file_path: Caminho do PCAP.
            sample: Quantidade de pacotes a amostrar.

        Returns:
            True se a captura e wireless (Dot11/RadioTap).
        """
        from scapy.all import rdpcap  # type: ignore[import-untyped]
        from scapy.layers.dot11 import Dot11, RadioTap  # type: ignore[import-untyped]

        try:
            pkts = rdpcap(file_path, count=sample)
        except Exception:
            return False

        for pkt in pkts:
            if pkt.haslayer(Dot11) or pkt.haslayer(RadioTap):
                return True
        return False

    # ------------------------------------------------------------------
    # Entry point — branching wired/wireless
    # ------------------------------------------------------------------

    def _analyze_sync(self, file_path: str, max_packets: int) -> PcapSummary:
        """Analise sincrona — detecta tipo e delega."""
        if self._detect_wireless(file_path):
            return self._analyze_wireless_sync(file_path, max_packets)
        return self._analyze_wired_sync(file_path, max_packets)

    # ------------------------------------------------------------------
    # Analise WIRED (logica original)
    # ------------------------------------------------------------------

    def _analyze_wired_sync(self, file_path: str, max_packets: int) -> PcapSummary:
        """Analise sincrona de capturas Ethernet/IP com scapy.rdpcap()."""
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

        # Phase A: bandwidth tracking
        frame_sizes: list[int] = []
        per_second_bytes: Counter[int] = Counter()
        proto_per_packet: list[str] = []
        src_bytes: Counter[str] = Counter()
        dst_bytes: Counter[str] = Counter()
        conversation_bytes: Counter[tuple[str, str]] = Counter()

        # Phase B: HTTP/TLS tracking
        http_methods: Counter[str] = Counter()
        http_status_codes: Counter[str] = Counter()
        http_urls: list[str] = []
        http_host_set: set[str] = set()
        http_request_count = 0
        http_response_count = 0
        tls_versions: Counter[str] = Counter()
        tls_sni_set: set[str] = set()
        tls_cipher_set: set[str] = set()
        tls_client_hellos = 0
        tls_server_hellos = 0

        # Phase C: VoIP/SIP/RTP tracking
        sip_methods: Counter[str] = Counter()
        sip_responses: Counter[str] = Counter()
        rtp_ssrc_set: set[int] = set()
        rtp_payload_types: set[int] = set()

        # Import HTTP layers (pode falhar em scapy antigo)
        try:
            from scapy.layers.http import HTTPRequest, HTTPResponse  # type: ignore[import-untyped]
            _has_http_layer = True
        except ImportError:
            _has_http_layer = False

        for pkt in packets:
            # Protocolo de alto nivel
            proto = self._get_protocol_name(pkt)
            proto_counter[proto] += 1

            # Phase A: frame size e per-second bytes
            pkt_len = len(pkt)
            frame_sizes.append(pkt_len)
            per_second_bytes[int(float(pkt.time))] += pkt_len
            proto_per_packet.append(proto)

            # IP stats
            if pkt.haslayer(IP):
                ip_layer = pkt[IP]
                src_counter[ip_layer.src] += 1
                dst_counter[ip_layer.dst] += 1
                src_bytes[ip_layer.src] += pkt_len
                dst_bytes[ip_layer.dst] += pkt_len

                pair = tuple(sorted([ip_layer.src, ip_layer.dst]))
                conversations_counter[pair] += 1  # type: ignore[arg-type]
                conversation_bytes[pair] += pkt_len  # type: ignore[arg-type]

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

                # Phase B: TLS — parse raw TCP payload
                tls_info = _extract_tls_info(pkt)
                if tls_info:
                    if tls_info.get("version"):
                        tls_versions[tls_info["version"]] += 1
                    if tls_info.get("sni"):
                        tls_sni_set.add(tls_info["sni"])
                    if tls_info.get("cipher"):
                        tls_cipher_set.add(tls_info["cipher"])
                    if tls_info.get("is_client_hello"):
                        tls_client_hellos += 1
                    if tls_info.get("is_server_hello"):
                        tls_server_hellos += 1

                # Phase C: SIP sobre TCP (porta 5060/5061)
                if tcp_layer.dport in (5060, 5061) or tcp_layer.sport in (5060, 5061):
                    try:
                        payload = bytes(tcp_layer.payload)
                        if payload:
                            _extract_sip_info(payload, sip_methods, sip_responses)
                    except Exception:
                        pass

            # Phase B: HTTP (scapy HTTP layer)
            if _has_http_layer:
                if pkt.haslayer(HTTPRequest):
                    http_request_count += 1
                    req = pkt[HTTPRequest]
                    method = getattr(req, "Method", b"")
                    if isinstance(method, bytes):
                        method = method.decode("utf-8", errors="replace")
                    if method:
                        http_methods[method] += 1
                    path = getattr(req, "Path", b"")
                    if isinstance(path, bytes):
                        path = path.decode("utf-8", errors="replace")
                    if path and len(http_urls) < 200:
                        http_urls.append(path)
                    host = getattr(req, "Host", b"")
                    if isinstance(host, bytes):
                        host = host.decode("utf-8", errors="replace")
                    if host:
                        http_host_set.add(host)

                if pkt.haslayer(HTTPResponse):
                    http_response_count += 1
                    resp = pkt[HTTPResponse]
                    status_code = getattr(resp, "Status_Code", b"")
                    reason = getattr(resp, "Reason_Phrase", b"")
                    if isinstance(status_code, bytes):
                        status_code = status_code.decode("utf-8", errors="replace")
                    if isinstance(reason, bytes):
                        reason = reason.decode("utf-8", errors="replace")
                    if status_code:
                        key_str = f"{status_code} {reason}".strip()
                        http_status_codes[key_str] += 1

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
                udp_layer = pkt[UDP]
                if udp_layer.dport == 1985 or udp_layer.sport == 1985:
                    network_protos.add("HSRP")
                if udp_layer.dport == 3222 or udp_layer.sport == 3222:
                    network_protos.add("GLBP")

                # Phase C: SIP sobre UDP (porta 5060)
                if udp_layer.dport in (5060, 5061) or udp_layer.sport in (5060, 5061):
                    try:
                        payload = bytes(udp_layer.payload)
                        if payload:
                            _extract_sip_info(payload, sip_methods, sip_responses)
                    except Exception:
                        pass

                # Phase C: RTP detection (UDP, porta par >=1024, payload >=12 bytes)
                sport = udp_layer.sport
                dport = udp_layer.dport
                if (sport >= 1024 and dport >= 1024
                        and (sport % 2 == 0 or dport % 2 == 0)):
                    try:
                        payload = bytes(udp_layer.payload)
                        if len(payload) >= 12:
                            _extract_rtp_info(
                                payload, rtp_ssrc_set, rtp_payload_types,
                            )
                    except Exception:
                        pass

        # Preenche summary
        summary.protocols = dict(proto_counter.most_common(20))

        # Top talkers (src + dst combinado)
        all_ips = src_counter + dst_counter
        all_ip_bytes = src_bytes + dst_bytes
        summary.top_talkers = [
            {"ip": ip, "packets": count, "bytes": all_ip_bytes.get(ip, 0)}
            for ip, count in all_ips.most_common(10)
        ]

        # Conversations
        summary.conversations = [
            {
                "src": pair[0], "dst": pair[1],
                "packets": count,
                "bytes": conversation_bytes.get(pair, 0),
            }
            for pair, count in conversations_counter.most_common(10)
        ]

        # DNS
        summary.dns_queries = dns_queries[:50]

        # Network protocols
        summary.network_protocols = sorted(network_protos)

        # Phase A: Bandwidth stats
        self._compute_bandwidth_stats(
            summary, frame_sizes, per_second_bytes, timestamps,
            proto_per_packet,
        )

        # Phase B: HTTP
        if http_request_count or http_response_count:
            summary.http_methods = dict(http_methods.most_common(20))
            summary.http_status_codes = dict(http_status_codes.most_common(20))
            summary.http_urls = http_urls[:20]
            summary.http_hosts = sorted(http_host_set)[:50]
            summary.http_request_count = http_request_count
            summary.http_response_count = http_response_count

        # Phase B: TLS
        if tls_versions:
            summary.tls_versions = dict(tls_versions.most_common(10))
            summary.tls_sni_hosts = sorted(tls_sni_set)[:50]
            summary.tls_cipher_suites = sorted(tls_cipher_set)[:20]
            summary.tls_handshakes = {
                "client_hello": tls_client_hellos,
                "server_hello": tls_server_hellos,
            }

        # Phase C: VoIP/SIP
        if sip_methods or sip_responses:
            summary.voip_sip_methods = dict(sip_methods.most_common(20))
            summary.voip_sip_responses = dict(sip_responses.most_common(20))
        if rtp_ssrc_set:
            summary.voip_rtp_streams = len(rtp_ssrc_set)
            summary.voip_rtp_codecs = [
                RTP_PAYLOAD_CODECS.get(pt, f"Unknown PT={pt}")
                for pt in sorted(rtp_payload_types)
            ]

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

        # Phase A: Bandwidth anomalies
        self._detect_bandwidth_anomalies(summary)

        # Phase B: HTTP/TLS anomalies
        self._detect_http_tls_anomalies(summary)

        # Phase C: VoIP/SIP anomalies
        self._detect_voip_anomalies(summary)

        return summary

    # ------------------------------------------------------------------
    # Analise WIRELESS (802.11)
    # ------------------------------------------------------------------

    def _analyze_wireless_sync(self, file_path: str, max_packets: int) -> PcapSummary:
        """Analise sincrona de capturas 802.11 Wi-Fi.

        Single-pass: extrai frame types, deauth/disassoc, retry, sinal, canais,
        SSIDs, e dispositivos wireless.
        """
        from scapy.all import rdpcap  # type: ignore[import-untyped]
        from scapy.layers.dot11 import (  # type: ignore[import-untyped]
            Dot11,
            Dot11Auth,
            Dot11AssoReq,
            Dot11AssoResp,
            Dot11Beacon,
            Dot11Deauth,
            Dot11Disas,
            Dot11ProbeReq,
            Dot11ProbeResp,
            RadioTap,
        )

        summary = PcapSummary(is_wireless=True)

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
        frame_type_counter: Counter[str] = Counter()
        mac_counter: Counter[str] = Counter()
        channel_counter: Counter[int] = Counter()
        signal_values: list[float] = []
        ssid_set: set[str] = set()
        deauth_events: list[dict] = []
        disassoc_events: list[dict] = []
        total_retries = 0
        total_with_retry_field = 0

        # Phase A: bandwidth tracking (wireless)
        frame_sizes: list[int] = []
        per_second_bytes: Counter[int] = Counter()
        proto_per_packet: list[str] = []
        mac_bytes: Counter[str] = Counter()

        first_ts = timestamps[0] if timestamps else 0.0

        for pkt in packets:
            # Protocolo de alto nivel wireless
            proto = self._get_wireless_protocol_name(pkt)
            proto_counter[proto] += 1

            # Phase A: frame size e per-second bytes
            pkt_len = len(pkt)
            frame_sizes.append(pkt_len)
            per_second_bytes[int(float(pkt.time))] += pkt_len
            proto_per_packet.append(proto)

            if not pkt.haslayer(Dot11):
                continue

            dot11 = pkt[Dot11]

            # Frame type/subtype
            ftype = dot11.type
            fsubtype = dot11.subtype
            frame_name = DOT11_FRAME_TYPES.get(
                (ftype, fsubtype),
                f"{_TYPE_LABELS.get(ftype, 'Unknown')} (subtype={fsubtype})",
            )
            frame_type_counter[frame_name] += 1

            # Retry flag (bit 3 de FCfield)
            total_with_retry_field += 1
            if dot11.FCfield & 0x8:
                total_retries += 1

            # Transmitter MAC (addr2)
            if dot11.addr2:
                mac_counter[dot11.addr2] += 1
                mac_bytes[dot11.addr2] += pkt_len

            # Deauthentication
            if pkt.haslayer(Dot11Deauth):
                reason = pkt[Dot11Deauth].reason
                deauth_events.append({
                    "src": dot11.addr2 or "unknown",
                    "dst": dot11.addr1 or "unknown",
                    "reason": reason,
                    "reason_text": DEAUTH_REASON_CODES.get(reason, f"Unknown ({reason})"),
                    "timestamp": round(float(pkt.time) - first_ts, 3),
                })

            # Disassociation
            if pkt.haslayer(Dot11Disas):
                reason = pkt[Dot11Disas].reason
                disassoc_events.append({
                    "src": dot11.addr2 or "unknown",
                    "dst": dot11.addr1 or "unknown",
                    "reason": reason,
                    "reason_text": DEAUTH_REASON_CODES.get(reason, f"Unknown ({reason})"),
                    "timestamp": round(float(pkt.time) - first_ts, 3),
                })

            # RadioTap: sinal e canal
            if pkt.haslayer(RadioTap):
                rt = pkt[RadioTap]
                # Sinal dBm
                dbm = getattr(rt, "dBm_AntSignal", None)
                if dbm is not None:
                    try:
                        val = float(dbm)
                        # Filtro de sanidade: scapy pode retornar unsigned
                        if val > 0:
                            val = val - 256
                        if -120 <= val <= 0:
                            signal_values.append(val)
                    except (TypeError, ValueError):
                        pass

                # Frequencia -> canal
                freq = getattr(rt, "ChannelFrequency", None)
                if freq is not None:
                    try:
                        freq_int = int(freq)
                        channel = FREQ_TO_CHANNEL.get(freq_int)
                        if channel is not None:
                            channel_counter[channel] += 1
                    except (TypeError, ValueError):
                        pass

            # SSIDs (Beacon e Probe Response)
            if pkt.haslayer(Dot11Beacon) or pkt.haslayer(Dot11ProbeResp):
                ssid = self._extract_ssid(pkt)
                if ssid:
                    ssid_set.add(ssid)

            # SSIDs de Probe Request tambem
            if pkt.haslayer(Dot11ProbeReq):
                ssid = self._extract_ssid(pkt)
                if ssid:
                    ssid_set.add(ssid)

        # --- Preenche summary ---
        summary.protocols = dict(proto_counter.most_common(20))
        summary.wireless_frame_types = dict(frame_type_counter.most_common(30))

        # Deauth/Disassoc (limita a 50 eventos)
        summary.deauth_events = deauth_events[:50]
        summary.disassoc_events = disassoc_events[:50]

        # Retry stats
        if total_with_retry_field > 0:
            rate = round(total_retries * 100 / total_with_retry_field, 1)
            summary.retry_stats = {
                "total_frames": total_with_retry_field,
                "retries": total_retries,
                "rate_pct": rate,
            }

        # Signal stats
        if signal_values:
            summary.signal_stats = {
                "min_dBm": round(min(signal_values), 1),
                "max_dBm": round(max(signal_values), 1),
                "avg_dBm": round(statistics.mean(signal_values), 1),
                "median_dBm": round(statistics.median(signal_values), 1),
                "samples": len(signal_values),
            }

        # Canais
        summary.channels = dict(
            sorted(channel_counter.items(), key=lambda x: x[1], reverse=True)
        )

        # SSIDs
        summary.ssids = sorted(ssid_set)

        # Top wireless devices
        summary.wireless_devices = [
            {"mac": mac, "packets": count, "bytes": mac_bytes.get(mac, 0), "type": "transmitter"}
            for mac, count in mac_counter.most_common(15)
        ]

        # Top talkers (reusa formato para consistencia)
        summary.top_talkers = [
            {"ip": mac, "packets": count, "bytes": mac_bytes.get(mac, 0)}
            for mac, count in mac_counter.most_common(10)
        ]

        # Phase A: Bandwidth stats (wireless)
        self._compute_bandwidth_stats(
            summary, frame_sizes, per_second_bytes, timestamps,
            proto_per_packet,
        )

        # Anomalias wireless
        self._detect_wireless_anomalies(
            summary, deauth_events, disassoc_events, timestamps
        )

        # Phase A: Bandwidth anomalies
        self._detect_bandwidth_anomalies(summary)

        return summary

    # ------------------------------------------------------------------
    # Helpers wireless
    # ------------------------------------------------------------------

    @staticmethod
    def _get_wireless_protocol_name(pkt) -> str:  # noqa: ANN001
        """Classifica pacote 802.11 em protocolo legivel."""
        from scapy.layers.dot11 import (  # type: ignore[import-untyped]
            Dot11,
            Dot11Auth,
            Dot11AssoReq,
            Dot11AssoResp,
            Dot11Beacon,
            Dot11Deauth,
            Dot11Disas,
            Dot11ProbeReq,
            Dot11ProbeResp,
        )

        if pkt.haslayer(Dot11Beacon):
            return "802.11 Beacon"
        if pkt.haslayer(Dot11ProbeReq):
            return "802.11 Probe Request"
        if pkt.haslayer(Dot11ProbeResp):
            return "802.11 Probe Response"
        if pkt.haslayer(Dot11Auth):
            return "802.11 Authentication"
        if pkt.haslayer(Dot11Deauth):
            return "802.11 Deauthentication"
        if pkt.haslayer(Dot11Disas):
            return "802.11 Disassociation"
        if pkt.haslayer(Dot11AssoReq):
            return "802.11 Association Req"
        if pkt.haslayer(Dot11AssoResp):
            return "802.11 Association Resp"

        if pkt.haslayer(Dot11):
            ftype = pkt[Dot11].type
            if ftype == 2:
                return "802.11 Data"
            if ftype == 1:
                return "802.11 Control"
            return "802.11 Management"

        return "802.11 Other"

    @staticmethod
    def _extract_ssid(pkt) -> str | None:
        """Extrai SSID de um frame Beacon/ProbeResp/ProbeReq.

        Percorre Dot11Elt layers buscando tag ID=0 (SSID).

        Returns:
            Nome do SSID ou None se nao encontrado/vazio.
        """
        from scapy.layers.dot11 import Dot11Elt  # type: ignore[import-untyped]

        elt = pkt.getlayer(Dot11Elt)
        while elt:
            if elt.ID == 0:  # SSID tag
                try:
                    ssid = elt.info.decode("utf-8", errors="replace").strip()
                    if ssid and ssid != "\x00" * len(ssid):
                        return ssid
                except (AttributeError, UnicodeDecodeError):
                    pass
                return None
            elt = elt.payload.getlayer(Dot11Elt)
        return None

    @staticmethod
    def _detect_wireless_anomalies(
        summary: PcapSummary,
        deauth_events: list[dict],
        disassoc_events: list[dict],
        timestamps: list[float],
    ) -> None:
        """Detecta anomalias em capturas wireless e popula summary.anomalies.

        Args:
            summary: PcapSummary sendo construido.
            deauth_events: Lista completa de deauths (antes do truncamento).
            disassoc_events: Lista completa de disassocs.
            timestamps: Timestamps de todos os pacotes.
        """
        duration = summary.duration_seconds

        # Deauth flood: >10 deauths em <10s
        if len(deauth_events) > 10 and duration > 0:
            if duration < 10:
                summary.anomalies.append(
                    f"DEAUTH FLOOD: {len(deauth_events)} deauthentication frames "
                    f"in {duration}s — possible deauth attack"
                )
            elif len(deauth_events) / duration > 1.0:
                rate = round(len(deauth_events) / duration, 1)
                summary.anomalies.append(
                    f"HIGH DEAUTH RATE: {len(deauth_events)} deauths "
                    f"({rate}/sec) — possible deauth attack"
                )

        # Disassociation storm
        if len(disassoc_events) > 10 and duration > 0:
            rate = round(len(disassoc_events) / max(duration, 0.1), 1)
            if rate > 1.0:
                summary.anomalies.append(
                    f"DISASSOC STORM: {len(disassoc_events)} disassociation frames "
                    f"({rate}/sec)"
                )

        # Deauths concentrados em mesmo reason code
        if len(deauth_events) > 5:
            reason_counter: Counter[int] = Counter(
                e["reason"] for e in deauth_events
            )
            top_reason, top_count = reason_counter.most_common(1)[0]
            if top_count > len(deauth_events) * 0.8:
                reason_text = DEAUTH_REASON_CODES.get(
                    top_reason, f"code {top_reason}"
                )
                summary.anomalies.append(
                    f"SUSPICIOUS PATTERN: {top_count}/{len(deauth_events)} deauths "
                    f"with same reason: {reason_text}"
                )

        # Alto retry rate
        if summary.retry_stats:
            rate_pct = summary.retry_stats.get("rate_pct", 0)
            if rate_pct > 30:
                summary.anomalies.append(
                    f"VERY HIGH RETRY RATE: {rate_pct}% — severe RF interference "
                    f"or congestion"
                )
            elif rate_pct > 15:
                summary.anomalies.append(
                    f"HIGH RETRY RATE: {rate_pct}% — RF interference or congestion"
                )

        # Sinal fraco
        if summary.signal_stats:
            avg_dbm = summary.signal_stats.get("avg_dBm", 0)
            if avg_dbm < -80:
                summary.anomalies.append(
                    f"VERY WEAK SIGNAL: average {avg_dbm} dBm — poor connectivity expected"
                )
            elif avg_dbm < -75:
                summary.anomalies.append(
                    f"WEAK SIGNAL: average {avg_dbm} dBm — may cause packet loss"
                )

    # ------------------------------------------------------------------
    # Protocolo wired (original)
    # ------------------------------------------------------------------

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
            if tcp.dport == 5060 or tcp.sport == 5060:
                return "SIP"
            if tcp.dport == 5061 or tcp.sport == 5061:
                return "SIP/TLS"
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
            if udp.dport == 5060 or udp.sport == 5060:
                return "SIP"
            if udp.dport == 5061 or udp.sport == 5061:
                return "SIP/TLS"
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

    # ------------------------------------------------------------------
    # Phase A: Bandwidth & Time-Series
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_bandwidth_stats(
        summary: PcapSummary,
        frame_sizes: list[int],
        per_second_bytes: Counter[int],
        timestamps: list[float],
        proto_per_packet: list[str],
    ) -> None:
        """Calcula estatisticas de bandwidth e time buckets.

        Args:
            summary: PcapSummary a preencher.
            frame_sizes: Lista de tamanhos de frame por pacote.
            per_second_bytes: Bytes por segundo (chave = epoch inteiro).
            timestamps: Lista de timestamps de pacotes.
            proto_per_packet: Protocolo de cada pacote (mesmo indice de frame_sizes).
        """
        if not frame_sizes:
            return

        summary.total_bytes = sum(frame_sizes)

        # Frame size stats
        summary.frame_size_stats = {
            "min": min(frame_sizes),
            "max": max(frame_sizes),
            "avg": round(statistics.mean(frame_sizes), 1),
            "median": round(statistics.median(frame_sizes), 1),
        }

        # Frame size distribution
        dist: dict[str, int] = {}
        for size in frame_sizes:
            for low, high, label in _FRAME_SIZE_BUCKETS:
                if low <= size <= high:
                    dist[label] = dist.get(label, 0) + 1
                    break
            else:
                dist["9001+"] = dist.get("9001+", 0) + 1
        summary.frame_size_distribution = dist

        # Throughput
        duration = summary.duration_seconds
        if duration > 0:
            summary.avg_throughput_bps = round(
                (summary.total_bytes * 8) / duration, 1
            )
            if per_second_bytes:
                peak_bytes_sec = max(per_second_bytes.values())
                summary.peak_throughput_bps = round(peak_bytes_sec * 8, 1)

        # Time buckets
        PcapAnalyzerService._compute_time_buckets(
            summary, timestamps, frame_sizes, proto_per_packet,
        )

    @staticmethod
    def _compute_time_buckets(
        summary: PcapSummary,
        timestamps: list[float],
        frame_sizes: list[int],
        proto_per_packet: list[str],
    ) -> None:
        """Divide captura em buckets temporais com packets, bytes e top protocol.

        Args:
            summary: PcapSummary a preencher.
            timestamps: Timestamps de pacotes.
            frame_sizes: Tamanhos de frame (mesmo indice).
            proto_per_packet: Protocolo por pacote (mesmo indice).
        """
        if len(timestamps) < 2:
            return

        t_min = min(timestamps)
        t_max = max(timestamps)
        duration = t_max - t_min
        if duration <= 0:
            return

        width = _select_bucket_width(duration)
        summary.bucket_width_seconds = width

        num_buckets = math.ceil(duration / width) + 1
        bucket_packets = [0] * num_buckets
        bucket_bytes = [0] * num_buckets
        bucket_protos: list[Counter[str]] = [Counter() for _ in range(num_buckets)]

        for i, ts in enumerate(timestamps):
            idx = min(int((ts - t_min) / width), num_buckets - 1)
            bucket_packets[idx] += 1
            bucket_bytes[idx] += frame_sizes[i]
            bucket_protos[idx][proto_per_packet[i]] += 1

        buckets = []
        for i in range(num_buckets):
            if bucket_packets[i] == 0:
                continue
            top_protos = dict(bucket_protos[i].most_common(5))
            buckets.append({
                "time_offset": round(i * width, 2),
                "packets": bucket_packets[i],
                "bytes": bucket_bytes[i],
                "top_protocols": top_protos,
            })

        summary.time_buckets = buckets

    @staticmethod
    def _detect_bandwidth_anomalies(summary: PcapSummary) -> None:
        """Detecta anomalias de bandwidth (spikes, jumbo frames).

        Args:
            summary: PcapSummary com bandwidth stats ja preenchidos.
        """
        if not summary.time_buckets or summary.avg_throughput_bps <= 0:
            return

        avg_bytes_per_bucket = summary.total_bytes / max(len(summary.time_buckets), 1)

        # Spike: bucket com >3x a media de bytes
        for bucket in summary.time_buckets:
            if avg_bytes_per_bucket > 0 and bucket["bytes"] > avg_bytes_per_bucket * 3:
                summary.anomalies.append(
                    f"BANDWIDTH SPIKE: {_format_bytes(bucket['bytes'])} at "
                    f"t={bucket['time_offset']}s (>{3}x average per bucket)"
                )
                break  # Apenas primeiro spike

        # Micro-burst: pico >10x avg/sec
        if summary.peak_throughput_bps > summary.avg_throughput_bps * 10:
            summary.anomalies.append(
                f"MICRO-BURST: peak {_format_bps(summary.peak_throughput_bps)} "
                f"vs avg {_format_bps(summary.avg_throughput_bps)} (>10x)"
            )

        # Jumbo frames
        jumbo_count = summary.frame_size_distribution.get("1519-9000 (Jumbo)", 0)
        over_jumbo = summary.frame_size_distribution.get("9001+", 0)
        if jumbo_count + over_jumbo > 0:
            summary.anomalies.append(
                f"JUMBO FRAMES: {jumbo_count + over_jumbo} frames >1518 bytes detected"
            )

    @staticmethod
    def _get_notable_periods(summary: PcapSummary) -> list[str]:
        """Extrai ate 8 observacoes textuais de periodos notaveis para o LLM.

        Args:
            summary: PcapSummary com time_buckets preenchidos.

        Returns:
            Lista de observacoes em texto (max 8).
        """
        if not summary.time_buckets:
            return []

        notes: list[str] = []
        buckets = summary.time_buckets
        width = summary.bucket_width_seconds

        if len(buckets) < 2:
            return []

        bytes_values = [b["bytes"] for b in buckets]
        avg_bytes = statistics.mean(bytes_values) if bytes_values else 0

        # Buscar picos e vales
        for b in buckets:
            if avg_bytes > 0 and b["bytes"] > avg_bytes * 3:
                top_proto = max(b["top_protocols"], key=b["top_protocols"].get) if b["top_protocols"] else "Unknown"
                notes.append(
                    f"Spike at t={b['time_offset']}s: "
                    f"{_format_bytes(b['bytes'])} ({top_proto} dominant)"
                )
            elif avg_bytes > 0 and b["bytes"] < avg_bytes * 0.1 and b["packets"] > 0:
                notes.append(
                    f"Quiet period at t={b['time_offset']}s: "
                    f"only {b['packets']} packets"
                )
            if len(notes) >= 8:
                break

        # Protocol shift detection
        if len(buckets) >= 4:
            first_quarter = buckets[:len(buckets) // 4]
            last_quarter = buckets[-(len(buckets) // 4):]
            first_protos = Counter()
            last_protos = Counter()
            for b in first_quarter:
                first_protos.update(b["top_protocols"])
            for b in last_quarter:
                last_protos.update(b["top_protocols"])
            first_top = first_protos.most_common(1)[0][0] if first_protos else None
            last_top = last_protos.most_common(1)[0][0] if last_protos else None
            if first_top and last_top and first_top != last_top and len(notes) < 8:
                notes.append(
                    f"Protocol shift: dominant protocol changed from "
                    f"{first_top} to {last_top}"
                )

        return notes[:8]

    # ------------------------------------------------------------------
    # Phase B: HTTP/TLS anomalies
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_http_tls_anomalies(summary: PcapSummary) -> None:
        """Detecta anomalias em trafego HTTP e TLS.

        Args:
            summary: PcapSummary com HTTP/TLS stats preenchidos.
        """
        # HTTP 5xx errors
        total_5xx = sum(
            count for code, count in summary.http_status_codes.items()
            if code.startswith("5")
        )
        if total_5xx > 10:
            summary.anomalies.append(
                f"HTTP SERVER ERRORS: {total_5xx} responses with 5xx status codes"
            )

        # HTTP 4xx > 30% dos requests
        total_4xx = sum(
            count for code, count in summary.http_status_codes.items()
            if code.startswith("4")
        )
        total_responses = sum(summary.http_status_codes.values())
        if total_responses > 0 and total_4xx > total_responses * 0.3:
            pct = round(total_4xx * 100 / total_responses, 1)
            summary.anomalies.append(
                f"HIGH HTTP CLIENT ERROR RATE: {total_4xx} 4xx responses "
                f"({pct}% of all responses)"
            )

        # TLS deprecated versions
        deprecated_count = sum(
            count for ver, count in summary.tls_versions.items()
            if ver in _TLS_DEPRECATED_VERSIONS
        )
        if deprecated_count > 0:
            dep_versions = [
                ver for ver in summary.tls_versions if ver in _TLS_DEPRECATED_VERSIONS
            ]
            summary.anomalies.append(
                f"DEPRECATED TLS: {deprecated_count} connections using "
                f"{', '.join(dep_versions)} — upgrade recommended"
            )

    # ------------------------------------------------------------------
    # Phase C: VoIP/SIP anomalies
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_voip_anomalies(summary: PcapSummary) -> None:
        """Detecta anomalias em trafego VoIP/SIP.

        Args:
            summary: PcapSummary com VoIP stats preenchidos.
        """
        # SIP auth failures (401/403/407)
        auth_failures = sum(
            count for code, count in summary.voip_sip_responses.items()
            if any(code.startswith(c) for c in ("401", "403", "407"))
        )
        if auth_failures > 5:
            summary.anomalies.append(
                f"SIP AUTH FAILURES: {auth_failures} authentication failures "
                f"(401/403/407) — possible credential issue or brute-force"
            )

        # SIP busy/decline (486/600)
        busy_count = sum(
            count for code, count in summary.voip_sip_responses.items()
            if any(code.startswith(c) for c in ("486", "600"))
        )
        if busy_count > 10:
            summary.anomalies.append(
                f"SIP BUSY/DECLINE: {busy_count} busy/decline responses "
                f"(486/600) — possible capacity issue"
            )

    # ------------------------------------------------------------------
    # Formatacao
    # ------------------------------------------------------------------

    def format_summary(self, summary: PcapSummary) -> str:
        """Formata PcapSummary como texto para o LLM.

        Args:
            summary: Resultado da analise.

        Returns:
            Texto formatado em Markdown.
        """
        if summary.is_wireless:
            return self._format_wireless_summary(summary)
        return self._format_wired_summary(summary)

    def _format_wired_summary(self, summary: PcapSummary) -> str:
        """Formata analise de captura Ethernet/IP."""
        parts: list[str] = ["## PCAP Analysis Summary"]

        parts.append(f"\n**Total Packets:** {summary.total_packets}")
        parts.append(f"**Duration:** {summary.duration_seconds}s")
        if summary.total_bytes:
            parts.append(f"**Total Data:** {_format_bytes(summary.total_bytes)}")

        # Bandwidth & Throughput
        if summary.avg_throughput_bps > 0:
            parts.append("\n### Bandwidth & Throughput")
            parts.append(f"- Average: {_format_bps(summary.avg_throughput_bps)}")
            if summary.peak_throughput_bps:
                parts.append(f"- Peak: {_format_bps(summary.peak_throughput_bps)}")
            if summary.frame_size_stats:
                fs = summary.frame_size_stats
                parts.append(
                    f"- Frame sizes: min={int(fs['min'])}B, max={int(fs['max'])}B, "
                    f"avg={fs['avg']}B, median={fs['median']}B"
                )
            if summary.frame_size_distribution:
                parts.append("- Frame size distribution:")
                for label, count in summary.frame_size_distribution.items():
                    parts.append(f"  - {label} bytes: {count} frames")

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

        # Top talkers (enriquecido com bytes)
        if summary.top_talkers:
            parts.append("\n### Top Talkers")
            for t in summary.top_talkers[:10]:
                byte_str = f" ({_format_bytes(t['bytes'])})" if t.get("bytes") else ""
                parts.append(f"- {t['ip']}: {t['packets']} packets{byte_str}")

        # Conversations (enriquecido com bytes)
        if summary.conversations:
            parts.append("\n### Top Conversations")
            for c in summary.conversations[:10]:
                byte_str = f" ({_format_bytes(c['bytes'])})" if c.get("bytes") else ""
                parts.append(
                    f"- {c['src']} <-> {c['dst']}: {c['packets']} packets{byte_str}"
                )

        # DNS
        if summary.dns_queries:
            parts.append(f"\n### DNS Queries ({len(summary.dns_queries)} unique)")
            for q in summary.dns_queries[:20]:
                parts.append(f"- {q}")
            if len(summary.dns_queries) > 20:
                parts.append(f"... and {len(summary.dns_queries) - 20} more")

        # HTTP Analysis
        if summary.http_request_count or summary.http_response_count:
            parts.append("\n### HTTP Analysis")
            parts.append(
                f"- Requests: {summary.http_request_count}, "
                f"Responses: {summary.http_response_count}"
            )
            if summary.http_methods:
                parts.append("- Methods: " + ", ".join(
                    f"{m}: {c}" for m, c in summary.http_methods.items()
                ))
            if summary.http_status_codes:
                parts.append("- Status codes:")
                for code, count in summary.http_status_codes.items():
                    parts.append(f"  - {code}: {count}")
            if summary.http_hosts:
                parts.append(f"- Hosts ({len(summary.http_hosts)}):")
                for host in summary.http_hosts[:15]:
                    parts.append(f"  - {host}")
            if summary.http_urls:
                parts.append(f"- Top URLs ({len(summary.http_urls)}):")
                # Dedupe para exibicao
                seen: set[str] = set()
                shown = 0
                for url in summary.http_urls:
                    if url not in seen and shown < 15:
                        parts.append(f"  - {url}")
                        seen.add(url)
                        shown += 1

        # TLS/SSL Analysis
        if summary.tls_versions:
            parts.append("\n### TLS/SSL Analysis")
            parts.append("- Versions:")
            for ver, count in summary.tls_versions.items():
                dep_marker = " ⚠ DEPRECATED" if ver in _TLS_DEPRECATED_VERSIONS else ""
                parts.append(f"  - {ver}: {count} connections{dep_marker}")
            if summary.tls_handshakes:
                hs = summary.tls_handshakes
                parts.append(
                    f"- Handshakes: {hs.get('client_hello', 0)} ClientHello, "
                    f"{hs.get('server_hello', 0)} ServerHello"
                )
            if summary.tls_sni_hosts:
                parts.append(f"- SNI Hostnames ({len(summary.tls_sni_hosts)}):")
                for host in summary.tls_sni_hosts[:15]:
                    parts.append(f"  - {host}")
            if summary.tls_cipher_suites:
                parts.append(f"- Cipher Suites ({len(summary.tls_cipher_suites)}):")
                for cipher in summary.tls_cipher_suites[:10]:
                    parts.append(f"  - {cipher}")

        # VoIP/SIP Analysis
        if summary.voip_sip_methods or summary.voip_sip_responses or summary.voip_rtp_streams:
            parts.append("\n### VoIP/SIP Analysis")
            if summary.voip_sip_methods:
                parts.append("- SIP Methods: " + ", ".join(
                    f"{m}: {c}" for m, c in summary.voip_sip_methods.items()
                ))
            if summary.voip_sip_responses:
                parts.append("- SIP Responses:")
                for code, count in summary.voip_sip_responses.items():
                    parts.append(f"  - {code}: {count}")
            if summary.voip_rtp_streams:
                parts.append(f"- RTP Streams: {summary.voip_rtp_streams}")
            if summary.voip_rtp_codecs:
                parts.append("- RTP Codecs: " + ", ".join(summary.voip_rtp_codecs))

        # Traffic Timeline (notable periods)
        notable = self._get_notable_periods(summary)
        if notable:
            parts.append("\n### Traffic Timeline")
            for note in notable:
                parts.append(f"- {note}")

        # Anomalies
        if summary.anomalies:
            parts.append("\n### Anomalies Detected")
            for a in summary.anomalies:
                parts.append(f"- {a}")

        # TCP issues detail
        if summary.tcp_issues:
            parts.append(f"\n### TCP Issues ({len(summary.tcp_issues)} shown)")
            for issue in summary.tcp_issues[:10]:
                parts.append(
                    f"- {issue['type']}: {issue['src']} -> {issue['dst']} "
                    f"(seq={issue['seq']})"
                )

        if not summary.anomalies:
            parts.append("\n### No anomalies detected")
            parts.append("The capture appears normal based on automated checks.")

        return "\n".join(parts)

    def _format_wireless_summary(self, summary: PcapSummary) -> str:
        """Formata analise de captura 802.11 Wi-Fi."""
        parts: list[str] = ["## Wi-Fi (802.11) PCAP Analysis"]

        parts.append(f"\n**Total Packets:** {summary.total_packets}")
        parts.append(f"**Duration:** {summary.duration_seconds}s")
        parts.append("**Capture Type:** Wireless (802.11)")
        if summary.total_bytes:
            parts.append(
                f"**Total Data:** {_format_bytes(summary.total_bytes)} "
                f"(includes RadioTap/802.11 overhead)"
            )

        # Frame types
        if summary.wireless_frame_types:
            parts.append("\n### Frame Type Distribution")
            for frame_type, count in summary.wireless_frame_types.items():
                pct = count * 100 // max(summary.total_packets, 1)
                parts.append(f"- {frame_type}: {count} ({pct}%)")

        # Protocol distribution
        if summary.protocols:
            parts.append("\n### Protocol Distribution")
            for proto, count in summary.protocols.items():
                pct = count * 100 // max(summary.total_packets, 1)
                parts.append(f"- {proto}: {count} ({pct}%)")

        # Channels
        if summary.channels:
            parts.append("\n### Channels")
            for channel, count in summary.channels.items():
                band = "2.4 GHz" if channel <= 14 else "5 GHz"
                parts.append(f"- Channel {channel} ({band}): {count} packets")

        # SSIDs
        if summary.ssids:
            parts.append(f"\n### SSIDs Detected ({len(summary.ssids)})")
            for ssid in summary.ssids:
                parts.append(f"- {ssid}")
        else:
            parts.append("\n### SSIDs Detected: None (hidden or no beacons)")

        # Signal strength
        if summary.signal_stats:
            s = summary.signal_stats
            parts.append("\n### Signal Strength")
            parts.append(f"- Min: {s['min_dBm']} dBm")
            parts.append(f"- Max: {s['max_dBm']} dBm")
            parts.append(f"- Average: {s['avg_dBm']} dBm")
            parts.append(f"- Median: {s['median_dBm']} dBm")
            parts.append(f"- Samples: {int(s['samples'])}")

        # Retry rate
        if summary.retry_stats:
            r = summary.retry_stats
            parts.append("\n### Retry Rate")
            parts.append(
                f"- {int(r['retries'])} retries out of {int(r['total_frames'])} frames "
                f"({r['rate_pct']}%)"
            )

        # Deauthentication events
        if summary.deauth_events:
            parts.append(
                f"\n### Deauthentication Events ({len(summary.deauth_events)})"
            )
            parts.append("| Timestamp | Source | Destination | Reason |")
            parts.append("|-----------|--------|-------------|--------|")
            for evt in summary.deauth_events[:20]:
                parts.append(
                    f"| {evt['timestamp']}s | {evt['src']} | {evt['dst']} | "
                    f"{evt['reason_text']} (code {evt['reason']}) |"
                )
            if len(summary.deauth_events) > 20:
                parts.append(
                    f"... and {len(summary.deauth_events) - 20} more events"
                )

        # Disassociation events
        if summary.disassoc_events:
            parts.append(
                f"\n### Disassociation Events ({len(summary.disassoc_events)})"
            )
            parts.append("| Timestamp | Source | Destination | Reason |")
            parts.append("|-----------|--------|-------------|--------|")
            for evt in summary.disassoc_events[:20]:
                parts.append(
                    f"| {evt['timestamp']}s | {evt['src']} | {evt['dst']} | "
                    f"{evt['reason_text']} (code {evt['reason']}) |"
                )
            if len(summary.disassoc_events) > 20:
                parts.append(
                    f"... and {len(summary.disassoc_events) - 20} more events"
                )

        # Bandwidth & Throughput (wireless)
        if summary.avg_throughput_bps > 0:
            parts.append("\n### Bandwidth & Throughput")
            parts.append(f"- Average: {_format_bps(summary.avg_throughput_bps)}")
            if summary.peak_throughput_bps:
                parts.append(f"- Peak: {_format_bps(summary.peak_throughput_bps)}")
            if summary.frame_size_stats:
                fs = summary.frame_size_stats
                parts.append(
                    f"- Frame sizes: min={int(fs['min'])}B, max={int(fs['max'])}B, "
                    f"avg={fs['avg']}B, median={fs['median']}B"
                )

        # Top wireless devices (enriquecido com bytes)
        if summary.wireless_devices:
            parts.append(
                f"\n### Top Wireless Devices ({len(summary.wireless_devices)})"
            )
            for dev in summary.wireless_devices[:15]:
                byte_str = f" ({_format_bytes(dev['bytes'])})" if dev.get("bytes") else ""
                parts.append(f"- {dev['mac']}: {dev['packets']} packets{byte_str}")

        # Traffic Timeline (notable periods)
        notable = self._get_notable_periods(summary)
        if notable:
            parts.append("\n### Traffic Timeline")
            for note in notable:
                parts.append(f"- {note}")

        # Anomalies
        if summary.anomalies:
            parts.append("\n### Anomalies Detected")
            for a in summary.anomalies:
                parts.append(f"- WARNING: {a}")
        else:
            parts.append("\n### No anomalies detected")
            parts.append("The wireless capture appears normal based on automated checks.")

        return "\n".join(parts)
