"""
PCAP tools para o agent LangGraph — analyze_pcap.

Precisa de db + user_id para acessar arquivo via Document model.
Despacha analise para Celery worker.
"""
from __future__ import annotations

import asyncio
import os
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
            return f"Invalid document ID: '{document_id}'. Expected a UUID."

        try:
            # Valida documento pertence ao usuario
            result = await db.execute(
                select(Document).where(
                    Document.id == doc_uuid,
                    Document.user_id == user_id,
                )
            )
            document = result.scalar_one_or_none()

            if not document:
                return (
                    f"Document '{document_id}' not found or does not belong to you."
                )

            if document.file_type not in ("pcap", "pcapng"):
                return (
                    f"Document '{document.original_filename}' is not a PCAP file "
                    f"(type: {document.file_type})."
                )

            if not os.path.exists(document.storage_path):
                return (
                    f"PCAP file not found on disk. The file may have been removed."
                )

            # Despacha para Celery worker
            from app.workers.tasks.pcap_tasks import analyze_pcap

            task_result = analyze_pcap.delay(
                document.storage_path,
                settings.PCAP_MAX_PACKETS,
            )

            # Aguarda resultado sem bloquear event loop
            result_data = await asyncio.to_thread(
                task_result.get, timeout=settings.PCAP_ANALYSIS_TIMEOUT
            )

            return result_data["formatted"]
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
