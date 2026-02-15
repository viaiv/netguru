"""
PCAP tools para o agent LangGraph — analyze_pcap.

Precisa de db + user_id para acessar arquivo via Document model.
Despacha analise para Celery worker.
"""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from langchain_core.tools import StructuredTool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document

logger = logging.getLogger(__name__)


def _lazy_pcap_service():
    """Cria instancia do PcapAnalyzerService sem __init__ (para format_summary)."""
    from app.services.pcap_analyzer_service import PcapAnalyzerService
    return object.__new__(PcapAnalyzerService)


def create_analyze_pcap_tool(
    db: AsyncSession, user_id: UUID, *, workspace_id: UUID | None = None,
) -> StructuredTool:
    """Cria tool de analise de PCAPs."""

    # Escopo de busca: workspace quando disponivel, senao user_id
    _scope_workspace_id = workspace_id
    _scope_user_id = user_id

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
                # Busca por UUID escopada por workspace ou user_id
                if _scope_workspace_id:
                    result = await db.execute(
                        select(Document).where(
                            Document.id == doc_uuid,
                            Document.workspace_id == _scope_workspace_id,
                        )
                    )
                else:
                    result = await db.execute(
                        select(Document).where(
                            Document.id == doc_uuid,
                            Document.user_id == _scope_user_id,
                        )
                    )
                document = result.scalar_one_or_none()
            else:
                # Busca por filename escopada por workspace ou user_id
                scope_filter = (
                    Document.workspace_id == _scope_workspace_id
                    if _scope_workspace_id
                    else Document.user_id == _scope_user_id
                )
                result = await db.execute(
                    select(Document)
                    .where(
                        scope_filter,
                        Document.original_filename == document_id,
                        Document.file_type.in_(("pcap", "pcapng")),
                    )
                    .order_by(Document.created_at.desc())
                    .limit(1)
                )
                document = result.scalar_one_or_none()

            if not document:
                logger.warning(
                    "analyze_pcap: document not found. "
                    "document_id=%s user_id=%s",
                    document_id,
                    user_id,
                )
                # Listar PCAPs recentes do usuario para ajudar o LLM
                return await _build_not_found_message(document_id)

            if document.status == "pending_upload":
                logger.warning(
                    "analyze_pcap: document still pending upload. "
                    "document_id=%s status=%s user_id=%s",
                    document.id,
                    document.status,
                    user_id,
                )
                return (
                    f"O arquivo '{document.original_filename}' ainda esta sendo "
                    f"enviado (status: pending_upload). Aguarde o upload completar "
                    f"e tente novamente."
                )

            if document.file_type not in ("pcap", "pcapng"):
                return (
                    f"Document '{document.original_filename}' is not a PCAP file "
                    f"(type: {document.file_type})."
                )

            # Verifica se ja tem resultado em cache (Document.metadata)
            cached = document.document_metadata
            if isinstance(cached, dict) and "pcap_analysis" in cached:
                try:
                    logger.info("analyze_pcap: usando resultado em cache doc=%s", document.id)
                    svc = _lazy_pcap_service()
                    from app.services.pcap_analyzer_service import PcapSummary
                    import dataclasses
                    valid_fields = {f.name for f in dataclasses.fields(PcapSummary)}
                    filtered = {k: v for k, v in cached["pcap_analysis"].items() if k in valid_fields}
                    summary = PcapSummary(**filtered)
                    formatted = svc.format_summary(summary)
                    pcap_data = json.dumps(cached["pcap_analysis"], default=str, ensure_ascii=False)
                    return f"{formatted}\n<!-- PCAP_DATA:{pcap_data} -->"
                except Exception:
                    logger.warning("analyze_pcap: cache invalido, re-analisando doc=%s", document.id)

            # Despacha para Celery worker (o worker baixa do R2 se necessario)
            from app.workers.tasks.pcap_tasks import analyze_pcap

            task_result = analyze_pcap.delay(
                document.storage_path,
                settings.PCAP_MAX_PACKETS,
                str(document.id),
            )

            # Polling assincrono — verifica estado a cada 2s sem bloquear event loop
            timeout = settings.PCAP_ANALYSIS_TIMEOUT
            elapsed = 0.0
            poll_interval = 2.0

            while elapsed < timeout:
                state = await asyncio.to_thread(lambda: task_result.state)

                if state == "SUCCESS":
                    result_data = await asyncio.to_thread(lambda: task_result.result)
                    formatted = result_data["formatted"]
                    pcap_data = json.dumps(
                        result_data.get("data", {}),
                        default=str,
                        ensure_ascii=False,
                    )
                    return f"{formatted}\n<!-- PCAP_DATA:{pcap_data} -->"

                if state == "FAILURE":
                    exc_info = await asyncio.to_thread(lambda: task_result.info)
                    return f"PCAP analysis failed: {exc_info}"

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            return (
                f"PCAP analysis timed out after {timeout}s. "
                f"The file may be too large. Try with a smaller capture."
            )
        except Exception as e:
            logger.exception(
                "analyze_pcap: unexpected error. document_id=%s user_id=%s",
                document_id,
                user_id,
            )
            return f"Error analyzing PCAP: {e}"

    async def _build_not_found_message(document_id: str) -> str:
        """Monta mensagem de 'not found' com lista de PCAPs disponiveis."""
        try:
            scope_filter = (
                Document.workspace_id == _scope_workspace_id
                if _scope_workspace_id
                else Document.user_id == _scope_user_id
            )
            result = await db.execute(
                select(Document)
                .where(
                    scope_filter,
                    Document.file_type.in_(("pcap", "pcapng")),
                    Document.status == "uploaded",
                )
                .order_by(Document.created_at.desc())
                .limit(5)
            )
            recent_pcaps = result.scalars().all()
        except Exception:
            recent_pcaps = []

        msg = f"Document '{document_id}' not found."
        if recent_pcaps:
            pcap_list = ", ".join(
                f"{doc.original_filename} (UUID: {doc.id})"
                for doc in recent_pcaps
            )
            msg += (
                f" PCAPs disponiveis para este usuario: {pcap_list}. "
                f"Use o UUID correto do arquivo desejado."
            )
        else:
            msg += (
                " Nenhum PCAP foi encontrado para este usuario. "
                "O arquivo pode nao ter sido enviado corretamente. "
                "Solicite ao usuario que reenvie o arquivo."
            )
        return msg

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
