"""
Celery signal handlers — persist task execution events to celery_task_events.

Imported by celery_app.py to register handlers on worker startup.
Every handler is wrapped in try/except to never interfere with the task itself.
"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime
from uuid import uuid4

from celery.signals import task_failure, task_postrun, task_prerun

logger = logging.getLogger(__name__)


def _sanitize(value: object, max_len: int = 500) -> str | None:
    """Converte valor para string truncada, removendo dados sensiveis obvios."""
    if value is None:
        return None
    text = str(value)
    # Mascarar tokens/keys que possam aparecer nos args
    for keyword in ("token", "key", "password", "secret"):
        if keyword in text.lower():
            text = "<redacted>"
            break
    return text[:max_len] if len(text) > max_len else text


@task_prerun.connect
def on_task_prerun(sender: object = None, task_id: str = "", task: object = None, args: tuple = (), kwargs: dict | None = None, **kw: object) -> None:
    """INSERT novo registro com status=STARTED."""
    try:
        from app.core.database_sync import get_sync_db
        from app.models.celery_task_event import CeleryTaskEvent

        worker_hostname = None
        if hasattr(task, "request") and hasattr(task.request, "hostname"):
            worker_hostname = str(task.request.hostname) if task.request.hostname else None

        args_summary = _sanitize((args, kwargs or {}))

        event = CeleryTaskEvent(
            id=uuid4(),
            task_id=task_id,
            task_name=sender.name if hasattr(sender, "name") else str(sender),
            status="STARTED",
            args_summary=args_summary,
            started_at=datetime.utcnow(),
            worker=worker_hostname,
        )

        with get_sync_db() as db:
            db.add(event)

    except Exception:
        logger.warning("Falha ao gravar task_prerun para %s: %s", task_id, traceback.format_exc())


@task_postrun.connect
def on_task_postrun(sender: object = None, task_id: str = "", task: object = None, retval: object = None, state: str = "", **kw: object) -> None:
    """UPDATE registro existente com resultado e duracao."""
    try:
        from app.core.database_sync import get_sync_db
        from app.models.celery_task_event import CeleryTaskEvent

        now = datetime.utcnow()

        with get_sync_db() as db:
            event = (
                db.query(CeleryTaskEvent)
                .filter(CeleryTaskEvent.task_id == task_id)
                .first()
            )
            if event is None:
                logger.debug("Nenhum evento prerun encontrado para task_id=%s, criando novo", task_id)
                event = CeleryTaskEvent(
                    id=uuid4(),
                    task_id=task_id,
                    task_name=sender.name if hasattr(sender, "name") else str(sender),
                    status=state or "SUCCESS",
                    started_at=now,
                    finished_at=now,
                    duration_ms=0,
                    result_summary=_sanitize(retval),
                )
                db.add(event)
                return

            event.status = state or "SUCCESS"
            event.finished_at = now
            if event.started_at:
                delta = (now - event.started_at).total_seconds() * 1000
                event.duration_ms = round(delta, 2)
            event.result_summary = _sanitize(retval)

    except Exception:
        logger.warning("Falha ao gravar task_postrun para %s: %s", task_id, traceback.format_exc())


@task_failure.connect
def on_task_failure(sender: object = None, task_id: str = "", exception: BaseException | None = None, traceback: object = None, **kw: object) -> None:
    """UPDATE registro existente com FAILURE e traceback."""
    try:
        from app.core.database_sync import get_sync_db
        from app.models.celery_task_event import CeleryTaskEvent
        import traceback as tb_module

        now = datetime.utcnow()
        error_text = ""
        if exception:
            error_text = "".join(tb_module.format_exception(type(exception), exception, exception.__traceback__))
        error_text = error_text[:2000] if len(error_text) > 2000 else error_text

        with get_sync_db() as db:
            event = (
                db.query(CeleryTaskEvent)
                .filter(CeleryTaskEvent.task_id == task_id)
                .first()
            )
            if event is None:
                event = CeleryTaskEvent(
                    id=uuid4(),
                    task_id=task_id,
                    task_name=sender.name if hasattr(sender, "name") else str(sender),
                    status="FAILURE",
                    started_at=now,
                    finished_at=now,
                    duration_ms=0,
                    error=error_text,
                )
                db.add(event)
                return

            event.status = "FAILURE"
            event.finished_at = now
            if event.started_at:
                delta = (now - event.started_at).total_seconds() * 1000
                event.duration_ms = round(delta, 2)
            event.error = error_text

    except Exception:
        logger.warning("Falha ao gravar task_failure para %s", task_id)
