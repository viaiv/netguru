"""
Topology API — read generated topologies with ownership control.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Optional

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_workspace
from app.models.topology import Topology
from app.models.user import User
from app.models.workspace import Workspace

router = APIRouter()


class TopologyResponse(BaseModel):
    """Public topology response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    conversation_id: Optional[UUID] = None
    message_id: Optional[UUID] = None
    title: str
    source_type: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    summary: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: str


class TopologyListItem(BaseModel):
    """Compact topology list item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    source_type: str
    summary: Optional[str] = None
    created_at: str


@router.get("/{topology_id}", response_model=TopologyResponse)
async def get_topology(
    topology_id: UUID,
    current_user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> TopologyResponse:
    """Get a topology by ID (workspace-scoped)."""
    stmt = select(Topology).where(
        Topology.id == topology_id,
        Topology.workspace_id == workspace.id,
    )
    result = await db.execute(stmt)
    topo = result.scalar_one_or_none()

    if not topo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topologia nao encontrada.",
        )

    return TopologyResponse(
        id=topo.id,
        user_id=topo.user_id,
        conversation_id=topo.conversation_id,
        message_id=topo.message_id,
        title=topo.title,
        source_type=topo.source_type,
        nodes=topo.nodes,
        edges=topo.edges,
        summary=topo.summary,
        metadata=topo.topology_metadata,
        created_at=topo.created_at.isoformat(),
    )


@router.get("", response_model=list[TopologyListItem])
async def list_topologies(
    current_user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[TopologyListItem]:
    """List all topologies within the workspace."""
    stmt = (
        select(Topology)
        .where(Topology.workspace_id == workspace.id)
        .order_by(Topology.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    topologies = result.scalars().all()

    return [
        TopologyListItem(
            id=t.id,
            title=t.title,
            source_type=t.source_type,
            summary=t.summary,
            created_at=t.created_at.isoformat(),
        )
        for t in topologies
    ]
