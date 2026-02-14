"""
DocumentProcessor — Chunking + embedding de documentos uploadados.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document, Embedding
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

# Extensoes que podem ser lidas como texto puro
TEXT_EXTENSIONS = {"txt", "conf", "cfg", "log", "md"}


class DocumentProcessor:
    """
    Processa documentos: le arquivo → chunka → gera embeddings → persiste.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._embedding = EmbeddingService.get_instance()

    async def process_document(self, document: Document) -> int:
        """
        Processa um documento completo.

        Args:
            document: Modelo Document com storage_path valido.

        Returns:
            Quantidade de chunks gerados.
        """
        document.status = "processing"
        await self._db.flush()

        try:
            raw_text = self._read_file(document.storage_path, document.file_type)
            chunks = self._chunk_text(raw_text)

            if not chunks:
                document.status = "completed"
                document.processed_at = datetime.now(UTC)
                await self._db.commit()
                return 0

            vectors = self._embedding.encode_batch(chunks)

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
                self._db.add(embedding)

            document.status = "completed"
            document.processed_at = datetime.now(UTC)
            await self._db.commit()

            logger.info(
                "Documento processado: %s (%d chunks)",
                document.original_filename,
                len(chunks),
            )
            return len(chunks)

        except Exception:
            document.status = "failed"
            await self._db.commit()
            logger.exception("Erro ao processar documento %s", document.id)
            raise

    def _read_file(self, storage_path: str, file_type: str) -> str:
        """Le conteudo do arquivo como texto."""
        path = Path(storage_path)

        if file_type == "pdf" or path.suffix.lower() == ".pdf":
            return self._read_pdf(path)

        # Texto puro para demais formatos
        return path.read_text(encoding="utf-8", errors="replace")

    def _read_pdf(self, path: Path) -> str:
        """Extrai texto de PDF via pymupdf."""
        import pymupdf

        text_parts: list[str] = []
        with pymupdf.open(str(path)) as doc:
            for page in doc:
                text_parts.append(page.get_text())
        return "\n".join(text_parts)

    def _chunk_text(self, text: str) -> list[str]:
        """Divide texto em chunks com overlap."""
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        return splitter.split_text(text)
