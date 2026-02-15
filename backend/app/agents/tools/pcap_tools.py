"""
PCAP tools para o agent LangGraph — analyze_pcap.

Precisa de db + user_id para acessar arquivo via Document model.
Despacha analise para Celery worker.
"""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

from langchain_core.tools import StructuredTool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document


def create_analyze_pcap_tool(db: AsyncSession, user_id: UUID) -> StructuredTool:
    """Cria tool de analise de PCAPs."""

    async def _analyze_pcap(document_id: str) -> str:
        """
        Analyze a PCAP/PCAPNG file that the user has previously uploaded.
        Extracts protocol distribution, top talkers, conversations, DNS queries,
        TCP issues (retransmissions, RST floods), and network protocol detection
        (OSPF, BGP, EIGRP, HSRP).

        Use this tool when the user asks to analyze a packet capture or mentions
        a PCAP file they uploaded.

        Args:
            document_id: The UUID of the uploaded PCAP document.
        """
        try:
            doc_uuid = UUID(document_id)
        except ValueError:
            doc_uuid = None

        try:
            document = None
            if doc_uuid is not None:
                # Busca por UUID + user_id
                result = await db.execute(
                    select(Document).where(
                        Document.id == doc_uuid,
                        Document.user_id == user_id,
                    )
                )
                document = result.scalar_one_or_none()

                # Fallback: buscar sem user_id (doc pode ter user_id NULL ou mismatch)
                if document is None:
                    result = await db.execute(
                        select(Document).where(Document.id == doc_uuid)
                    )
                    document = result.scalar_one_or_none()
            else:
                # Fallback: busca por filename (LLM pode passar nome ao inves de UUID)
                result = await db.execute(
                    select(Document)
                    .where(
                        Document.user_id == user_id,
                        Document.original_filename == document_id,
                        Document.file_type.in_(("pcap", "pcapng")),
                    )
                    .order_by(Document.created_at.desc())
                    .limit(1)
                )
                document = result.scalar_one_or_none()

                # Fallback: buscar sem user_id
                if document is None:
                    result = await db.execute(
                        select(Document)
                        .where(
                            Document.original_filename == document_id,
                            Document.file_type.in_(("pcap", "pcapng")),
                        )
                        .order_by(Document.created_at.desc())
                        .limit(1)
                    )
                    document = result.scalar_one_or_none()

            if not document:
                return (
                    f"Document '{document_id}' not found."
                )

            if document.file_type not in ("pcap", "pcapng"):
                return (
                    f"Document '{document.original_filename}' is not a PCAP file "
                    f"(type: {document.file_type})."
                )

            # Despacha para Celery worker (o worker baixa do R2 se necessario)
            from app.workers.tasks.pcap_tasks import analyze_pcap

            task_result = analyze_pcap.delay(
                document.storage_path,
                settings.PCAP_MAX_PACKETS,
            )

            # Aguarda resultado sem bloquear event loop
            result_data = await asyncio.to_thread(
                task_result.get, timeout=settings.PCAP_ANALYSIS_TIMEOUT
            )

            formatted = result_data["formatted"]
            pcap_data = json.dumps(
                result_data.get("data", {}),
                default=str,
                ensure_ascii=False,
            )
            return f"{formatted}\n<!-- PCAP_DATA:{pcap_data} -->"
        except Exception as e:
            return f"Error analyzing PCAP: {e}"

    return StructuredTool.from_function(
        coroutine=_analyze_pcap,
        name="analyze_pcap",
        description=(
            "Analyze a PCAP/PCAPNG packet capture file. Auto-detects wired (Ethernet/IP) "
            "vs wireless (802.11) captures. "
            "For wired: protocol distribution, top talkers with bytes, conversations, "
            "DNS queries, TCP issues, routing protocols, bandwidth/throughput stats, "
            "frame size distribution, time-series traffic buckets, HTTP methods/status codes/"
            "URLs/hosts, TLS versions/SNI/cipher suites, VoIP SIP methods/responses, "
            "RTP stream count/codecs. "
            "For wireless (Wi-Fi): frame type distribution, deauth/disassoc events with "
            "reason codes, retry rate, signal strength (dBm), channels, SSIDs, bandwidth "
            "stats, and wireless anomaly detection (deauth floods, high retries). "
            "Use when the user asks about a packet capture or PCAP analysis. "
            "Input: the document_id (UUID) of the uploaded PCAP file. "
            "IMPORTANT: always pass the UUID from [CONTEXTO_AUTOMATICO_DE_ANEXO], never the filename."
        ),
    )
