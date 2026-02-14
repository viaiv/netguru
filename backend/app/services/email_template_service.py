"""
EmailTemplateService — CRUD e renderizacao de templates de email.

Fornece acesso async (FastAPI) e sync (Celery/EmailService).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate


class EmailTemplateService:
    """CRUD e renderizacao para email_templates."""

    # ------------------------------------------------------------------
    # Async (FastAPI endpoints)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_all(db: AsyncSession) -> list[EmailTemplate]:
        """Retorna todos os templates ordenados por email_type."""
        stmt = select(EmailTemplate).order_by(EmailTemplate.email_type)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_type(db: AsyncSession, email_type: str) -> Optional[EmailTemplate]:
        """Busca template pelo tipo de email."""
        stmt = select(EmailTemplate).where(EmailTemplate.email_type == email_type)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update(
        db: AsyncSession,
        email_type: str,
        *,
        subject: Optional[str] = None,
        body_html: Optional[str] = None,
        is_active: Optional[bool] = None,
        updated_by: Optional[UUID] = None,
    ) -> Optional[EmailTemplate]:
        """Atualiza campos do template. Retorna None se nao encontrado."""
        template = await EmailTemplateService.get_by_type(db, email_type)
        if template is None:
            return None

        if subject is not None:
            template.subject = subject
        if body_html is not None:
            template.body_html = body_html
        if is_active is not None:
            template.is_active = is_active
        template.updated_by = updated_by
        template.updated_at = datetime.utcnow()

        await db.flush()
        await db.refresh(template)
        return template

    # ------------------------------------------------------------------
    # Sync (Celery / EmailService)
    # ------------------------------------------------------------------

    @staticmethod
    def get_by_type_sync(db: Session, email_type: str) -> Optional[EmailTemplate]:
        """Versao sincrona de get_by_type para uso em workers/EmailService."""
        stmt = select(EmailTemplate).where(EmailTemplate.email_type == email_type)
        return db.execute(stmt).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Renderizacao
    # ------------------------------------------------------------------

    @staticmethod
    def render(body_html: str, variables: dict[str, str]) -> str:
        """
        Substitui placeholders ``{{var}}`` no body_html.

        Variaveis nao encontradas no dict ficam inalteradas no HTML.

        Args:
            body_html: Template HTML com placeholders {{var}}.
            variables: Dicionario nome→valor para substituicao.

        Returns:
            HTML com variaveis substituidas.
        """
        def _replacer(match: re.Match) -> str:
            key = match.group(1).strip()
            return variables.get(key, match.group(0))

        return re.sub(r"\{\{(\s*\w+\s*)\}\}", _replacer, body_html)
