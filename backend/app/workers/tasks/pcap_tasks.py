"""
Celery task para analise de PCAP.

Sem acesso a DB — a validacao de ownership e feita no tool do agent.
"""
from __future__ import annotations

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.pcap_tasks.analyze_pcap")
def analyze_pcap(file_path: str, max_packets: int) -> dict:
    """
    Analisa PCAP via scapy no worker.

    Args:
        file_path: Caminho do arquivo PCAP no disco.
        max_packets: Maximo de pacotes a processar.

    Returns:
        Dict com 'formatted' (texto para LLM) e 'data' (dados estruturados).
    """
    from app.services.pcap_analyzer_service import PcapAnalyzerService

    logger.info("Iniciando analise PCAP: %s (max=%d)", file_path, max_packets)

    # Instancia service sem DB (metodo _analyze_sync nao precisa)
    svc = object.__new__(PcapAnalyzerService)
    summary = svc._analyze_sync(file_path, max_packets)
    formatted = svc.format_summary(summary)

    return {
        "formatted": formatted,
        "data": {
            "total_packets": summary.total_packets,
            "duration_seconds": summary.duration_seconds,
            "protocols": summary.protocols,
            "top_talkers": summary.top_talkers,
            "conversations": summary.conversations,
            "anomalies": summary.anomalies,
            "dns_queries": summary.dns_queries,
            "tcp_issues": summary.tcp_issues,
            "network_protocols": summary.network_protocols,
        },
    }
