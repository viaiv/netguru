"""
Pydantic schemas for Workspace API.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class WorkspaceCreate(BaseModel):
    """Schema para criacao de workspace."""

    name: str = Field(..., min_length=1, max_length=255)


class WorkspaceUpdate(BaseModel):
    """Schema para atualizacao de workspace."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)


class WorkspaceResponse(BaseModel):
    """Schema para workspace em responses."""

    id: UUID
    name: str
    slug: str
    owner_id: UUID
    plan_tier: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceMemberResponse(BaseModel):
    """Schema para membro de workspace em responses."""

    id: UUID
    workspace_id: UUID
    user_id: UUID
    email: str
    full_name: Optional[str] = None
    workspace_role: str
    joined_at: datetime

    class Config:
        from_attributes = True


class WorkspaceInviteRequest(BaseModel):
    """Schema para convite de membro ao workspace."""

    email: EmailStr
    workspace_role: str = Field(
        default="member",
        pattern="^(admin|member|viewer)$",
        description="admin|member|viewer (owner nao pode ser atribuido via convite)",
    )


class WorkspaceMemberRoleUpdate(BaseModel):
    """Schema para atualizacao de role de membro."""

    workspace_role: str = Field(
        ...,
        pattern="^(admin|member|viewer)$",
        description="admin|member|viewer",
    )


class WorkspaceDetailResponse(WorkspaceResponse):
    """Schema com detalhes do workspace incluindo membros."""

    members: list[WorkspaceMemberResponse] = []
    member_count: int = 0
