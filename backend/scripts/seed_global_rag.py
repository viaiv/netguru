"""
Seed Global RAG — Ingere documentos de vendors no RAG Global (user_id=NULL).

Uso:
    cd backend
    python -m scripts.seed_global_rag --source-dir ./data/vendor_docs/cisco --vendor cisco
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.document import Document, Embedding
from app.services.embedding_service import EmbeddingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".conf", ".cfg"}


def chunk_text(text: str) -> list[str]:
    """Divide texto em chunks com overlap."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text)


def read_file(path: Path) -> str:
    """Le conteudo de um arquivo."""
    if path.suffix.lower() == ".pdf":
        import pymupdf

        parts: list[str] = []
        with pymupdf.open(str(path)) as doc:
            for page in doc:
                parts.append(page.get_text())
        return "\n".join(parts)
    return path.read_text(encoding="utf-8", errors="replace")


async def seed(source_dir: str, vendor: str, category: str) -> None:
    """Processa todos os arquivos do diretorio e insere no RAG Global."""
    source_path = Path(source_dir)
    if not source_path.is_dir():
        logger.error("Diretorio nao encontrado: %s", source_dir)
        sys.exit(1)

    files = [f for f in source_path.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]
    if not files:
        logger.warning("Nenhum arquivo suportado encontrado em %s", source_dir)
        return

    logger.info("Encontrados %d arquivos em %s", len(files), source_dir)
    embedding_svc = EmbeddingService.get_instance()

    async with AsyncSessionLocal() as db:
        total_chunks = 0
        for filepath in sorted(files):
            logger.info("Processando: %s", filepath.name)
            raw_text = read_file(filepath)
            chunks = chunk_text(raw_text)

            if not chunks:
                logger.warning("  Arquivo vazio ou sem texto: %s", filepath.name)
                continue

            # Cria Document global (user_id=NULL)
            doc = Document(
                id=uuid4(),
                user_id=None,
                filename=filepath.name,
                original_filename=filepath.name,
                file_type=filepath.suffix.lstrip("."),
                file_size_bytes=filepath.stat().st_size,
                storage_path=str(filepath.resolve()),
                mime_type="text/plain",
                status="completed",
                document_metadata={
                    "vendor": vendor,
                    "category": category,
                    "source": "seed_global_rag",
                },
            )
            db.add(doc)
            await db.flush()

            vectors = embedding_svc.encode_batch(chunks)

            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                emb = Embedding(
                    user_id=None,
                    document_id=doc.id,
                    chunk_text=chunk,
                    chunk_index=i,
                    embedding=vector,
                    embedding_model=settings.EMBEDDING_MODEL,
                    embedding_dimension=settings.VECTOR_DIMENSION,
                    embedding_metadata={
                        "vendor": vendor,
                        "category": category,
                        "source_filename": filepath.name,
                    },
                )
                db.add(emb)

            total_chunks += len(chunks)
            logger.info("  -> %d chunks gerados", len(chunks))

        await db.commit()
        logger.info("Seed completo: %d arquivos, %d chunks totais", len(files), total_chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Global RAG com documentos de vendors")
    parser.add_argument("--source-dir", required=True, help="Diretorio com arquivos para ingestao")
    parser.add_argument("--vendor", required=True, help="Nome do vendor (cisco, juniper, arista)")
    parser.add_argument("--category", default="configuration", help="Categoria (configuration, troubleshooting)")
    args = parser.parse_args()

    asyncio.run(seed(args.source_dir, args.vendor, args.category))


if __name__ == "__main__":
    main()
