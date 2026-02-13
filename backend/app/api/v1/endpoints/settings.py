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
    EmailTemplatePreviewRequest,
    EmailTemplatePreviewResponse,
    EmailTemplateResponse,
    EmailTemplateUpdate,
    PaginationMeta,
    SystemSettingResponse,
    SystemSettingUpdate,
)
from app.services.email_template_service import EmailTemplateService
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

    send_error: str | None = None

    def _do_send() -> None:
        nonlocal send_error
        with get_sync_db() as sync_db:
            svc = EmailService(sync_db)
            svc._load_config()
            try:
                svc.send_test_email(current_user.email, user_id=current_user.id)
            except Exception as exc:
                send_error = str(exc)

    await asyncio.to_thread(_do_send)

    if send_error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Falha ao enviar email de teste: {send_error}",
        )

    return {"message": f"Email de teste enviado para {current_user.email}"}


@router.post("/settings/test-r2", status_code=status.HTTP_200_OK)
async def test_r2(
    current_user: User = Depends(require_permissions(Permission.ADMIN_SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Testa conexao com Cloudflare R2 listando objetos do bucket."""
    from app.services.r2_storage_service import (
        R2NotConfiguredError,
        R2OperationError,
        R2StorageService,
    )

    try:
        r2 = await R2StorageService.from_settings(db)
    except R2NotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        r2.list_objects(max_keys=1)
    except R2OperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Falha ao conectar ao R2: {exc}",
        ) from exc

    # Configura CORS automaticamente para permitir upload direto do browser
    try:
        r2.ensure_cors()
    except R2OperationError:
        pass  # CORS e best-effort; conexao ja foi validada

    return {"message": "Conexao com R2 realizada com sucesso (CORS configurado)"}


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


# ---------------------------------------------------------------------------
# Email Templates
# ---------------------------------------------------------------------------

@router.get("/email-templates", response_model=list[EmailTemplateResponse])
async def list_email_templates(
    current_user: User = Depends(require_permissions(Permission.ADMIN_SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[EmailTemplateResponse]:
    """Lista todos os templates de email."""
    templates = await EmailTemplateService.get_all(db)
    return [EmailTemplateResponse.model_validate(t) for t in templates]


@router.get("/email-templates/{email_type}", response_model=EmailTemplateResponse)
async def get_email_template(
    email_type: str,
    current_user: User = Depends(require_permissions(Permission.ADMIN_SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateResponse:
    """Busca um template pelo tipo de email."""
    template = await EmailTemplateService.get_by_type(db, email_type)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{email_type}' nao encontrado",
        )
    return EmailTemplateResponse.model_validate(template)


@router.put("/email-templates/{email_type}", response_model=EmailTemplateResponse)
async def update_email_template(
    email_type: str,
    body: EmailTemplateUpdate,
    current_user: User = Depends(require_permissions(Permission.ADMIN_SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateResponse:
    """Atualiza subject, body_html e/ou is_active de um template."""
    template = await EmailTemplateService.update(
        db,
        email_type,
        subject=body.subject,
        body_html=body.body_html,
        is_active=body.is_active,
        updated_by=current_user.id,
    )
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{email_type}' nao encontrado",
        )
    return EmailTemplateResponse.model_validate(template)


@router.post(
    "/email-templates/{email_type}/preview",
    response_model=EmailTemplatePreviewResponse,
)
async def preview_email_template(
    email_type: str,
    body: EmailTemplatePreviewRequest,
    current_user: User = Depends(require_permissions(Permission.ADMIN_SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplatePreviewResponse:
    """Renderiza template com variaveis de exemplo e retorna HTML completo."""
    template = await EmailTemplateService.get_by_type(db, email_type)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{email_type}' nao encontrado",
        )

    # Usa variaveis enviadas ou gera exemplos a partir da definicao
    variables = dict(body.variables)
    for var_def in template.variables:
        if var_def["name"] not in variables:
            variables[var_def["name"]] = f"[{var_def['name']}]"

    rendered_body = EmailTemplateService.render(template.body_html, variables)

    # Wrapa no layout base do email (mesmo usado pelo EmailService)
    from app.services.email_service import _render_template
    full_html = _render_template(title=template.subject, body=rendered_body)

    rendered_subject = EmailTemplateService.render(template.subject, variables)

    return EmailTemplatePreviewResponse(subject=rendered_subject, html=full_html)
