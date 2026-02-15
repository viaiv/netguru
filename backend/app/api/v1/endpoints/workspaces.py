"""
Workspace CRUD and member management endpoints.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_workspace
from app.core.rbac import (
    WorkspacePermission,
    has_workspace_permission,
    normalize_workspace_role,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceDetailResponse,
    WorkspaceInviteRequest,
    WorkspaceMemberResponse,
    WorkspaceMemberRoleUpdate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services.workspace_service import WorkspaceService

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_workspace_permission(
    workspace: Workspace,
    user: User,
    permission: WorkspacePermission,
    db: AsyncSession,
) -> None:
    """Raise 403 if user lacks the workspace-level permission."""
    svc = WorkspaceService(db)
    member = await svc.get_workspace_member(workspace.id, user.id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Voce nao e membro deste workspace.",
        )
    role = normalize_workspace_role(member.workspace_role)
    if not has_workspace_permission(role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permissao insuficiente: {permission.value}",
        )


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceResponse]:
    """Lista workspaces onde o usuario e membro."""
    svc = WorkspaceService(db)
    workspaces = await svc.get_user_workspaces(current_user.id)
    return [WorkspaceResponse.model_validate(ws) for ws in workspaces]


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Cria novo workspace com o usuario como owner."""
    svc = WorkspaceService(db)
    workspace = await svc.create_workspace(owner=current_user, name=payload.name)
    await db.commit()
    await db.refresh(workspace)
    return WorkspaceResponse.model_validate(workspace)


@router.get("/{workspace_id}", response_model=WorkspaceDetailResponse)
async def get_workspace_detail(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceDetailResponse:
    """Retorna detalhes do workspace com lista de membros."""
    svc = WorkspaceService(db)

    # Verificar membership
    member = await svc.get_workspace_member(workspace_id, current_user.id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace nao encontrado.",
        )

    workspace = await svc.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace nao encontrado.",
        )

    members_data = await svc.get_workspace_members_with_users(workspace_id)
    members = [WorkspaceMemberResponse(**m) for m in members_data]

    return WorkspaceDetailResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        owner_id=workspace.owner_id,
        plan_tier=workspace.plan_tier,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        members=members,
        member_count=len(members),
    )


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    payload: WorkspaceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Atualiza nome do workspace (requer permissao workspace:update)."""
    svc = WorkspaceService(db)
    workspace = await svc.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace nao encontrado.",
        )

    await _require_workspace_permission(
        workspace, current_user, WorkspacePermission.WORKSPACE_UPDATE, db,
    )

    if payload.name is not None:
        workspace.name = payload.name

    await db.commit()
    await db.refresh(workspace)
    return WorkspaceResponse.model_validate(workspace)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    workspace_id: UUID,
    payload: WorkspaceInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMemberResponse:
    """Convida usuario existente para o workspace."""
    svc = WorkspaceService(db)
    workspace = await svc.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace nao encontrado.",
        )

    await _require_workspace_permission(
        workspace, current_user, WorkspacePermission.WORKSPACE_MEMBERS_MANAGE, db,
    )

    try:
        member = await svc.invite_member(
            workspace_id=workspace_id,
            email=payload.email,
            workspace_role=payload.workspace_role,
            invited_by=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await db.commit()

    # Recarregar dados completos do membro
    members_data = await svc.get_workspace_members_with_users(workspace_id)
    for m in members_data:
        if m["user_id"] == member.user_id:
            return WorkspaceMemberResponse(**m)

    # Fallback (shouldn't happen)
    return WorkspaceMemberResponse(
        id=member.id,
        workspace_id=member.workspace_id,
        user_id=member.user_id,
        email=payload.email,
        workspace_role=member.workspace_role,
        joined_at=member.joined_at,
    )


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    workspace_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove membro do workspace."""
    svc = WorkspaceService(db)
    workspace = await svc.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace nao encontrado.",
        )

    await _require_workspace_permission(
        workspace, current_user, WorkspacePermission.WORKSPACE_MEMBERS_MANAGE, db,
    )

    try:
        await svc.remove_member(workspace_id, user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await db.commit()


@router.patch(
    "/{workspace_id}/members/{user_id}/role",
    response_model=WorkspaceMemberResponse,
)
async def update_member_role(
    workspace_id: UUID,
    user_id: UUID,
    payload: WorkspaceMemberRoleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMemberResponse:
    """Altera role de um membro do workspace."""
    svc = WorkspaceService(db)
    workspace = await svc.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace nao encontrado.",
        )

    await _require_workspace_permission(
        workspace, current_user, WorkspacePermission.WORKSPACE_MEMBERS_MANAGE, db,
    )

    try:
        await svc.update_member_role(workspace_id, user_id, payload.workspace_role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await db.commit()

    members_data = await svc.get_workspace_members_with_users(workspace_id)
    for m in members_data:
        if m["user_id"] == user_id:
            return WorkspaceMemberResponse(**m)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Membro nao encontrado.",
    )


@router.post("/{workspace_id}/transfer-ownership", response_model=WorkspaceResponse)
async def transfer_ownership(
    workspace_id: UUID,
    new_owner_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Transfere ownership do workspace para outro membro."""
    svc = WorkspaceService(db)

    try:
        await svc.transfer_ownership(workspace_id, current_user.id, new_owner_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await db.commit()

    workspace = await svc.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace nao encontrado.",
        )
    return WorkspaceResponse.model_validate(workspace)


@router.post("/switch/{workspace_id}", response_model=WorkspaceResponse)
async def switch_workspace(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Troca workspace ativo do usuario."""
    svc = WorkspaceService(db)

    try:
        workspace = await svc.switch_workspace(current_user, workspace_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await db.commit()
    return WorkspaceResponse.model_validate(workspace)
