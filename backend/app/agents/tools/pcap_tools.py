"""
PCAP tools para o agent LangGraph — analyze_pcap.

Precisa de db + user_id para acessar arquivo via Document model.
"""
from __future__ import annotations

import os
from uuid import UUID

from langchain_core.tools import StructuredTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pcap_analyzer_service import PcapAnalyzerService


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
            return f"Invalid document ID: '{document_id}'. Expected a UUID."

        try:
            svc = PcapAnalyzerService(db)

            # Valida documento pertence ao usuario
            document = await svc.get_document(doc_uuid, user_id)
            if not document:
                return (
                    f"Document '{document_id}' not found or does not belong to you."
                )

            # Valida tipo de arquivo
            if document.file_type not in ("pcap", "pcapng"):
                return (
                    f"Document '{document.original_filename}' is not a PCAP file "
                    f"(type: {document.file_type})."
                )

            # Valida arquivo existe no disco
            if not os.path.exists(document.storage_path):
                return (
                    f"PCAP file not found on disk. The file may have been removed."
                )

            # Analisa
            summary = await svc.analyze(document.storage_path)
            return svc.format_summary(summary)
        except Exception as e:
            return f"Error analyzing PCAP: {e}"

    return StructuredTool.from_function(
        coroutine=_analyze_pcap,
        name="analyze_pcap",
        description=(
            "Analyze a PCAP/PCAPNG packet capture file uploaded by the user. "
            "Extracts protocol distribution, top talkers, conversations, DNS queries, "
            "TCP issues (retransmissions, resets), and detects network protocols (OSPF, BGP, etc.). "
            "Use when the user asks about a packet capture or PCAP analysis. "
            "Input: the document_id (UUID) of the uploaded PCAP file."
        ),
    )
