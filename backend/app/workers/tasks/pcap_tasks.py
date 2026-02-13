"""
Celery task para analise de PCAP.

Suporta arquivos locais e objetos no R2.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _is_r2_path(storage_path: str) -> bool:
    """Retorna True se o storage_path e uma chave R2."""
    return storage_path.startswith("uploads/") and not Path(storage_path).is_absolute()


@celery_app.task(name="app.workers.tasks.pcap_tasks.analyze_pcap")
def analyze_pcap(storage_path: str, max_packets: int) -> dict:
    """
    Analisa PCAP via scapy no worker.

    Args:
        storage_path: Caminho local ou chave R2 do arquivo PCAP.
        max_packets: Maximo de pacotes a processar.

    Returns:
        Dict com 'formatted' (texto para LLM) e 'data' (dados estruturados).
    """
    from app.services.pcap_analyzer_service import PcapAnalyzerService

    temp_path = None

    try:
        if _is_r2_path(storage_path):
            from app.core.database_sync import get_sync_db
            from app.services.r2_storage_service import R2StorageService

            suffix = Path(storage_path).suffix or ".pcap"
            with get_sync_db() as db:
                r2 = R2StorageService.from_settings_sync(db)
                temp_path = r2.download_to_tempfile(storage_path, suffix)
            file_path = str(temp_path)
            logger.info("Baixou R2 -> %s", file_path)
        else:
            file_path = storage_path

        logger.info("Iniciando analise PCAP: %s (max=%d)", file_path, max_packets)

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
                # Bandwidth & time-series
                "total_bytes": summary.total_bytes,
                "avg_throughput_bps": summary.avg_throughput_bps,
                "peak_throughput_bps": summary.peak_throughput_bps,
                "frame_size_stats": summary.frame_size_stats,
                "frame_size_distribution": summary.frame_size_distribution,
                "time_buckets": summary.time_buckets,
                "bucket_width_seconds": summary.bucket_width_seconds,
                # HTTP
                "http_methods": summary.http_methods,
                "http_status_codes": summary.http_status_codes,
                "http_urls": summary.http_urls,
                "http_hosts": summary.http_hosts,
                "http_request_count": summary.http_request_count,
                "http_response_count": summary.http_response_count,
                # TLS
                "tls_versions": summary.tls_versions,
                "tls_sni_hosts": summary.tls_sni_hosts,
                "tls_cipher_suites": summary.tls_cipher_suites,
                "tls_handshakes": summary.tls_handshakes,
                # VoIP/SIP
                "voip_sip_methods": summary.voip_sip_methods,
                "voip_sip_responses": summary.voip_sip_responses,
                "voip_rtp_streams": summary.voip_rtp_streams,
                "voip_rtp_codecs": summary.voip_rtp_codecs,
                # Campos wireless (802.11)
                "is_wireless": summary.is_wireless,
                "wireless_frame_types": summary.wireless_frame_types,
                "deauth_events": summary.deauth_events,
                "disassoc_events": summary.disassoc_events,
                "retry_stats": summary.retry_stats,
                "signal_stats": summary.signal_stats,
                "channels": {str(k): v for k, v in summary.channels.items()},
                "ssids": summary.ssids,
                "wireless_devices": summary.wireless_devices,
            },
        }
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
