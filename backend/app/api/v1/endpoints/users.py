"""
User profile endpoints.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import require_permissions
from app.core.rbac import Permission, UserRole, can_assign_role, normalize_role
from app.core.security import decrypt_api_key, encrypt_api_key
from app.models.user import User
from app.schemas.user import (
    ApiKeyMetadataResponse,
    UserByoLlmUsageSummaryResponse,
    UserResponse,
    UserRoleUpdate,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.byollm_usage_service import ByoLlmUsageService

router = APIRouter()


def _build_user_response(user: User) -> UserResponse:
    """
    Build a safe user response without sensitive fields.
    """
    from app.schemas.user import WorkspaceResponseCompact

    is_on_trial = (
        user.trial_ends_at is not None
        and user.trial_ends_at > datetime.utcnow()
    )

    workspace_compact = None
    active_workspace = getattr(user, "active_workspace", None)
    if active_workspace is not None:
        workspace_compact = WorkspaceResponseCompact.model_validate(active_workspace)

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        plan_tier=user.plan_tier,
        role=user.role,
        llm_provider=user.llm_provider,
        has_api_key=bool(user.encrypted_api_key),
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        trial_ends_at=user.trial_ends_at,
        is_on_trial=is_on_trial,
        active_workspace_id=user.active_workspace_id,
        active_workspace=workspace_compact,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(require_permissions(Permission.USERS_READ_SELF)),
) -> UserResponse:
    """
    Get current authenticated user information.
    """
    return _build_user_response(current_user)


@router.get("/me/usage-summary", response_model=UserByoLlmUsageSummaryResponse)
async def get_my_usage_summary(
    days: int = Query(default=7, ge=1, le=90),
    provider: str | None = Query(default=None, max_length=50),
    current_user: User = Depends(require_permissions(Permission.USERS_READ_SELF)),
    db: AsyncSession = Depends(get_db),
) -> UserByoLlmUsageSummaryResponse:
    """
    Return BYO-LLM usage summary for current user in the requested window.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    report = await ByoLlmUsageService.build_report(
        db=db,
        start_date=start_date,
        end_date=end_date,
        provider_filter=provider.lower().strip() if provider else None,
        user_id=current_user.id,
    )

    return UserByoLlmUsageSummaryResponse(
        period_days=days,
        provider_filter=report.get("provider_filter"),
        totals=report["totals"],
        by_provider_model=report["by_provider_model"],
        alerts=[
            {
                "code": alert.get("code", "unknown"),
                "severity": alert.get("severity", "info"),
                "message": alert.get("message", ""),
            }
            for alert in report.get("alerts", [])
            if isinstance(alert, dict)
        ],
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    user_update: UserUpdate,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Update current user's profile and API key/provider metadata.
    """
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name

    if user_update.api_key is not None:
        current_user.encrypted_api_key = encrypt_api_key(user_update.api_key)

    if user_update.llm_provider is not None:
        current_user.llm_provider = user_update.llm_provider

    current_user.updated_at = datetime.utcnow()
    await db.commit()

    # Reload with active_workspace to avoid lazy-load
    stmt = (
        select(User)
        .options(selectinload(User.active_workspace))
        .where(User.id == current_user.id)
    )
    current_user = (await db.execute(stmt)).scalar_one()

    return _build_user_response(current_user)


@router.get("/me/api-keys", response_model=ApiKeyMetadataResponse)
async def get_my_api_keys(
    current_user: User = Depends(require_permissions(Permission.API_KEYS_READ_SELF)),
) -> ApiKeyMetadataResponse:
    """
    Return API key metadata without exposing plaintext secret.
    """
    if not current_user.encrypted_api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No API key configured",
        )

    decrypted_key = decrypt_api_key(current_user.encrypted_api_key)
    masked_key = "***"
    if len(decrypted_key) >= 4:
        masked_key = f"***{decrypted_key[-4:]}"

    return ApiKeyMetadataResponse(
        llm_provider=current_user.llm_provider,
        has_api_key=True,
        masked_key=masked_key,
    )


@router.get("", response_model=list[UserResponse])
async def list_users(
    _current_user: User = Depends(require_permissions(Permission.USERS_LIST)),
    db: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    """
    List all users (admin/owner only).
    """
    stmt = (
        select(User)
        .options(selectinload(User.active_workspace))
        .order_by(User.id)
    )
    result = await db.execute(stmt)
    users = result.scalars().all()
    return [_build_user_response(user) for user in users]


@router.patch("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: UUID,
    role_update: UserRoleUpdate,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_ROLE)),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Update role for a specific user (RBAC-protected).
    """
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Users cannot change their own role",
        )

    stmt = (
        select(User)
        .options(selectinload(User.active_workspace))
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    actor_role = normalize_role(current_user.role)
    if target_user.role == UserRole.OWNER.value and actor_role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can modify owner account role",
        )

    if not can_assign_role(current_user.role, role_update.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role assignment is not allowed for current user",
        )

    target_user.role = role_update.role.value
    target_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(target_user)
    return _build_user_response(target_user)


@router.patch("/{user_id}/status", response_model=UserResponse)
async def update_user_status(
    user_id: UUID,
    status_update: UserStatusUpdate,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_STATUS)),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Enable/disable a user account (RBAC-protected).
    """
    if current_user.id == user_id and not status_update.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Users cannot deactivate their own account",
        )

    stmt = (
        select(User)
        .options(selectinload(User.active_workspace))
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    actor_role = normalize_role(current_user.role)
    if target_user.role == UserRole.OWNER.value and actor_role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can update owner account status",
        )

    target_user.is_active = status_update.is_active
    target_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(target_user)
    return _build_user_response(target_user)
