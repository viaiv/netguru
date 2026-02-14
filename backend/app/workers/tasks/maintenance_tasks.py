"""
Tarefas periodicas de manutencao (Celery Beat).

- cleanup_orphan_uploads: remove uploads orfaos
- cleanup_expired_tokens: remove refresh tokens sem TTL
- service_health_check: verifica saude de Redis e DB
- recalculate_stale_embeddings: re-gera embeddings com modelo desatualizado
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import redis
from sqlalchemy import select, delete

from app.core.config import settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _is_r2_path(storage_path: str) -> bool:
    """Verifica se o caminho corresponde a um objeto no R2 (relativo, prefixo uploads/)."""
    return storage_path.startswith("uploads/") and not Path(storage_path).is_absolute()


@celery_app.task(name="app.workers.tasks.maintenance_tasks.cleanup_orphan_uploads")
def cleanup_orphan_uploads() -> dict:
    """
    Remove documentos orfaos e pendentes de upload.

    1. Documentos com status 'pending_upload' ha mais de 1 hora.
    2. Documentos com status 'uploaded' ha mais de ORPHAN_UPLOAD_AGE_HOURS.

    Suporta exclusao tanto de arquivos locais quanto de objetos no R2.
    """
    from app.core.database_sync import get_sync_db
    from app.models.document import Document
    from app.services.file_storage import delete_stored_file
    from app.services.r2_storage_service import R2NotConfiguredError, R2StorageService

    removed = 0
    pending_removed = 0
    r2: R2StorageService | None = None

    with get_sync_db() as db:
        # --- 1) pending_upload docs (1 hour cutoff) ---
        pending_cutoff = datetime.now(UTC) - timedelta(hours=1)
        pending_stmt = select(Document).where(
            Document.status == "pending_upload",
            Document.created_at < pending_cutoff,
        )
        pending_docs = db.execute(pending_stmt).scalars().all()

        for doc in pending_docs:
            if doc.storage_path and _is_r2_path(doc.storage_path):
                try:
                    if r2 is None:
                        r2 = R2StorageService.from_settings_sync(db)
                    r2.delete_object(doc.storage_path)
                except R2NotConfiguredError:
                    logger.warning(
                        "R2 nao configurado, pulando exclusao do objeto: %s",
                        doc.storage_path,
                    )
                except Exception:
                    logger.warning(
                        "Falha ao deletar objeto R2 (pending): %s", doc.storage_path
                    )

            db.delete(doc)
            pending_removed += 1

        # --- 2) uploaded orphan docs (existing logic, with R2 support) ---
        cutoff = datetime.now(UTC) - timedelta(hours=settings.ORPHAN_UPLOAD_AGE_HOURS)
        stmt = select(Document).where(
            Document.status == "uploaded",
            Document.created_at < cutoff,
        )
        orphans = db.execute(stmt).scalars().all()

        for doc in orphans:
            try:
                if _is_r2_path(doc.storage_path):
                    if r2 is None:
                        r2 = R2StorageService.from_settings_sync(db)
                    r2.delete_object(doc.storage_path)
                else:
                    delete_stored_file(doc.storage_path)
            except R2NotConfiguredError:
                logger.warning(
                    "R2 nao configurado, pulando exclusao do objeto: %s",
                    doc.storage_path,
                )
            except Exception:
                logger.warning("Falha ao deletar arquivo: %s", doc.storage_path)

            db.delete(doc)
            removed += 1

    logger.info(
        "cleanup_orphan_uploads: %d orfaos removidos, %d pending removidos",
        removed,
        pending_removed,
    )
    return {"removed": removed, "pending_removed": pending_removed}


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


@celery_app.task(name="app.workers.tasks.maintenance_tasks.mark_stale_tasks_timeout")
def mark_stale_tasks_timeout() -> dict:
    """
    Marca tasks Celery com status STARTED ha mais de 5 minutos como TIMEOUT.

    Isso cobre cenarios onde o worker foi morto/reiniciado e os signals
    task_postrun/task_failure nunca dispararam.
    """
    from app.core.database_sync import get_sync_db
    from app.models.celery_task_event import CeleryTaskEvent

    cutoff = datetime.now(UTC) - timedelta(minutes=5)
    marked = 0

    with get_sync_db() as db:
        stmt = select(CeleryTaskEvent).where(
            CeleryTaskEvent.status == "STARTED",
            CeleryTaskEvent.started_at < cutoff,
        )
        stale_events = db.execute(stmt).scalars().all()

        now = datetime.now(UTC)
        for event in stale_events:
            event.status = "TIMEOUT"
            event.finished_at = now
            if event.started_at:
                event.duration_ms = round(
                    (now - event.started_at).total_seconds() * 1000, 2
                )
            event.error = "Task marcada como TIMEOUT: sem resposta do worker apos 5 minutos"
            marked += 1

    logger.info("mark_stale_tasks_timeout: %d tasks marcadas como TIMEOUT", marked)
    return {"marked": marked}
