"""
Celery task para processamento de documentos (chunking + embedding).
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Extensoes que podem ser lidas como texto puro
TEXT_EXTENSIONS = {"txt", "conf", "cfg", "log", "md"}


def _is_r2_path(storage_path: str) -> bool:
    """Verifica se o caminho aponta para objeto no R2 (Cloudflare).

    Args:
        storage_path: Caminho de armazenamento do documento.

    Returns:
        True se for caminho relativo com prefixo 'uploads/' (padrao R2).
    """
    return storage_path.startswith("uploads/") and not Path(storage_path).is_absolute()


@celery_app.task(
    name="app.workers.tasks.document_tasks.process_document",
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
)
def process_document(document_id: str) -> dict:
    """
    Processa documento: le arquivo, chunka, gera embeddings e persiste.

    Args:
        document_id: UUID do documento (string).

    Returns:
        Dict com status e quantidade de chunks.
    """
    from uuid import UUID

    from app.core.database_sync import get_sync_db
    from app.models.document import Document, Embedding
    from app.services.embedding_service import EmbeddingService

    doc_uuid = UUID(document_id)

    with get_sync_db() as db:
        stmt = select(Document).where(Document.id == doc_uuid)
        document = db.execute(stmt).scalar_one_or_none()

        if document is None:
            logger.warning("Documento %s nao encontrado", document_id)
            return {"status": "not_found", "chunks": 0}

        if document.status != "uploaded":
            logger.info(
                "Documento %s com status '%s', pulando",
                document_id,
                document.status,
            )
            return {"status": "skipped", "chunks": 0}

        document.status = "processing"
        db.flush()

        try:
            raw_text = _read_file(document.storage_path, document.file_type, db=db)
            chunks = _chunk_text(raw_text)

            if not chunks:
                document.status = "completed"
                document.processed_at = datetime.utcnow()
                return {"status": "completed", "chunks": 0}

            embedding_svc = EmbeddingService.get_instance()
            vectors = embedding_svc.encode_batch(chunks)

            for i, (chunk_text, vector) in enumerate(zip(chunks, vectors)):
                embedding = Embedding(
                    user_id=document.user_id,
                    document_id=document.id,
                    chunk_text=chunk_text,
                    chunk_index=i,
                    embedding=vector,
                    embedding_model=settings.EMBEDDING_MODEL,
                    embedding_dimension=settings.VECTOR_DIMENSION,
                    embedding_metadata={
                        "source_filename": document.original_filename,
                        "file_type": document.file_type,
                    },
                )
                db.add(embedding)

            document.status = "completed"
            document.processed_at = datetime.utcnow()

            logger.info(
                "Documento processado: %s (%d chunks)",
                document.original_filename,
                len(chunks),
            )
            return {"status": "completed", "chunks": len(chunks)}

        except Exception:
            document.status = "failed"
            db.commit()
            logger.exception("Erro ao processar documento %s", document_id)
            raise


def _read_file(storage_path: str, file_type: str, db: Session | None = None) -> str:
    """Le conteudo do arquivo como texto (disco local ou R2).

    Args:
        storage_path: Caminho do arquivo (local absoluto ou chave R2 relativa).
        file_type: Tipo do arquivo (ex: 'pdf', 'txt', 'conf').
        db: Sessao sync do banco, obrigatoria para arquivos no R2.

    Returns:
        Conteudo textual do arquivo.

    Raises:
        RuntimeError: Se arquivo estiver no R2 e db nao for fornecido.
    """
    if _is_r2_path(storage_path):
        from app.services.r2_storage_service import R2StorageService

        if db is None:
            raise RuntimeError("db session required for R2 storage")

        r2 = R2StorageService.from_settings_sync(db)

        suffix = f".{file_type}" if file_type else Path(storage_path).suffix
        if suffix and not suffix.startswith("."):
            suffix = f".{suffix}"

        tmp_path = r2.download_to_tempfile(storage_path, suffix)
        try:
            if file_type == "pdf" or tmp_path.suffix.lower() == ".pdf":
                return _read_pdf(tmp_path)
            return tmp_path.read_text(encoding="utf-8", errors="replace")
        finally:
            tmp_path.unlink(missing_ok=True)

    # Arquivo local — logica original
    path = Path(storage_path)

    if file_type == "pdf" or path.suffix.lower() == ".pdf":
        return _read_pdf(path)

    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    """Extrai texto de PDF via pymupdf."""
    import pymupdf

    text_parts: list[str] = []
    with pymupdf.open(str(path)) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts)


def _chunk_text(text: str) -> list[str]:
    """Divide texto em chunks com overlap."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text)
