"""
Redis-backed rate limiter for sensitive endpoints (auth, etc).
Uses sliding window counter pattern.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

# Defaults
AUTH_RATE_LIMIT = getattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 10)
AUTH_RATE_WINDOW = 60  # seconds


async def check_rate_limit(
    request: Request,
    *,
    prefix: str = "rl:auth",
    limit: int = AUTH_RATE_LIMIT,
    window: int = AUTH_RATE_WINDOW,
) -> None:
    """
    Check rate limit for the request IP. Raises 429 if exceeded.

    Args:
        request: FastAPI request (used for client IP).
        prefix: Redis key prefix for this limiter.
        limit: Max requests per window.
        window: Window size in seconds.

    Raises:
        HTTPException: 429 Too Many Requests.
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"{prefix}:{client_ip}"

    try:
        redis: Redis = get_redis_client()
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, window)

        if current > limit:
            ttl = await redis.ttl(key)
            logger.warning("rate_limit_exceeded ip=%s key=%s count=%d limit=%d", client_ip, key, current, limit)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas tentativas. Tente novamente em breve.",
                headers={"Retry-After": str(max(ttl, 1))},
            )
    except HTTPException:
        raise
    except Exception:
        # Se Redis falhar, nao bloquear o request (fail-open)
        logger.exception("rate_limit redis error, allowing request")
