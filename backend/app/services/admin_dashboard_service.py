"""
Admin dashboard service — aggregated stats and system health checks.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.models.usage_metric import UsageMetric
from app.models.user import User

logger = logging.getLogger(__name__)

# Tracked since process start
_process_start = time.monotonic()


class AdminDashboardService:
    """
    Provides dashboard statistics and system health probes.
    """

    @staticmethod
    async def get_stats(db: AsyncSession) -> dict[str, Any]:
        """
        Return aggregated dashboard statistics.
        Uses asyncio.gather for parallel queries.
        """

        async def _total_users() -> int:
            r = await db.execute(select(func.count()).select_from(User))
            return int(r.scalar_one())

        async def _active_users() -> int:
            r = await db.execute(
                select(func.count()).select_from(User).where(User.is_active.is_(True))
            )
            return int(r.scalar_one())

        async def _total_conversations() -> int:
            r = await db.execute(select(func.count()).select_from(Conversation))
            return int(r.scalar_one())

        async def _total_messages() -> int:
            r = await db.execute(select(func.count()).select_from(Message))
            return int(r.scalar_one())

        async def _total_documents() -> int:
            r = await db.execute(select(func.count()).select_from(Document))
            return int(r.scalar_one())

        async def _users_by_plan() -> dict[str, int]:
            r = await db.execute(
                select(User.plan_tier, func.count())
                .group_by(User.plan_tier)
            )
            return {row[0]: row[1] for row in r.all()}

        async def _users_by_role() -> dict[str, int]:
            r = await db.execute(
                select(User.role, func.count())
                .group_by(User.role)
            )
            return {row[0]: row[1] for row in r.all()}

        async def _recent_signups() -> int:
            cutoff = datetime.utcnow() - timedelta(days=7)
            r = await db.execute(
                select(func.count())
                .select_from(User)
                .where(User.created_at >= cutoff)
            )
            return int(r.scalar_one())

        async def _messages_today() -> int:
            today = datetime.utcnow().date()
            r = await db.execute(
                select(func.coalesce(func.sum(UsageMetric.messages_count), 0))
                .where(UsageMetric.metric_date == today)
            )
            return int(r.scalar_one())

        (
            total_users,
            active_users,
            total_conversations,
            total_messages,
            total_documents,
            users_by_plan,
            users_by_role,
            recent_signups,
            messages_today,
        ) = await asyncio.gather(
            _total_users(),
            _active_users(),
            _total_conversations(),
            _total_messages(),
            _total_documents(),
            _users_by_plan(),
            _users_by_role(),
            _recent_signups(),
            _messages_today(),
        )

        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "total_documents": total_documents,
            "users_by_plan": users_by_plan,
            "users_by_role": users_by_role,
            "recent_signups_7d": recent_signups,
            "messages_today": messages_today,
        }

    @staticmethod
    async def get_system_health(db: AsyncSession) -> dict[str, Any]:
        """
        Probe database, Redis, and Celery for health status.
        """
        services = []

        # --- Database ---
        db_status = await _probe_database(db)
        services.append(db_status)

        # --- Redis ---
        redis_status = await _probe_redis()
        services.append(redis_status)

        # --- Celery ---
        celery_status = await _probe_celery()
        services.append(celery_status)

        # Overall
        statuses = [s["status"] for s in services]
        if all(s == "healthy" for s in statuses):
            overall = "healthy"
        elif any(s == "down" for s in statuses):
            overall = "down"
        else:
            overall = "degraded"

        return {
            "overall": overall,
            "services": services,
            "uptime_seconds": round(time.monotonic() - _process_start, 1),
        }


async def _probe_database(db: AsyncSession) -> dict[str, Any]:
    """Ping PostgreSQL."""
    try:
        start = time.monotonic()
        await db.execute(text("SELECT 1"))
        latency = round((time.monotonic() - start) * 1000, 1)
        return {"name": "PostgreSQL", "status": "healthy", "latency_ms": latency}
    except Exception as exc:
        logger.warning("DB health check failed: %s", exc)
        return {"name": "PostgreSQL", "status": "down", "details": str(exc)}


async def _probe_redis() -> dict[str, Any]:
    """Ping Redis."""
    try:
        import redis.asyncio as aioredis

        start = time.monotonic()
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pong = await r.ping()
        latency = round((time.monotonic() - start) * 1000, 1)
        await r.aclose()
        if pong:
            return {"name": "Redis", "status": "healthy", "latency_ms": latency}
        return {"name": "Redis", "status": "degraded", "details": "ping returned False"}
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return {"name": "Redis", "status": "down", "details": str(exc)}


async def _probe_celery() -> dict[str, Any]:
    """Inspect Celery for active workers."""
    try:
        from app.workers.celery_app import celery_app

        loop = asyncio.get_event_loop()
        inspector = celery_app.control.inspect(timeout=2.0)
        active = await loop.run_in_executor(None, inspector.active)
        if active:
            worker_count = len(active)
            return {
                "name": "Celery",
                "status": "healthy",
                "details": f"{worker_count} worker(s) active",
            }
        return {"name": "Celery", "status": "degraded", "details": "No active workers"}
    except Exception as exc:
        logger.warning("Celery health check failed: %s", exc)
        return {"name": "Celery", "status": "down", "details": str(exc)}
