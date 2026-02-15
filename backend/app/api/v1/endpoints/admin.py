"""
Admin endpoints — dashboard, user management, plans, audit log, system health, RAG.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_permissions
from app.core.rbac import Permission, UserRole, can_assign_role, normalize_role
from app.models.document import Document, Embedding
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.memory import (
    SystemMemoryCreate,
    SystemMemoryResponse,
    SystemMemoryUpdate,
)
from app.models.llm_model import LlmModel
from app.schemas.admin import (
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserUpdate,
    AuditLogListResponse,
    AuditLogResponse,
    BrainworkCrawlRequest,
    BrainworkCrawlResponse,
    CeleryTaskEventListResponse,
    CeleryTaskEventResponse,
    CeleryTaskTriggerRequest,
    CeleryTaskTriggerResponse,
    DashboardStats,
    EntitlementToolStatus,
    LlmModelCreate,
    LlmModelResponse,
    LlmModelUpdate,
    PaginationMeta,
    PlanCreate,
    PlanResponse,
    PlanUpdate,
    SubscriptionResponse,
    SystemHealthResponse,
    UsageSummary,
    UserEntitlementDiagnostic,
)
from app.schemas.rag import (
    FileTypeDistribution,
    RagDocumentItem,
    RagDocumentListResponse,
    RagGapItem,
    RagGapListResponse,
    RagGapStatsResponse,
    RagIngestUrlRequest,
    RagIngestUrlResponse,
    RagReprocessResponse,
    RagStatsResponse,
    RagUploadResponse,
    StatusDistribution,
    TopGapQuery,
)
from app.services.admin_dashboard_service import AdminDashboardService
from app.services.audit_log_service import AuditLogService
from app.services.memory_service import MemoryService, MemoryServiceError
from app.services.subscription_service import (
    StripeNotConfiguredError,
    SubscriptionService,
    SubscriptionServiceError,
)
from app.services.url_ingestion_service import UrlIngestionError, UrlIngestionService
from app.services.usage_tracking_service import UsageTrackingService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _raise_memory_http_error(exc: MemoryServiceError) -> None:
    """Convert memory domain errors to HTTP responses."""
    status_code = status.HTTP_400_BAD_REQUEST
    if exc.code == "memory_not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == "memory_conflict":
        status_code = status.HTTP_409_CONFLICT
    raise HTTPException(status_code=status_code, detail=exc.detail) from exc


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard(
    _current_user: User = Depends(require_permissions(Permission.ADMIN_DASHBOARD)),
    db: AsyncSession = Depends(get_db),
) -> DashboardStats:
    """Aggregated dashboard statistics."""
    stats = await AdminDashboardService.get_stats(db)
    return DashboardStats(**stats)


@router.get("/system-health", response_model=SystemHealthResponse)
async def get_system_health(
    _current_user: User = Depends(require_permissions(Permission.ADMIN_SYSTEM_HEALTH)),
    db: AsyncSession = Depends(get_db),
) -> SystemHealthResponse:
    """System health check for DB, Redis, Celery."""
    health = await AdminDashboardService.get_system_health(db)
    return SystemHealthResponse(**health)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=255),
    role: Optional[str] = Query(default=None),
    plan_tier: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    _current_user: User = Depends(require_permissions(Permission.ADMIN_USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    """Paginated user list with search and filters."""
    filters = []
    if search:
        term = f"%{search}%"
        filters.append(
            or_(
                User.email.ilike(term),
                User.full_name.ilike(term),
            )
        )
    if role:
        filters.append(User.role == role)
    if plan_tier:
        filters.append(User.plan_tier == plan_tier)
    if is_active is not None:
        filters.append(User.is_active.is_(is_active))

    # Count
    count_q = select(func.count()).select_from(User)
    if filters:
        count_q = count_q.where(*filters)
    total = int((await db.execute(count_q)).scalar_one())

    # Fetch
    offset = (page - 1) * limit
    q = select(User).order_by(desc(User.created_at)).offset(offset).limit(limit)
    if filters:
        q = q.where(*filters)
    users = (await db.execute(q)).scalars().all()

    pages = (total + limit - 1) // limit if total else 0
    return AdminUserListResponse(
        items=[
            AdminUserListItem(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                plan_tier=u.plan_tier,
                role=u.role,
                is_active=u.is_active,
                is_verified=u.is_verified,
                created_at=u.created_at,
                last_login_at=u.last_login_at,
            )
            for u in users
        ],
        pagination=PaginationMeta(total=total, page=page, pages=pages, limit=limit),
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
async def get_user_detail(
    user_id: UUID,
    _current_user: User = Depends(require_permissions(Permission.ADMIN_USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserDetailResponse:
    """Detailed user info including usage and subscription."""
    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Usage (resolve via active workspace)
    ws_id = user.active_workspace_id
    if ws_id:
        usage_row = await UsageTrackingService.get_today_usage(db, ws_id, user.id)
    else:
        usage_row = None
    usage = UsageSummary(
        uploads_today=usage_row.uploads_count if usage_row else 0,
        messages_today=usage_row.messages_count if usage_row else 0,
        tokens_today=usage_row.tokens_used if usage_row else 0,
    )

    # Subscription (via workspace)
    from app.models.workspace import Workspace, WorkspaceMember
    sub = None
    if ws_id:
        sub_stmt = (
            select(Subscription)
            .where(
                Subscription.workspace_id == ws_id,
                Subscription.status.in_(["active", "trialing", "past_due"]),
            )
            .order_by(desc(Subscription.created_at))
            .limit(1)
        )
        sub = (await db.execute(sub_stmt)).scalar_one_or_none()

    return AdminUserDetailResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        plan_tier=user.plan_tier,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        llm_provider=user.llm_provider,
        has_api_key=bool(user.encrypted_api_key),
        usage=usage,
        subscription=SubscriptionResponse.model_validate(sub) if sub else None,
    )


@router.get("/users/{user_id}/entitlements", response_model=UserEntitlementDiagnostic)
async def get_user_entitlements(
    user_id: UUID,
    _current_user: User = Depends(require_permissions(Permission.ADMIN_USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> UserEntitlementDiagnostic:
    """Diagnostico de entitlements efetivos: features do plano e acesso a cada tool."""
    from app.services.plan_limit_service import PlanLimitService
    from app.services.tool_guardrail_service import FEATURE_TOOL_MAP, TOOL_FEATURE_MAP

    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    plan = await PlanLimitService.get_user_plan(db, user)
    raw_features = plan.features if plan.features else {}
    features: dict[str, bool] = {
        k: bool(v) for k, v in raw_features.items() if isinstance(k, str)
    }

    tools: list[EntitlementToolStatus] = []
    for feature, tool_names in FEATURE_TOOL_MAP.items():
        enabled = features.get(feature, False)
        for tool_name in tool_names:
            tools.append(
                EntitlementToolStatus(
                    tool=tool_name,
                    feature=feature,
                    allowed=enabled,
                    reason=None if enabled else f"feature '{feature}' desabilitada no plano '{plan.name}'",
                )
            )

    return UserEntitlementDiagnostic(
        user_id=user.id,
        email=user.email,
        plan_name=plan.name,
        plan_features=features,
        tools=tools,
    )


@router.patch("/users/{user_id}", response_model=AdminUserDetailResponse)
async def update_user(
    user_id: UUID,
    body: AdminUserUpdate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserDetailResponse:
    """Update user role, status, or plan_tier with audit logging."""
    stmt = select(User).where(User.id == user_id)
    target = (await db.execute(stmt)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    actor_role = normalize_role(current_user.role)
    changes: dict = {}

    # Protect owner
    if target.role == UserRole.OWNER.value and actor_role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can modify owner account",
        )

    if body.role is not None and body.role != target.role:
        new_role = UserRole(body.role)
        if not can_assign_role(current_user.role, new_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role assignment not allowed",
            )
        changes["role"] = {"from": target.role, "to": body.role}
        target.role = body.role

    if body.is_active is not None and body.is_active != target.is_active:
        if current_user.id == user_id and not body.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate own account",
            )
        changes["is_active"] = {"from": target.is_active, "to": body.is_active}
        target.is_active = body.is_active

    if body.plan_tier is not None and body.plan_tier != target.plan_tier:
        changes["plan_tier"] = {"from": target.plan_tier, "to": body.plan_tier}
        target.plan_tier = body.plan_tier

    if changes:
        target.updated_at = datetime.utcnow()
        await AuditLogService.record(
            db,
            actor_id=current_user.id,
            action="user.updated",
            target_type="user",
            target_id=str(target.id),
            changes=changes,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )

    await db.flush()

    # Return full detail
    return await get_user_detail(user_id, _current_user=current_user, db=db)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a user permanently (cascade deletes conversations, documents, etc)."""
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete own account",
        )

    stmt = select(User).where(User.id == user_id)
    target = (await db.execute(stmt)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    actor_role = normalize_role(current_user.role)
    if target.role == UserRole.OWNER.value and actor_role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can delete owner account",
        )

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="user.deleted",
        target_type="user",
        target_id=str(target.id),
        changes={"email": target.email, "role": target.role, "plan_tier": target.plan_tier},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.delete(target)
    await db.flush()


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

@router.get("/audit-log", response_model=AuditLogListResponse)
async def list_audit_log(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    action: Optional[str] = Query(default=None),
    actor_id: Optional[UUID] = Query(default=None),
    target_type: Optional[str] = Query(default=None),
    _current_user: User = Depends(require_permissions(Permission.ADMIN_AUDIT_LOG)),
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    """Paginated audit log with optional filters."""
    items, total = await AuditLogService.list_logs(
        db, page=page, limit=limit,
        action=action, actor_id=actor_id, target_type=target_type,
    )
    pages = (total + limit - 1) // limit if total else 0
    return AuditLogListResponse(
        items=[AuditLogResponse(**item) for item in items],
        pagination=PaginationMeta(total=total, page=page, pages=pages, limit=limit),
    )


# ---------------------------------------------------------------------------
# System Memories
# ---------------------------------------------------------------------------

@router.get("/system-memories", response_model=list[SystemMemoryResponse])
async def list_system_memories(
    include_inactive: bool = Query(default=False),
    _current_user: User = Depends(require_permissions(Permission.ADMIN_SYSTEM_MEMORIES_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[SystemMemoryResponse]:
    """List curated system memories available to all users."""
    service = MemoryService(db)
    rows = await service.list_system_memories(include_inactive=include_inactive)
    return [SystemMemoryResponse.model_validate(row) for row in rows]


@router.post("/system-memories", response_model=SystemMemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_system_memory(
    body: SystemMemoryCreate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_SYSTEM_MEMORIES_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SystemMemoryResponse:
    """Create a curated system memory."""
    service = MemoryService(db)
    try:
        memory = await service.create_system_memory(
            actor_id=current_user.id,
            payload=body,
        )
    except MemoryServiceError as exc:
        _raise_memory_http_error(exc)

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="memory_system.created",
        target_type="system_memory",
        target_id=str(memory.id),
        changes=body.model_dump(mode="json"),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.flush()
    return SystemMemoryResponse.model_validate(memory)


@router.patch("/system-memories/{memory_id}", response_model=SystemMemoryResponse)
async def update_system_memory(
    memory_id: UUID,
    body: SystemMemoryUpdate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_SYSTEM_MEMORIES_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SystemMemoryResponse:
    """Update a curated system memory."""
    service = MemoryService(db)
    existing = await service.get_system_memory(memory_id=memory_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memoria de sistema nao encontrada")

    before = {
        "scope": existing.scope,
        "scope_name": existing.scope_name,
        "memory_key": existing.memory_key,
        "memory_value": existing.memory_value,
        "tags": existing.tags,
        "ttl_seconds": existing.ttl_seconds,
        "expires_at": existing.expires_at.isoformat() if existing.expires_at else None,
        "version": existing.version,
        "is_active": existing.is_active,
    }

    try:
        updated = await service.update_system_memory(
            actor_id=current_user.id,
            memory_id=memory_id,
            payload=body,
        )
    except MemoryServiceError as exc:
        _raise_memory_http_error(exc)

    after = {
        "scope": updated.scope,
        "scope_name": updated.scope_name,
        "memory_key": updated.memory_key,
        "memory_value": updated.memory_value,
        "tags": updated.tags,
        "ttl_seconds": updated.ttl_seconds,
        "expires_at": updated.expires_at.isoformat() if updated.expires_at else None,
        "version": updated.version,
        "is_active": updated.is_active,
    }
    changes = {
        key: {"from": before.get(key), "to": after.get(key)}
        for key in after
        if before.get(key) != after.get(key)
    }
    if changes:
        await AuditLogService.record(
            db,
            actor_id=current_user.id,
            action="memory_system.updated",
            target_type="system_memory",
            target_id=str(updated.id),
            changes=changes,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )

    await db.flush()
    return SystemMemoryResponse.model_validate(updated)


@router.delete("/system-memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_system_memory(
    memory_id: UUID,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_SYSTEM_MEMORIES_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a curated system memory."""
    service = MemoryService(db)
    try:
        memory = await service.delete_system_memory(
            actor_id=current_user.id,
            memory_id=memory_id,
        )
    except MemoryServiceError as exc:
        _raise_memory_http_error(exc)

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="memory_system.deleted",
        target_type="system_memory",
        target_id=str(memory.id),
        changes={"is_active": {"from": True, "to": False}},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.flush()


# ---------------------------------------------------------------------------
# LLM Model Catalog
# ---------------------------------------------------------------------------

@router.get("/llm-models", response_model=list[LlmModelResponse])
async def list_llm_models(
    _current_user: User = Depends(require_permissions(Permission.ADMIN_PLANS_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[LlmModelResponse]:
    """List all LLM models in the catalog."""
    stmt = select(LlmModel).order_by(LlmModel.sort_order, LlmModel.provider)
    models = (await db.execute(stmt)).scalars().all()
    return [LlmModelResponse.model_validate(m) for m in models]


@router.post("/llm-models", response_model=LlmModelResponse, status_code=status.HTTP_201_CREATED)
async def create_llm_model(
    body: LlmModelCreate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_PLANS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> LlmModelResponse:
    """Add a new LLM model to the catalog."""
    existing = (
        await db.execute(
            select(LlmModel).where(
                LlmModel.provider == body.provider,
                LlmModel.model_id == body.model_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Model '{body.provider}/{body.model_id}' already exists",
        )

    model = LlmModel(**body.model_dump())
    db.add(model)

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="llm_model.created",
        target_type="llm_model",
        target_id=str(model.id),
        changes=body.model_dump(),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.flush()
    await db.refresh(model)
    return LlmModelResponse.model_validate(model)


@router.patch("/llm-models/{model_id}", response_model=LlmModelResponse)
async def update_llm_model(
    model_id: UUID,
    body: LlmModelUpdate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_PLANS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> LlmModelResponse:
    """Update an LLM model in the catalog."""
    stmt = select(LlmModel).where(LlmModel.id == model_id)
    model = (await db.execute(stmt)).scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM model not found")

    changes = {}
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        old = getattr(model, field)
        if old != value:
            changes[field] = {"from": old, "to": value}
            setattr(model, field, value)

    if changes:
        from datetime import datetime as _dt
        model.updated_at = _dt.utcnow()
        await AuditLogService.record(
            db,
            actor_id=current_user.id,
            action="llm_model.updated",
            target_type="llm_model",
            target_id=str(model.id),
            changes=changes,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )

    await db.flush()
    await db.refresh(model)
    return LlmModelResponse.model_validate(model)


@router.delete("/llm-models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_model(
    model_id: UUID,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_PLANS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an LLM model from the catalog."""
    stmt = select(LlmModel).where(LlmModel.id == model_id)
    model = (await db.execute(stmt)).scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM model not found")

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="llm_model.deleted",
        target_type="llm_model",
        target_id=str(model.id),
        changes={"provider": model.provider, "model_id": model.model_id},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.delete(model)
    await db.flush()


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    _current_user: User = Depends(require_permissions(Permission.ADMIN_PLANS_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[PlanResponse]:
    """List all plans (including inactive)."""
    stmt = select(Plan).order_by(Plan.sort_order)
    plans = (await db.execute(stmt)).scalars().all()
    return [PlanResponse.model_validate(p) for p in plans]


@router.post("/plans", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    body: PlanCreate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_PLANS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PlanResponse:
    """Create a new subscription plan (owner only)."""
    # Check name uniqueness
    existing = (
        await db.execute(select(Plan).where(Plan.name == body.name))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Plan '{body.name}' already exists",
        )

    plan = Plan(**body.model_dump())
    db.add(plan)

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="plan.created",
        target_type="plan",
        target_id=str(plan.id),
        changes=body.model_dump(),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.flush()
    await db.refresh(plan)
    return PlanResponse.model_validate(plan)


@router.patch("/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: UUID,
    body: PlanUpdate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_PLANS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PlanResponse:
    """Update an existing plan (owner only)."""
    stmt = select(Plan).where(Plan.id == plan_id)
    plan = (await db.execute(stmt)).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    changes = {}
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        old = getattr(plan, field)
        if old != value:
            changes[field] = {"from": old, "to": value}
            setattr(plan, field, value)

    if changes:
        plan.updated_at = datetime.utcnow()
        await AuditLogService.record(
            db,
            actor_id=current_user.id,
            action="plan.updated",
            target_type="plan",
            target_id=str(plan.id),
            changes=changes,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )

    await db.flush()
    await db.refresh(plan)
    return PlanResponse.model_validate(plan)


@router.delete("/plans/{plan_id}", status_code=status.HTTP_200_OK)
async def delete_plan(
    plan_id: UUID,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_PLANS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PlanResponse:
    """Soft-delete a plan (set is_active=False)."""
    stmt = select(Plan).where(Plan.id == plan_id)
    plan = (await db.execute(stmt)).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    plan.is_active = False
    plan.updated_at = datetime.utcnow()

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="plan.deactivated",
        target_type="plan",
        target_id=str(plan.id),
        changes={"is_active": {"from": True, "to": False}},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.flush()
    await db.refresh(plan)
    return PlanResponse.model_validate(plan)


@router.post("/plans/{plan_id}/stripe-sync", response_model=PlanResponse)
async def stripe_sync_plan(
    plan_id: UUID,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_PLANS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PlanResponse:
    """
    Create or update Stripe Product + Price for this plan.

    - If stripe_product_id is empty, creates a new Stripe Product.
    - Always creates a new Stripe Price (Stripe prices are immutable).
    - Updates the plan with the resulting IDs.
    """
    import stripe as stripe_lib

    stmt = select(Plan).where(Plan.id == plan_id)
    plan = (await db.execute(stmt)).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    if plan.price_cents <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Plano com preco zero nao pode ser sincronizado com Stripe. Defina um preco primeiro.",
        )

    try:
        svc = await SubscriptionService.from_settings(db)
    except StripeNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.detail,
        ) from exc

    svc._configure_stripe()
    logger.info("Stripe sync started for plan %s (%s)", plan.name, plan_id)

    changes: dict = {}

    try:
        # 1. Product
        if plan.stripe_product_id:
            # Update existing product name
            stripe_lib.Product.modify(
                plan.stripe_product_id,
                name=plan.display_name,
                metadata={"plan_slug": plan.name, "plan_id": str(plan.id)},
            )
        else:
            product = stripe_lib.Product.create(
                name=plan.display_name,
                metadata={"plan_slug": plan.name, "plan_id": str(plan.id)},
            )
            changes["stripe_product_id"] = {"from": None, "to": product.id}
            plan.stripe_product_id = product.id

        # 2. Price (always create new — Stripe prices are immutable)
        interval = "month" if plan.billing_period == "monthly" else "year"
        price = stripe_lib.Price.create(
            product=plan.stripe_product_id,
            unit_amount=plan.price_cents,
            currency="brl",
            recurring={"interval": interval},
            metadata={"plan_slug": plan.name, "plan_id": str(plan.id)},
        )
        old_price_id = plan.stripe_price_id
        changes["stripe_price_id"] = {"from": old_price_id, "to": price.id}
        plan.stripe_price_id = price.id

        # Deactivate old price if replaced
        if old_price_id:
            try:
                stripe_lib.Price.modify(old_price_id, active=False)
            except Exception:
                pass  # Non-critical

    except stripe_lib.StripeError as exc:
        logger.exception("Stripe API error syncing plan %s: %s", plan_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro ao comunicar com Stripe: {exc.user_message or str(exc)}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error syncing plan %s with Stripe", plan_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro inesperado ao sincronizar com Stripe: {str(exc)}",
        ) from exc

    plan.updated_at = datetime.utcnow()

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="plan.stripe_synced",
        target_type="plan",
        target_id=str(plan.id),
        changes=changes,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.flush()
    await db.refresh(plan)
    return PlanResponse.model_validate(plan)


# ---------------------------------------------------------------------------
# Celery Task Events
# ---------------------------------------------------------------------------

@router.get("/celery-tasks", response_model=CeleryTaskEventListResponse)
async def list_celery_tasks(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    task_name: Optional[str] = Query(default=None),
    _current_user: User = Depends(require_permissions(Permission.ADMIN_SYSTEM_HEALTH)),
    db: AsyncSession = Depends(get_db),
) -> CeleryTaskEventListResponse:
    """Paginated Celery task execution log."""
    from app.models.celery_task_event import CeleryTaskEvent

    filters = []
    if status_filter:
        filters.append(CeleryTaskEvent.status == status_filter)
    if task_name:
        filters.append(CeleryTaskEvent.task_name.ilike(f"%{task_name}%"))

    # Count
    count_q = select(func.count()).select_from(CeleryTaskEvent)
    if filters:
        count_q = count_q.where(*filters)
    total = int((await db.execute(count_q)).scalar_one())

    # Fetch
    offset = (page - 1) * limit
    q = (
        select(CeleryTaskEvent)
        .order_by(desc(CeleryTaskEvent.started_at))
        .offset(offset)
        .limit(limit)
    )
    if filters:
        q = q.where(*filters)
    events = (await db.execute(q)).scalars().all()

    pages = (total + limit - 1) // limit if total else 0
    return CeleryTaskEventListResponse(
        items=[CeleryTaskEventResponse.model_validate(e) for e in events],
        pagination=PaginationMeta(total=total, page=page, pages=pages, limit=limit),
    )


# Whitelist de tasks que podem ser disparadas manualmente via admin UI.
TRIGGERABLE_TASKS: dict[str, str] = {
    "cleanup_orphan_uploads": "app.workers.tasks.maintenance_tasks.cleanup_orphan_uploads",
    "cleanup_expired_tokens": "app.workers.tasks.maintenance_tasks.cleanup_expired_tokens",
    "service_health_check": "app.workers.tasks.maintenance_tasks.service_health_check",
    "recalculate_stale_embeddings": "app.workers.tasks.maintenance_tasks.recalculate_stale_embeddings",
    "mark_stale_tasks_timeout": "app.workers.tasks.maintenance_tasks.mark_stale_tasks_timeout",
    "downgrade_expired_trials": "app.workers.tasks.maintenance_tasks.downgrade_expired_trials",
    "reconcile_seat_quantities": "app.workers.tasks.billing_tasks.reconcile_seat_quantities",
    "check_byollm_discount_eligibility": "app.workers.tasks.billing_tasks.check_byollm_discount_eligibility",
    "crawl_brainwork_blog": "app.workers.tasks.brainwork_tasks.crawl_brainwork_blog",
}


@router.post("/celery-tasks/trigger", response_model=CeleryTaskTriggerResponse)
async def trigger_celery_task(
    body: CeleryTaskTriggerRequest,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_SYSTEM_HEALTH)),
    db: AsyncSession = Depends(get_db),
) -> CeleryTaskTriggerResponse:
    """Dispara uma task Celery agendada manualmente."""
    full_name = TRIGGERABLE_TASKS.get(body.task_name)
    if not full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task '{body.task_name}' nao esta na whitelist de tasks disparaveis",
        )

    from app.workers.celery_app import celery_app

    result = celery_app.send_task(full_name)

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="celery_task.triggered",
        target_type="celery_task",
        target_id=body.task_name,
        changes={"task_name": body.task_name, "celery_task_id": result.id},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.flush()

    return CeleryTaskTriggerResponse(
        task_id=result.id,
        task_name=body.task_name,
        message="Task disparada com sucesso",
    )


# ---------------------------------------------------------------------------
# RAG Management
# ---------------------------------------------------------------------------

PROCESSABLE_EXTENSIONS = {"txt", "conf", "cfg", "log", "md", "pdf"}


@router.get("/rag/stats", response_model=RagStatsResponse)
async def get_rag_stats(
    _current_user: User = Depends(require_permissions(Permission.ADMIN_RAG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RagStatsResponse:
    """Totais e distribuicoes de documentos e chunks RAG."""
    # Total documents
    total_docs = int(
        (await db.execute(select(func.count()).select_from(Document))).scalar_one()
    )
    global_docs = int(
        (await db.execute(
            select(func.count()).select_from(Document).where(Document.user_id.is_(None))
        )).scalar_one()
    )
    local_docs = total_docs - global_docs

    # Total chunks
    total_chunks = int(
        (await db.execute(select(func.count()).select_from(Embedding))).scalar_one()
    )
    global_chunks = int(
        (await db.execute(
            select(func.count()).select_from(Embedding).where(Embedding.user_id.is_(None))
        )).scalar_one()
    )
    local_chunks = total_chunks - global_chunks

    # By file_type
    ft_rows = (await db.execute(
        select(Document.file_type, func.count())
        .group_by(Document.file_type)
        .order_by(func.count().desc())
    )).all()
    by_file_type = [FileTypeDistribution(file_type=r[0], count=r[1]) for r in ft_rows]

    # By status
    st_rows = (await db.execute(
        select(Document.status, func.count())
        .group_by(Document.status)
        .order_by(func.count().desc())
    )).all()
    by_status = [StatusDistribution(status=r[0], count=r[1]) for r in st_rows]

    return RagStatsResponse(
        total_documents=total_docs,
        total_chunks=total_chunks,
        global_documents=global_docs,
        global_chunks=global_chunks,
        local_documents=local_docs,
        local_chunks=local_chunks,
        by_file_type=by_file_type,
        by_status=by_status,
    )


@router.get("/rag/documents", response_model=RagDocumentListResponse)
async def list_rag_documents(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    scope: Optional[str] = Query(default=None, pattern="^(global|local|all)$"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    file_type: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=255),
    _current_user: User = Depends(require_permissions(Permission.ADMIN_RAG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RagDocumentListResponse:
    """Lista paginada de documentos RAG com filtros."""
    filters = []
    if scope == "global":
        filters.append(Document.user_id.is_(None))
    elif scope == "local":
        filters.append(Document.user_id.isnot(None))

    if status_filter:
        filters.append(Document.status == status_filter)
    if file_type:
        filters.append(Document.file_type == file_type)
    if search:
        term = f"%{search}%"
        filters.append(
            or_(
                Document.original_filename.ilike(term),
                Document.filename.ilike(term),
            )
        )

    # Count
    count_q = select(func.count()).select_from(Document)
    if filters:
        count_q = count_q.where(*filters)
    total = int((await db.execute(count_q)).scalar_one())

    # Chunk count subquery
    chunk_count_sq = (
        select(func.count())
        .where(Embedding.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )

    # Fetch with optional user email join
    q = (
        select(
            Document,
            User.email.label("user_email"),
            chunk_count_sq.label("chunk_count"),
        )
        .outerjoin(User, Document.user_id == User.id)
        .order_by(desc(Document.created_at))
        .offset((page - 1) * limit)
        .limit(limit)
    )
    if filters:
        q = q.where(*filters)

    rows = (await db.execute(q)).all()

    items = []
    for row in rows:
        doc = row[0]
        user_email = row[1]
        chunk_cnt = row[2] or 0
        items.append(
            RagDocumentItem(
                id=doc.id,
                user_id=doc.user_id,
                user_email=user_email,
                filename=doc.filename,
                original_filename=doc.original_filename,
                file_type=doc.file_type,
                file_size_bytes=doc.file_size_bytes,
                status=doc.status,
                chunk_count=chunk_cnt,
                metadata=doc.document_metadata,
                created_at=doc.created_at,
                processed_at=doc.processed_at,
            )
        )

    pages = (total + limit - 1) // limit if total else 0
    return RagDocumentListResponse(
        items=items,
        pagination=PaginationMeta(total=total, page=page, pages=pages, limit=limit),
    )


@router.post(
    "/rag/documents/upload",
    response_model=RagUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_rag_document(
    file: UploadFile = File(...),
    request: Request = None,
    current_user: User = Depends(require_permissions(Permission.ADMIN_RAG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RagUploadResponse:
    """Upload de documento para RAG Global (user_id=None)."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename obrigatorio",
        )

    ext = Path(file.filename).suffix.lower().lstrip(".")
    allowed = settings.ALLOWED_FILE_EXTENSIONS.split(",")
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extensao '{ext}' nao permitida",
        )

    # Ler conteudo em chunks — rejeitar antes de materializar tudo
    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    chunks: list[bytes] = []
    total_read = 0
    while True:
        chunk = await file.read(1024 * 1024)  # 1 MB por vez
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Arquivo excede limite de {settings.MAX_FILE_SIZE_MB} MB",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    # Armazenar (R2 ou local)
    from app.services.url_ingestion_service import _store_file

    doc_uuid = uuid4()
    stored_filename = f"{doc_uuid}.{ext}"
    object_key = f"uploads/global/{stored_filename}"
    storage_path = await _store_file(db, object_key, content, file.content_type or "application/octet-stream")

    document = Document(
        id=doc_uuid,
        user_id=None,
        filename=stored_filename,
        original_filename=file.filename,
        file_type=ext,
        file_size_bytes=len(content),
        storage_path=storage_path,
        mime_type=file.content_type,
        status="uploaded",
        document_metadata={"ingestion_method": "upload"},
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="rag.document_uploaded",
        target_type="document",
        target_id=str(document.id),
        changes={"filename": file.filename, "file_type": ext, "scope": "global"},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent") if request else None,
    )
    await db.commit()

    # Trigger Celery
    if ext in PROCESSABLE_EXTENSIONS:
        from app.workers.tasks.document_tasks import process_document

        process_document.delay(str(document.id))

    return RagUploadResponse(
        id=document.id,
        filename=document.original_filename,
        file_type=document.file_type,
        file_size_bytes=document.file_size_bytes,
        status=document.status,
        created_at=document.created_at,
    )


@router.post(
    "/rag/documents/ingest-url",
    response_model=RagIngestUrlResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_rag_url(
    body: RagIngestUrlRequest,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_RAG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RagIngestUrlResponse:
    """Ingere URL como documento RAG Global."""
    service = UrlIngestionService(db)

    try:
        document = await service.ingest(url=body.url, title=body.title)
    except UrlIngestionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await db.commit()
    await db.refresh(document)

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="rag.url_ingested",
        target_type="document",
        target_id=str(document.id),
        changes={"url": body.url, "title": body.title, "scope": "global"},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()

    # Trigger Celery
    ext = Path(document.original_filename).suffix.lower().lstrip(".")
    if ext in PROCESSABLE_EXTENSIONS:
        from app.workers.tasks.document_tasks import process_document

        process_document.delay(str(document.id))

    source_url = ""
    if document.document_metadata and isinstance(document.document_metadata, dict):
        source_url = document.document_metadata.get("source_url", body.url)

    return RagIngestUrlResponse(
        id=document.id,
        original_filename=document.original_filename,
        file_type=document.file_type,
        file_size_bytes=document.file_size_bytes,
        status=document.status,
        source_url=source_url,
        created_at=document.created_at,
    )


@router.post("/rag/documents/{document_id}/reprocess", response_model=RagReprocessResponse)
async def reprocess_rag_document(
    document_id: UUID,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_RAG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RagReprocessResponse:
    """Reprocessa documento RAG: deleta embeddings e redespacha Celery."""
    stmt = select(Document).where(Document.id == document_id)
    document = (await db.execute(stmt)).scalar_one_or_none()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento nao encontrado",
        )

    if document.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Documento ja esta sendo processado",
        )

    # Deletar embeddings existentes
    await db.execute(
        delete(Embedding).where(Embedding.document_id == document_id)
    )

    # Reset status
    document.status = "uploaded"
    document.processed_at = None
    await db.commit()

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="rag.document_reprocessed",
        target_type="document",
        target_id=str(document.id),
        changes={"filename": document.original_filename},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()

    # Trigger Celery
    ext = Path(document.original_filename).suffix.lower().lstrip(".")
    if ext in PROCESSABLE_EXTENSIONS:
        from app.workers.tasks.document_tasks import process_document

        process_document.delay(str(document.id))

    return RagReprocessResponse(
        id=document.id,
        status="uploaded",
        message="Documento enviado para reprocessamento",
    )


@router.delete("/rag/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rag_document(
    document_id: UUID,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.ADMIN_RAG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deleta documento RAG (cascade deleta embeddings)."""
    stmt = select(Document).where(Document.id == document_id)
    document = (await db.execute(stmt)).scalar_one_or_none()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento nao encontrado",
        )

    storage_path = document.storage_path
    filename = document.original_filename
    scope = "global" if document.user_id is None else "local"

    await db.delete(document)
    await db.commit()

    # Limpar arquivo (R2 ou disco)
    _is_r2 = storage_path.startswith("uploads/") and not Path(storage_path).is_absolute()
    if _is_r2:
        try:
            from app.services.r2_storage_service import R2NotConfiguredError, R2StorageService
            r2 = await R2StorageService.from_settings(db)
            r2.delete_object(storage_path)
        except (R2NotConfiguredError, Exception):
            logger.warning("Falha ao deletar objeto R2: %s", storage_path)
    else:
        try:
            file_path = Path(storage_path)
            if file_path.is_file():
                file_path.unlink()
        except OSError:
            logger.warning("Falha ao deletar arquivo local: %s", storage_path)

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="rag.document_deleted",
        target_type="document",
        target_id=str(document_id),
        changes={"filename": filename, "scope": scope},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# RAG Gap Tracking
# ---------------------------------------------------------------------------

@router.get("/rag/gaps", response_model=RagGapListResponse)
async def list_rag_gaps(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tool_name: Optional[str] = Query(default=None, pattern="^(search_rag_global|search_rag_local)$"),
    gap_type: Optional[str] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=255),
    _current_user: User = Depends(require_permissions(Permission.ADMIN_RAG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RagGapListResponse:
    """Lista paginada de gaps detectados nas buscas RAG."""
    from app.models.rag_gap_event import RagGapEvent

    filters = []
    if tool_name:
        filters.append(RagGapEvent.tool_name == tool_name)
    if gap_type:
        filters.append(RagGapEvent.gap_type == gap_type)
    if date_from:
        filters.append(RagGapEvent.created_at >= date_from)
    if date_to:
        filters.append(RagGapEvent.created_at <= date_to)
    if search:
        filters.append(RagGapEvent.query.ilike(f"%{search}%"))

    # Count
    count_q = select(func.count()).select_from(RagGapEvent)
    if filters:
        count_q = count_q.where(*filters)
    total = int((await db.execute(count_q)).scalar_one())

    # Fetch with user email join
    offset = (page - 1) * limit
    q = (
        select(RagGapEvent, User.email.label("user_email"))
        .outerjoin(User, RagGapEvent.user_id == User.id)
        .order_by(desc(RagGapEvent.created_at))
        .offset(offset)
        .limit(limit)
    )
    if filters:
        q = q.where(*filters)

    rows = (await db.execute(q)).all()

    items = []
    for row in rows:
        gap = row[0]
        user_email = row[1]
        items.append(
            RagGapItem(
                id=gap.id,
                user_id=gap.user_id,
                user_email=user_email,
                conversation_id=gap.conversation_id,
                tool_name=gap.tool_name,
                query=gap.query,
                gap_type=gap.gap_type,
                result_preview=gap.result_preview,
                created_at=gap.created_at,
            )
        )

    pages = (total + limit - 1) // limit if total else 0
    return RagGapListResponse(
        items=items,
        pagination=PaginationMeta(total=total, page=page, pages=pages, limit=limit),
    )


@router.get("/rag/gaps/stats", response_model=RagGapStatsResponse)
async def get_rag_gap_stats(
    _current_user: User = Depends(require_permissions(Permission.ADMIN_RAG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RagGapStatsResponse:
    """Estatisticas agregadas de gaps RAG: totais e top queries sem resposta."""
    from app.models.rag_gap_event import RagGapEvent

    # Total gaps
    total_gaps = int(
        (await db.execute(select(func.count()).select_from(RagGapEvent))).scalar_one()
    )
    global_gaps = int(
        (await db.execute(
            select(func.count())
            .select_from(RagGapEvent)
            .where(RagGapEvent.tool_name == "search_rag_global")
        )).scalar_one()
    )
    local_gaps = total_gaps - global_gaps

    # Top queries (GROUP BY query, COUNT, ORDER BY count DESC LIMIT 20)
    top_q = (
        select(
            RagGapEvent.query,
            func.count().label("cnt"),
            func.max(RagGapEvent.created_at).label("last_seen"),
        )
        .group_by(RagGapEvent.query)
        .order_by(func.count().desc())
        .limit(20)
    )
    top_rows = (await db.execute(top_q)).all()
    top_queries = [
        TopGapQuery(query=row[0], count=row[1], last_seen=row[2])
        for row in top_rows
    ]

    return RagGapStatsResponse(
        total_gaps=total_gaps,
        global_gaps=global_gaps,
        local_gaps=local_gaps,
        top_queries=top_queries,
    )


# ---------------------------------------------------------------------------
# Brainwork Crawler
# ---------------------------------------------------------------------------

@router.post("/rag/crawl-brainwork", response_model=BrainworkCrawlResponse)
async def crawl_brainwork(
    body: BrainworkCrawlRequest | None = None,
    request: Request = None,
    current_user: User = Depends(require_permissions(Permission.ADMIN_RAG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BrainworkCrawlResponse:
    """Executa crawler do brainwork.com.br para ingestao no RAG Global."""
    from app.services.brainwork_crawler_service import BrainworkCrawlerService

    max_pages = body.max_pages if body else None

    service = BrainworkCrawlerService(db)
    result = await service.crawl(max_pages=max_pages)

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="rag.brainwork_crawl",
        target_type="crawler",
        target_id="brainwork",
        changes={
            "max_pages": max_pages,
            "total_urls": result.total_urls,
            "new_urls": result.new_urls,
            "ingested": result.ingested,
            "failed": result.failed,
        },
        ip_address=_client_ip(request) if request else "unknown",
        user_agent=request.headers.get("user-agent") if request else None,
    )

    return BrainworkCrawlResponse(
        total_urls=result.total_urls,
        new_urls=result.new_urls,
        ingested=result.ingested,
        failed=result.failed,
        errors=result.errors,
    )
