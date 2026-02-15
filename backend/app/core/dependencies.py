"""
FastAPI dependencies for auth, database, etc.
"""
from collections.abc import Callable
from datetime import datetime
from typing import Optional
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.rbac import Permission, UserRole, has_permission, normalize_role
from app.core.security import decode_token
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

# OAuth2 scheme for JWT bearer token
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user.
    
    Args:
        credentials: JWT token from Authorization header
        db: Database session
        
    Returns:
        User object
        
    Raises:
        HTTPException: If token is invalid or user not found
        
    Example:
        @app.get("/me")
        async def get_me(user: User = Depends(get_current_user)):
            return user
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decode token
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload is None:
        raise credentials_exception

    token_type = payload.get("type", "access")
    if token_type != "access":
        raise credentials_exception
    
    raw_user_id: Optional[str] = payload.get("sub")
    if raw_user_id is None:
        raise credentials_exception
    try:
        user_id = UUID(str(raw_user_id))
    except (TypeError, ValueError):
        raise credentials_exception
    
    # Get user from database (eagerly load active_workspace to avoid lazy-load in async)
    stmt = (
        select(User)
        .options(selectinload(User.active_workspace))
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    # Auto-downgrade expired trial
    if user.trial_ends_at and datetime.utcnow() > user.trial_ends_at:
        user.plan_tier = "free"
        user.trial_ends_at = None
        await db.commit()

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to ensure user is active.
    
    Args:
        current_user: User from get_current_user
        
    Returns:
        Active user
        
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    return current_user


def require_permissions(*required_permissions: Permission) -> Callable[..., User]:
    """
    Build dependency that requires one or more RBAC permissions.

    Args:
        required_permissions: Permissions required to access a route.

    Returns:
        FastAPI dependency that yields authenticated user if authorized.
    """

    async def _permission_dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        missing_permissions = [
            permission.value
            for permission in required_permissions
            if not has_permission(current_user.role, permission)
        ]

        if missing_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Insufficient permissions: "
                    + ", ".join(missing_permissions)
                ),
            )

        return current_user

    return _permission_dependency


async def get_current_workspace(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    """
    Resolve o workspace ativo do usuario autenticado.

    Args:
        current_user: Usuario autenticado.
        db: Database session.

    Returns:
        Workspace ativo do usuario.

    Raises:
        HTTPException 400: Se usuario nao tem workspace ativo.
    """
    if not current_user.active_workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum workspace ativo. Crie ou selecione um workspace.",
        )

    stmt = select(Workspace).where(Workspace.id == current_user.active_workspace_id)
    result = await db.execute(stmt)
    workspace = result.scalar_one_or_none()

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace ativo nao encontrado.",
        )

    # Verificar que usuario e membro do workspace
    member_stmt = select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace.id,
        WorkspaceMember.user_id == current_user.id,
    )
    member_result = await db.execute(member_stmt)
    if member_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Voce nao e membro deste workspace.",
        )

    return workspace


def require_roles(*allowed_roles: UserRole) -> Callable[..., User]:
    """
    Build dependency that allows access only for specific roles.

    Args:
        allowed_roles: Roles accepted for endpoint access.

    Returns:
        FastAPI dependency that yields authenticated user if role is allowed.
    """

    normalized_allowed_roles = {role for role in allowed_roles}

    async def _role_dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        current_role = normalize_role(current_user.role)
        if current_role not in normalized_allowed_roles:
            allowed_roles_str = ", ".join(role.value for role in allowed_roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role. Allowed roles: {allowed_roles_str}",
            )

        return current_user

    return _role_dependency
