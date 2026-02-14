"""
Persistent memory endpoints for user-scoped network context.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permissions
from app.core.rbac import Permission
from app.models.user import User
from app.schemas.memory import MemoryCreate, MemoryResponse, MemoryScope, MemoryUpdate
from app.services.audit_log_service import AuditLogService
from app.services.memory_service import MemoryService, MemoryServiceError

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    """
    Resolve client IP preferring common proxy headers.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    xrip = request.headers.get("x-real-ip")
    if xrip:
        return xrip.strip()
    if request.client:
        return request.client.host
    return None


def _raise_memory_http_error(exc: MemoryServiceError) -> None:
    """
    Convert domain error to HTTP response.
    """
    status_code = status.HTTP_400_BAD_REQUEST
    if exc.code == "memory_not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == "memory_conflict":
        status_code = status.HTTP_409_CONFLICT
    elif exc.code == "memory_schema_missing":
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    raise HTTPException(status_code=status_code, detail=exc.detail) from exc


@router.get("", response_model=list[MemoryResponse])
async def list_memories(
    scope: MemoryScope | None = Query(default=None),
    scope_name: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    current_user: User = Depends(require_permissions(Permission.USERS_READ_SELF)),
    db: AsyncSession = Depends(get_db),
) -> list[MemoryResponse]:
    """
    List memories from current user with optional filters.
    """
    service = MemoryService(db)
    memories = await service.list_memories(
        user_id=current_user.id,
        scope=scope,
        scope_name=scope_name,
        include_inactive=include_inactive,
    )
    return [MemoryResponse.model_validate(memory) for memory in memories]


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    payload: MemoryCreate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    """
    Create a persistent memory entry.
    """
    service = MemoryService(db)
    try:
        memory = await service.create_memory(user_id=current_user.id, payload=payload)
    except MemoryServiceError as exc:
        _raise_memory_http_error(exc)

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="memory.created",
        target_type="network_memory",
        target_id=str(memory.id),
        changes=payload.model_dump(mode="json"),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    await db.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: UUID,
    payload: MemoryUpdate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    """
    Update a persistent memory entry.
    """
    service = MemoryService(db)
    existing = await service.get_memory(user_id=current_user.id, memory_id=memory_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memoria nao encontrada.")

    before: dict[str, Any] = {
        "scope": existing.scope,
        "scope_name": existing.scope_name,
        "memory_key": existing.memory_key,
        "memory_value": existing.memory_value,
        "tags": existing.tags,
        "ttl_seconds": existing.ttl_seconds,
        "expires_at": existing.expires_at.isoformat() if existing.expires_at else None,
        "version": existing.version,
    }

    try:
        memory = await service.update_memory(
            user_id=current_user.id,
            memory_id=memory_id,
            payload=payload,
        )
    except MemoryServiceError as exc:
        _raise_memory_http_error(exc)

    after: dict[str, Any] = {
        "scope": memory.scope,
        "scope_name": memory.scope_name,
        "memory_key": memory.memory_key,
        "memory_value": memory.memory_value,
        "tags": memory.tags,
        "ttl_seconds": memory.ttl_seconds,
        "expires_at": memory.expires_at.isoformat() if memory.expires_at else None,
        "version": memory.version,
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
            action="memory.updated",
            target_type="network_memory",
            target_id=str(memory.id),
            changes=changes,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )

    await db.commit()
    await db.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: UUID,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE_SELF)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Soft-delete a persistent memory entry.
    """
    service = MemoryService(db)
    try:
        memory = await service.delete_memory(
            user_id=current_user.id,
            memory_id=memory_id,
        )
    except MemoryServiceError as exc:
        _raise_memory_http_error(exc)

    await AuditLogService.record(
        db,
        actor_id=current_user.id,
        action="memory.deleted",
        target_type="network_memory",
        target_id=str(memory.id),
        changes={"is_active": {"from": True, "to": False}},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
