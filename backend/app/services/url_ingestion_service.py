"""
UrlIngestionService — download + extracao de texto de URLs para RAG Global.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document

logger = logging.getLogger(__name__)

# Limite de download (10 MB)
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024

# Hostnames bloqueados para prevencao de SSRF
_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
})


def _is_private_ip(ip_str: str) -> bool:
    """Verifica se IP e privado, reservado, loopback, link-local ou multicast."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # Nao parsavel → bloquear por seguranca
    return (
        addr.is_private
        or addr.is_reserved
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
    )


def _validate_url_target(url: str) -> None:
    """
    Resolve DNS e bloqueia destinos internos/privados.

    Raises:
        UrlIngestionError: Se URL aponta para host bloqueado.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise UrlIngestionError("URL sem hostname valido.")

    # Checar hostnames bloqueados diretamente
    lower = hostname.lower()
    if lower in _BLOCKED_HOSTNAMES or lower.endswith(".local"):
        raise UrlIngestionError(
            f"URL bloqueada: destino interno ({hostname})."
        )

    # Resolver DNS e checar IPs
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlIngestionError(f"Nao foi possivel resolver DNS: {hostname}") from exc

    for info in addr_infos:
        ip_str = info[4][0]
        if _is_private_ip(ip_str):
            raise UrlIngestionError(
                f"URL bloqueada: {hostname} resolve para IP privado/reservado ({ip_str})."
            )

MIME_MAP = {
    "txt": "text/plain",
    "pdf": "application/pdf",
    "md": "text/markdown",
    "conf": "text/plain",
    "cfg": "text/plain",
    "log": "text/plain",
}


class UrlIngestionError(Exception):
    """Erro durante ingestao de URL."""


async def _store_file(
    db: AsyncSession,
    object_key: str,
    file_bytes: bytes,
    content_type: str,
) -> str:
    """
    Armazena bytes no R2 (preferencial) ou disco local (fallback).

    Returns:
        storage_path: chave R2 relativa ou path absoluto local.
    """
    from app.services.r2_storage_service import R2NotConfiguredError, R2StorageService

    try:
        r2 = await R2StorageService.from_settings(db)
        r2.upload_object(object_key, file_bytes, content_type)
        logger.info("Arquivo armazenado no R2: %s", object_key)
        return object_key  # ex: "uploads/global/uuid.txt"
    except R2NotConfiguredError:
        logger.info("R2 nao configurado, salvando localmente")

    # Fallback: disco local
    local_path = Path(settings.UPLOAD_DIR) / object_key.replace("uploads/", "", 1)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(file_bytes)
    return str(local_path)


class UrlIngestionService:
    """
    Faz download de URL, extrai texto e cria Document global (user_id=None).
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def ingest(self, url: str, title: str | None = None) -> Document:
        """
        Faz download da URL e cria Document para processamento.

        Args:
            url: URL publica para download.
            title: Titulo opcional (usado como original_filename).

        Returns:
            Document criado com status 'uploaded'.

        Raises:
            UrlIngestionError: Em caso de falha no download ou tipo nao suportado.
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise UrlIngestionError(f"Esquema de URL nao suportado: {parsed.scheme}")

        # Validacao SSRF: bloquear destinos internos/privados
        _validate_url_target(url)

        content_bytes, content_type = await self._download(url)

        # Determinar tipo e extensao
        file_type, ext = self._resolve_type(content_type, parsed.path)

        # Extrair texto para HTML, salvar bytes direto para PDF/texto
        if file_type == "html":
            text = self._extract_html_text(content_bytes)
            if not text.strip():
                raise UrlIngestionError("Pagina HTML nao contem texto extraivel")
            file_bytes = text.encode("utf-8")
            ext = "txt"
            file_type = "txt"
        else:
            file_bytes = content_bytes

        # Definir nome do arquivo
        if title:
            safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)
            original_filename = f"{safe_title}.{ext}"
        else:
            path_name = Path(parsed.path).stem or "documento"
            original_filename = f"{path_name}.{ext}"

        # Armazenar (R2 ou local)
        doc_uuid = uuid4()
        stored_filename = f"{doc_uuid}.{ext}"
        object_key = f"uploads/global/{stored_filename}"
        mime = MIME_MAP.get(ext, content_type)

        storage_path = await _store_file(self._db, object_key, file_bytes, mime)

        # Criar Document
        document = Document(
            id=doc_uuid,
            user_id=None,
            filename=stored_filename,
            original_filename=original_filename,
            file_type=file_type,
            file_size_bytes=len(file_bytes),
            storage_path=storage_path,
            mime_type=mime,
            status="uploaded",
            document_metadata={"source_url": url, "ingestion_method": "url"},
        )
        self._db.add(document)

        return document

    async def _download(self, url: str) -> tuple[bytes, str]:
        """
        Download da URL com limites de tamanho e timeout.
        Segue redirects manualmente para revalidar destinos SSRF.

        Returns:
            Tupla (bytes do conteudo, content-type).
        """
        max_redirects = 5
        current_url = url

        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(30.0),
            ) as client:
                for _ in range(max_redirects + 1):
                    response = await client.get(current_url)
                    if response.is_redirect:
                        redirect_url = str(response.next_request.url) if response.next_request else None
                        if not redirect_url:
                            raise UrlIngestionError("Redirect sem destino.")
                        _validate_url_target(redirect_url)
                        current_url = redirect_url
                        continue
                    response.raise_for_status()
                    break
                else:
                    raise UrlIngestionError(f"Limite de redirects excedido ({max_redirects}).")
        except UrlIngestionError:
            raise
        except httpx.TimeoutException as exc:
            raise UrlIngestionError(f"Timeout ao acessar URL: {url}") from exc
        except httpx.HTTPStatusError as exc:
            raise UrlIngestionError(
                f"HTTP {exc.response.status_code} ao acessar URL: {url}"
            ) from exc
        except httpx.RequestError as exc:
            raise UrlIngestionError(f"Erro de conexao: {exc}") from exc

        if len(response.content) > MAX_DOWNLOAD_BYTES:
            raise UrlIngestionError(
                f"Conteudo excede limite de {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB"
            )

        raw_ct = response.headers.get("content-type", "text/html")
        content_type = raw_ct.split(";")[0].strip().lower()

        return response.content, content_type

    def _resolve_type(self, content_type: str, url_path: str) -> tuple[str, str]:
        """
        Resolve file_type e extensao a partir do content-type e path da URL.

        Returns:
            Tupla (file_type, extensao).
        """
        if "pdf" in content_type or url_path.lower().endswith(".pdf"):
            return "pdf", "pdf"
        if "text/plain" in content_type:
            return "txt", "txt"
        if "markdown" in content_type or url_path.lower().endswith(".md"):
            return "md", "md"
        # Default: tratar como HTML
        return "html", "html"

    def _extract_html_text(self, html_bytes: bytes) -> str:
        """
        Extrai texto limpo de HTML removendo scripts, estilos e navegacao.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_bytes, "lxml")

        # Remover elementos nao-texto
        for tag_name in ("script", "style", "nav", "footer", "header", "aside"):
            for tag in soup.find_all(tag_name):
                tag.decompose()

        text = soup.get_text(separator="\n")

        # Limpar linhas em branco excessivas
        lines = [line.strip() for line in text.splitlines()]
        cleaned = "\n".join(line for line in lines if line)

        return cleaned
