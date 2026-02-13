"""
Usage tracking service — daily metric upserts and limit checks.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_metric import UsageMetric


class UsageTrackingService:
    """
    Tracks daily usage per user via upsert (INSERT ON CONFLICT UPDATE).
    """

    @staticmethod
    async def increment_uploads(
        db: AsyncSession, user_id: UUID, count: int = 1,
    ) -> None:
        """Increment daily upload count for a user."""
        await UsageTrackingService._upsert_increment(
            db, user_id, "uploads_count", count,
        )

    @staticmethod
    async def increment_messages(
        db: AsyncSession, user_id: UUID, count: int = 1,
    ) -> None:
        """Increment daily message count for a user."""
        await UsageTrackingService._upsert_increment(
            db, user_id, "messages_count", count,
        )

    @staticmethod
    async def increment_tokens(
        db: AsyncSession, user_id: UUID, count: int = 0,
    ) -> None:
        """Increment daily tokens used for a user."""
        if count <= 0:
            return
        await UsageTrackingService._upsert_increment(
            db, user_id, "tokens_used", count,
        )

    @staticmethod
    async def _upsert_increment(
        db: AsyncSession,
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
            user_id=user_id,
            metric_date=today,
            **{column_name: increment},
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_usage_user_date",
            set_={column_name: col + increment},
        )
        await db.execute(stmt)
        await db.flush()

    @staticmethod
    async def get_today_usage(
        db: AsyncSession, user_id: UUID,
    ) -> Optional[UsageMetric]:
        """Return today's usage row for a user, or None."""
        stmt = select(UsageMetric).where(
            UsageMetric.user_id == user_id,
            UsageMetric.metric_date == date.today(),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def check_limit(
        db: AsyncSession,
        user_id: UUID,
        metric: str,
        limit_value: int,
    ) -> bool:
        """
        Check if user is within daily limit for the given metric.

        Args:
            metric: One of "uploads_count", "messages_count", "tokens_used".
            limit_value: Maximum allowed value.

        Returns:
            True if within limit, False if exceeded.
        """
        usage = await UsageTrackingService.get_today_usage(db, user_id)
        if usage is None:
            return True
        current = getattr(usage, metric, 0)
        return current < limit_value

    @staticmethod
    async def get_usage_range(
        db: AsyncSession,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[UsageMetric]:
        """Return usage rows for a user within a date range."""
        stmt = (
            select(UsageMetric)
            .where(
                UsageMetric.user_id == user_id,
                UsageMetric.metric_date >= start_date,
                UsageMetric.metric_date <= end_date,
            )
            .order_by(UsageMetric.metric_date)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
