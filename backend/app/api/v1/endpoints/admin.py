"""
Admin endpoints — dashboard, user management, plans, audit log, system health.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permissions
from app.core.rbac import Permission, UserRole, can_assign_role, normalize_role
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.admin import (
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserUpdate,
    AuditLogListResponse,
    AuditLogResponse,
    CeleryTaskEventListResponse,
    CeleryTaskEventResponse,
    DashboardStats,
    PaginationMeta,
    PlanCreate,
    PlanResponse,
    PlanUpdate,
    SubscriptionResponse,
    SystemHealthResponse,
    UsageSummary,
)
from app.services.admin_dashboard_service import AdminDashboardService
from app.services.audit_log_service import AuditLogService
from app.services.usage_tracking_service import UsageTrackingService

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

    # Usage
    usage_row = await UsageTrackingService.get_today_usage(db, user.id)
    usage = UsageSummary(
        uploads_today=usage_row.uploads_count if usage_row else 0,
        messages_today=usage_row.messages_count if usage_row else 0,
        tokens_today=usage_row.tokens_used if usage_row else 0,
    )

    # Subscription
    sub_stmt = (
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
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
