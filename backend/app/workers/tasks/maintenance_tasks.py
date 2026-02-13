"""
Tarefas periodicas de manutencao (Celery Beat).

- cleanup_orphan_uploads: remove uploads orfaos
- cleanup_expired_tokens: remove refresh tokens sem TTL
- service_health_check: verifica saude de Redis e DB
- recalculate_stale_embeddings: re-gera embeddings com modelo desatualizado
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import redis
from sqlalchemy import select, delete

from app.core.config import settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.maintenance_tasks.cleanup_orphan_uploads")
def cleanup_orphan_uploads() -> dict:
    """
    Remove documentos com status 'uploaded' ha mais de ORPHAN_UPLOAD_AGE_HOURS.

    Deleta o arquivo do disco e o registro do banco.
    """
    from app.core.database_sync import get_sync_db
    from app.models.document import Document
    from app.services.file_storage import delete_stored_file

    cutoff = datetime.utcnow() - timedelta(hours=settings.ORPHAN_UPLOAD_AGE_HOURS)
    removed = 0

    with get_sync_db() as db:
        stmt = select(Document).where(
            Document.status == "uploaded",
            Document.created_at < cutoff,
        )
        orphans = db.execute(stmt).scalars().all()

        for doc in orphans:
            try:
                delete_stored_file(doc.storage_path)
            except Exception:
                logger.warning("Falha ao deletar arquivo: %s", doc.storage_path)

            db.delete(doc)
            removed += 1

    logger.info("cleanup_orphan_uploads: %d documentos removidos", removed)
    return {"removed": removed}


@celery_app.task(name="app.workers.tasks.maintenance_tasks.cleanup_expired_tokens")
def cleanup_expired_tokens() -> dict:
    """
    Remove chaves refresh_token:* no Redis que nao possuem TTL.

    Tokens validos sempre tem TTL configurado; chaves sem TTL sao orfas.
    """
    r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    removed = 0

    cursor = "0"
    while True:
        cursor, keys = r.scan(cursor=cursor, match="refresh_token:*", count=100)
        for key in keys:
            ttl = r.ttl(key)
            if ttl == -1:  # sem TTL
                r.delete(key)
                removed += 1
        if cursor == 0 or cursor == "0":
            break

    logger.info("cleanup_expired_tokens: %d tokens removidos", removed)
    return {"removed": removed}


@celery_app.task(name="app.workers.tasks.maintenance_tasks.service_health_check")
def service_health_check() -> dict:
    """
    Verifica saude do Redis e do banco de dados.

    Loga warnings em caso de falha.
    """
    status: dict[str, str] = {}

    # Redis
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.ping()
        status["redis"] = "ok"
    except Exception as e:
        logger.warning("Health check Redis falhou: %s", e)
        status["redis"] = f"error: {e}"

    # Database
    try:
        from app.core.database_sync import get_sync_db
        from sqlalchemy import text

        with get_sync_db() as db:
            db.execute(text("SELECT 1"))
        status["database"] = "ok"
    except Exception as e:
        logger.warning("Health check DB falhou: %s", e)
        status["database"] = f"error: {e}"

    logger.info("service_health_check: %s", status)
    return status


@celery_app.task(name="app.workers.tasks.maintenance_tasks.recalculate_stale_embeddings")
def recalculate_stale_embeddings() -> dict:
    """
    Re-gera embeddings cujo embedding_model difere do modelo atual.

    Processa em batches de 100 para evitar uso excessivo de memoria.
    """
    from app.core.database_sync import get_sync_db
    from app.models.document import Embedding
    from app.services.embedding_service import EmbeddingService

    batch_size = 100
    total_updated = 0
    embedding_svc = EmbeddingService.get_instance()

    with get_sync_db() as db:
        while True:
            stmt = (
                select(Embedding)
                .where(Embedding.embedding_model != settings.EMBEDDING_MODEL)
                .limit(batch_size)
            )
            stale = db.execute(stmt).scalars().all()

            if not stale:
                break

            texts = [e.chunk_text for e in stale]
            vectors = embedding_svc.encode_batch(texts)

            for emb, vec in zip(stale, vectors):
                emb.embedding = vec
                emb.embedding_model = settings.EMBEDDING_MODEL
                emb.embedding_dimension = settings.VECTOR_DIMENSION

            db.flush()
            total_updated += len(stale)

    logger.info("recalculate_stale_embeddings: %d embeddings atualizados", total_updated)
    return {"updated": total_updated}
