"""
AuditLog service — records admin actions in the same transaction.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.audit_log import AuditLog
from app.models.user import User


class AuditLogService:
    """
    Provides helpers to record and query audit entries.
    """

    @staticmethod
    async def record(
        db: AsyncSession,
        *,
        actor_id: Optional[UUID],
        action: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        changes: Optional[dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """
        Record an audit entry. Uses flush() so it participates
        in the caller's transaction.

        Args:
            db: Active database session.
            actor_id: User who performed the action.
            action: Machine-readable action name (e.g. "user.role_changed").
            target_type: Entity type ("user", "plan", etc.).
            target_id: UUID string of the target entity.
            changes: JSON diff of before/after values.
            ip_address: Client IP address.
            user_agent: Client user-agent string.

        Returns:
            Created AuditLog instance.
        """
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(entry)
        await db.flush()
        return entry

    @staticmethod
    async def list_logs(
        db: AsyncSession,
        *,
        page: int = 1,
        limit: int = 50,
        action: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        target_type: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Paginated audit log with optional filters.

        Returns:
            Tuple of (items as dicts with actor_email, total count).
        """
        filters = []
        if action:
            filters.append(AuditLog.action == action)
        if actor_id:
            filters.append(AuditLog.actor_id == actor_id)
        if target_type:
            filters.append(AuditLog.target_type == target_type)

        # Count
        count_stmt = select(func.count()).select_from(AuditLog).where(*filters) if filters else select(func.count()).select_from(AuditLog)
        count_result = await db.execute(count_stmt)
        total = int(count_result.scalar_one())

        # Query with actor email via outerjoin
        offset = (page - 1) * limit
        stmt = (
            select(AuditLog, User.email.label("actor_email"))
            .outerjoin(User, AuditLog.actor_id == User.id)
            .where(*filters)
            .order_by(desc(AuditLog.created_at))
            .offset(offset)
            .limit(limit)
        ) if filters else (
            select(AuditLog, User.email.label("actor_email"))
            .outerjoin(User, AuditLog.actor_id == User.id)
            .order_by(desc(AuditLog.created_at))
            .offset(offset)
            .limit(limit)
        )

        result = await db.execute(stmt)
        rows = result.all()

        items = []
        for row in rows:
            log = row[0]
            actor_email = row[1]
            items.append({
                "id": log.id,
                "actor_id": log.actor_id,
                "actor_email": actor_email,
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "changes": log.changes,
                "ip_address": log.ip_address,
                "created_at": log.created_at,
            })

        return items, total
