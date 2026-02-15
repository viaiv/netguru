"""
Usage tracking service — daily metric upserts and limit checks.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_metric import UsageMetric


class UsageTrackingService:
    """
    Tracks daily usage per (workspace, user) via upsert (INSERT ON CONFLICT UPDATE).
    """

    @staticmethod
    async def increment_uploads(
        db: AsyncSession, workspace_id: UUID, user_id: UUID, count: int = 1,
    ) -> None:
        """Increment daily upload count for a user within a workspace."""
        await UsageTrackingService._upsert_increment(
            db, workspace_id, user_id, "uploads_count", count,
        )

    @staticmethod
    async def increment_messages(
        db: AsyncSession, workspace_id: UUID, user_id: UUID, count: int = 1,
    ) -> None:
        """Increment daily message count for a user within a workspace."""
        await UsageTrackingService._upsert_increment(
            db, workspace_id, user_id, "messages_count", count,
        )

    @staticmethod
    async def increment_tokens(
        db: AsyncSession, workspace_id: UUID, user_id: UUID, count: int = 0,
    ) -> None:
        """Increment daily tokens used for a user within a workspace."""
        if count <= 0:
            return
        await UsageTrackingService._upsert_increment(
            db, workspace_id, user_id, "tokens_used", count,
        )

    @staticmethod
    async def _upsert_increment(
        db: AsyncSession,
        workspace_id: UUID,
        user_id: UUID,
        column_name: str,
        increment: int,
    ) -> None:
        """
        Atomic upsert: insert a new row or add to existing counter.
        Uses PostgreSQL INSERT ... ON CONFLICT DO UPDATE.
        """
        today = date.today()
        col = getattr(UsageMetric, column_name)

        stmt = pg_insert(UsageMetric).values(
            workspace_id=workspace_id,
            user_id=user_id,
            metric_date=today,
            **{column_name: increment},
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_usage_workspace_user_date",
            set_={column_name: col + increment},
        )
        await db.execute(stmt)
        await db.flush()

    @staticmethod
    async def get_today_usage(
        db: AsyncSession, workspace_id: UUID, user_id: UUID,
    ) -> Optional[UsageMetric]:
        """Return today's usage row for a user in a workspace, or None."""
        stmt = select(UsageMetric).where(
            UsageMetric.workspace_id == workspace_id,
            UsageMetric.user_id == user_id,
            UsageMetric.metric_date == date.today(),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_workspace_today_usage(
        db: AsyncSession, workspace_id: UUID,
    ) -> dict[str, int]:
        """
        Aggregate today's usage across all workspace members.

        Returns:
            Dict with uploads_total, messages_total, tokens_total.
        """
        today = date.today()
        stmt = select(
            func.coalesce(func.sum(UsageMetric.uploads_count), 0).label("uploads_total"),
            func.coalesce(func.sum(UsageMetric.messages_count), 0).label("messages_total"),
            func.coalesce(func.sum(UsageMetric.tokens_used), 0).label("tokens_total"),
        ).where(
            UsageMetric.workspace_id == workspace_id,
            UsageMetric.metric_date == today,
        )
        result = await db.execute(stmt)
        row = result.one()
        return {
            "uploads_total": int(row.uploads_total),
            "messages_total": int(row.messages_total),
            "tokens_total": int(row.tokens_total),
        }

    @staticmethod
    async def get_usage_range(
        db: AsyncSession,
        workspace_id: UUID,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[UsageMetric]:
        """Return usage rows for a user within a date range."""
        stmt = (
            select(UsageMetric)
            .where(
                UsageMetric.workspace_id == workspace_id,
                UsageMetric.user_id == user_id,
                UsageMetric.metric_date >= start_date,
                UsageMetric.metric_date <= end_date,
            )
            .order_by(UsageMetric.metric_date)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
