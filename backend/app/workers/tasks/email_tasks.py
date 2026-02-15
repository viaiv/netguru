"""
Celery tasks para envio de emails transacionais via Mailtrap.

Cada task registra o resultado (sent/failed/skipped) na tabela email_logs.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.email_tasks.send_verification_email",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_verification_email(to_email: str, token: str, user_id: Optional[str] = None) -> dict:
    """Envia email de verificacao de conta."""
    from uuid import UUID
    from app.core.database_sync import get_sync_db
    from app.services.email_service import EmailService

    uid = UUID(user_id) if user_id else None

    with get_sync_db() as db:
        svc = EmailService(db)
        if not svc.is_configured():
            logger.info("Email nao configurado, pulando verificacao para %s", to_email)
            svc.log_skipped(to_email, "verification", recipient_user_id=uid)
            return {"status": "skipped", "reason": "email_not_configured"}
        svc.send_verification_email(to_email, token, user_id=uid)
        return {"status": "sent", "to": to_email}


@celery_app.task(
    name="app.workers.tasks.email_tasks.send_password_reset_email",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_password_reset_email(to_email: str, token: str, user_id: Optional[str] = None) -> dict:
    """Envia email de redefinicao de senha."""
    from uuid import UUID
    from app.core.database_sync import get_sync_db
    from app.services.email_service import EmailService

    uid = UUID(user_id) if user_id else None

    with get_sync_db() as db:
        svc = EmailService(db)
        if not svc.is_configured():
            logger.info("Email nao configurado, pulando reset para %s", to_email)
            svc.log_skipped(to_email, "password_reset", recipient_user_id=uid)
            return {"status": "skipped", "reason": "email_not_configured"}
        svc.send_password_reset_email(to_email, token, user_id=uid)
        return {"status": "sent", "to": to_email}


@celery_app.task(
    name="app.workers.tasks.email_tasks.send_welcome_email",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_welcome_email(
    to_email: str,
    full_name: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    """Envia email de boas-vindas apos verificacao."""
    from uuid import UUID
    from app.core.database_sync import get_sync_db
    from app.services.email_service import EmailService

    uid = UUID(user_id) if user_id else None

    with get_sync_db() as db:
        svc = EmailService(db)
        if not svc.is_configured():
            logger.info("Email nao configurado, pulando welcome para %s", to_email)
            svc.log_skipped(to_email, "welcome", recipient_user_id=uid)
            return {"status": "skipped", "reason": "email_not_configured"}
        svc.send_welcome_email(to_email, full_name, user_id=uid)
        return {"status": "sent", "to": to_email}


@celery_app.task(
    name="app.workers.tasks.email_tasks.send_byollm_discount_warning_email",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
def send_byollm_discount_warning_email(
    to_email: str,
    full_name: Optional[str] = None,
    grace_days: int = 7,
    user_id: Optional[str] = None,
) -> dict:
    """Envia aviso de revogacao do desconto BYO-LLM."""
    from uuid import UUID
    from app.core.database_sync import get_sync_db
    from app.services.email_service import EmailService

    uid = UUID(user_id) if user_id else None

    with get_sync_db() as db:
        svc = EmailService(db)
        if not svc.is_configured():
            logger.info("Email nao configurado, pulando byollm warning para %s", to_email)
            svc.log_skipped(to_email, "byollm_discount_warning", recipient_user_id=uid)
            return {"status": "skipped", "reason": "email_not_configured"}
        svc.send_byollm_discount_warning(to_email, full_name, grace_days, user_id=uid)
        return {"status": "sent", "to": to_email}
