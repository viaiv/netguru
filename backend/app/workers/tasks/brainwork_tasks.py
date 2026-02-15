"""
Celery task para crawling do blog brainwork.com.br.
"""
from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run_crawl(max_pages: int | None = None) -> dict:
    """Executa o crawler em contexto async com sessao propria."""
    from app.core.database import AsyncSessionLocal
    from app.services.brainwork_crawler_service import BrainworkCrawlerService

    async with AsyncSessionLocal() as db:
        try:
            service = BrainworkCrawlerService(db)
            result = await service.crawl(max_pages=max_pages)
            await db.commit()
            return {
                "total_urls": result.total_urls,
                "new_urls": result.new_urls,
                "ingested": result.ingested,
                "failed": result.failed,
                "errors": result.errors,
            }
        except Exception:
            await db.rollback()
            raise


@celery_app.task(
    name="app.workers.tasks.brainwork_tasks.crawl_brainwork_blog",
    autoretry_for=(Exception,),
    max_retries=1,
    retry_backoff=True,
)
def crawl_brainwork_blog(max_pages: int | None = None) -> dict:
    """
    Task Celery que executa o crawler do Brainwork.

    Args:
        max_pages: Limite de paginas por execucao (None = usar config).

    Returns:
        Dict com total_urls, new_urls, ingested, failed, errors.
    """
    logger.info("crawl_brainwork_blog: iniciando (max_pages=%s)", max_pages)
    result = asyncio.run(_run_crawl(max_pages=max_pages))
    logger.info("crawl_brainwork_blog: resultado=%s", result)
    return result
