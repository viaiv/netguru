"""
Admin settings endpoints — manage system-wide configuration and email logs.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permissions
from app.core.rbac import Permission
from app.models.email_log import EmailLog
from app.models.user import User
from app.schemas.admin import (
    EmailLogListResponse,
    EmailLogResponse,
    PaginationMeta,
    SystemSettingResponse,
    SystemSettingUpdate,
)
from app.services.system_settings_service import SystemSettingsService

router = APIRouter()

# Mask encrypted values in list responses
_MASK = "********"


def _to_response(row) -> SystemSettingResponse:
    """Convert a SystemSetting row to a safe response (mask encrypted)."""
    return SystemSettingResponse(
        id=row.id,
        key=row.key,
        value=_MASK if row.is_encrypted else row.value,
        is_encrypted=row.is_encrypted,
        description=row.description,
        updated_at=row.updated_at,
    )


@router.get("/settings", response_model=list[SystemSettingResponse])
async def list_settings(
    current_user: User = Depends(require_permissions(Permission.ADMIN_SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[SystemSettingResponse]:
    """Lista todas as configuracoes do sistema (valores criptografados mascarados)."""
    rows = await SystemSettingsService.get_all(db)
    return [_to_response(r) for r in rows]


@router.put("/settings/{key}", response_model=SystemSettingResponse)
async def upsert_setting(
    key: str,
    body: SystemSettingUpdate,
    current_user: User = Depends(require_permissions(Permission.ADMIN_SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SystemSettingResponse:
    """Cria ou atualiza uma configuracao do sistema."""
    row = await SystemSettingsService.upsert(
        db,
        key=key,
        value=body.value,
        description=body.description,
        updated_by=current_user.id,
    )
    return _to_response(row)


@router.post("/settings/test-email", status_code=status.HTTP_200_OK)
async def test_email(
    current_user: User = Depends(require_permissions(Permission.ADMIN_SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Envia email de teste para o admin logado para validar configuracao Mailtrap."""
    enabled = await SystemSettingsService.get(db, "email_enabled")
    if enabled != "true":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Servico de email nao esta habilitado",
        )

    api_key = await SystemSettingsService.get(db, "mailtrap_api_key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key do Mailtrap nao configurada",
        )

    # Usa sync DB dentro de thread para reutilizar EmailService (que registra log)
    import asyncio
    from app.core.database_sync import get_sync_db
    from app.services.email_service import EmailService

    def _do_send() -> None:
        with get_sync_db() as sync_db:
            svc = EmailService(sync_db)
            svc._load_config()
            svc.send_test_email(current_user.email, user_id=current_user.id)

    await asyncio.to_thread(_do_send)

    return {"message": f"Email de teste enviado para {current_user.email}"}


# ---------------------------------------------------------------------------
# Email logs
# ---------------------------------------------------------------------------

@router.get("/email-logs", response_model=EmailLogListResponse)
async def list_email_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    email_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    current_user: User = Depends(require_permissions(Permission.ADMIN_SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> EmailLogListResponse:
    """Lista logs de envio de email com paginacao e filtros."""
    base = select(EmailLog)

    if email_type:
        base = base.where(EmailLog.email_type == email_type)
    if status_filter:
        base = base.where(EmailLog.status == status_filter)
    if search:
        base = base.where(EmailLog.recipient_email.ilike(f"%{search}%"))

    # Total count
    count_stmt = select(func.count()).select_from(base.subquery())
    total = int((await db.execute(count_stmt)).scalar_one())

    # Paginated results
    offset = (page - 1) * limit
    rows_stmt = base.order_by(desc(EmailLog.created_at)).offset(offset).limit(limit)
    rows = (await db.execute(rows_stmt)).scalars().all()

    pages = max(1, (total + limit - 1) // limit)

    return EmailLogListResponse(
        items=[EmailLogResponse.model_validate(r) for r in rows],
        pagination=PaginationMeta(total=total, page=page, pages=pages, limit=limit),
    )
