"""
Redis client and helpers for authentication token workflows.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Optional

from redis.asyncio import Redis

from app.core.config import settings

_redis_client: Optional[Redis] = None


def get_redis_client() -> Redis:
    """
    Get or initialize a singleton async Redis client.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def get_redis() -> AsyncGenerator[Redis, None]:
    """
    Dependency that provides a Redis client.
    """
    yield get_redis_client()


async def close_redis_client() -> None:
    """
    Close Redis client during application shutdown.
    """
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
