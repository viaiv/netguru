"""
BrainworkCrawlerService — crawlea sitemap do brainwork.com.br e ingere posts no RAG Global.
"""
from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.services.url_ingestion_service import UrlIngestionError, UrlIngestionService

logger = logging.getLogger(__name__)


@dataclass
class SitemapEntry:
    """Entrada parseada do sitemap XML."""

    url: str
    lastmod: str | None = None


@dataclass
class CrawlResult:
    """Resultado agregado de uma execucao do crawler."""

    total_urls: int = 0
    new_urls: int = 0
    ingested: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class BrainworkCrawlerService:
    """Crawlea sitemap do brainwork.com.br e ingere posts no RAG Global."""

    SITEMAP_URL = "https://brainwork.com.br/sitemap-1.xml"
    # Padrao de URL de posts: /YYYY/MM/DD/slug/
    POST_URL_PATTERN = re.compile(r"brainwork\.com\.br/\d{4}/\d{2}/\d{2}/[\w-]+")

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def crawl(self, max_pages: int | None = None) -> CrawlResult:
        """
        Fluxo principal do crawler.

        Args:
            max_pages: Limite de paginas a ingerir (None = sem limite).

        Returns:
            CrawlResult com totais e erros.
        """
        result = CrawlResult()

        # 1. Fetch sitemap
        try:
            entries = await self._fetch_sitemap()
        except Exception as exc:
            logger.exception("Erro ao buscar sitemap do Brainwork")
            result.errors.append(f"Falha ao buscar sitemap: {exc}")
            return result

        result.total_urls = len(entries)

        if not entries:
            logger.info("brainwork_crawl: nenhuma URL encontrada no sitemap")
            return result

        # 2. Filtrar URLs ja ingeridas
        existing = await self._get_existing_urls()
        new_entries = [e for e in entries if e.url not in existing]
        result.new_urls = len(new_entries)

        if not new_entries:
            logger.info("brainwork_crawl: nenhuma URL nova (todas ja ingeridas)")
            return result

        # 3. Aplicar limite
        effective_max = max_pages or settings.BRAINWORK_CRAWL_MAX_PAGES
        if effective_max > 0:
            new_entries = new_entries[:effective_max]

        # 4. Ingerir cada URL
        delay = settings.BRAINWORK_CRAWL_DELAY_SECONDS
        for entry in new_entries:
            doc = await self._ingest_post(entry.url)
            if doc is not None:
                result.ingested += 1
            else:
                result.failed += 1

            if delay > 0:
                await asyncio.sleep(delay)

        logger.info(
            "brainwork_crawl: total=%d novas=%d ingeridas=%d falhas=%d",
            result.total_urls,
            result.new_urls,
            result.ingested,
            result.failed,
        )
        return result

    async def _fetch_sitemap(self) -> list[SitemapEntry]:
        """Parse sitemap XML e retorna lista de URLs de posts."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(self.SITEMAP_URL)
            response.raise_for_status()

        root = ET.fromstring(response.content)

        # Namespace padrao de sitemaps
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        entries: list[SitemapEntry] = []
        for url_elem in root.findall("sm:url", ns):
            loc = url_elem.findtext("sm:loc", namespaces=ns)
            if not loc:
                continue

            # Filtrar apenas URLs de posts (YYYY/MM/DD/slug)
            if not self.POST_URL_PATTERN.search(loc):
                continue

            lastmod = url_elem.findtext("sm:lastmod", namespaces=ns)
            entries.append(SitemapEntry(url=loc, lastmod=lastmod))

        logger.info("brainwork_sitemap: %d URLs de posts encontradas", len(entries))
        return entries

    async def _get_existing_urls(self) -> set[str]:
        """Retorna conjunto de URLs do Brainwork ja ingeridas no banco."""
        stmt = (
            select(Document.document_metadata["source_url"].as_string())
            .where(
                Document.document_metadata["source_url"]
                .as_string()
                .like("%brainwork.com.br%")
            )
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return {url for url in rows if url}

    async def _ingest_post(self, url: str) -> Document | None:
        """
        Ingere um post usando UrlIngestionService.

        Args:
            url: URL do post no Brainwork.

        Returns:
            Document criado ou None se falhou.
        """
        try:
            service = UrlIngestionService(self._db)
            document = await service.ingest(url=url)

            # Enriquecer metadata
            meta = document.document_metadata or {}
            meta["source"] = "brainwork"
            meta["category"] = "community"
            meta["ingestion_method"] = "crawler"
            document.document_metadata = meta

            await self._db.commit()

            # Disparar processamento (chunking + embedding)
            from app.workers.tasks.document_tasks import process_document

            process_document.delay(str(document.id))

            logger.debug("brainwork_ingest: %s -> doc=%s", url, document.id)
            return document

        except UrlIngestionError as exc:
            logger.warning("brainwork_ingest_fail: %s — %s", url, exc)
            return None
        except Exception as exc:
            logger.warning("brainwork_ingest_error: %s — %s", url, exc)
            return None
