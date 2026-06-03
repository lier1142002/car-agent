"""滑动窗口限流 — 基于 Redis Sorted Set."""

from __future__ import annotations

import time
import uuid
import logging
from typing import Optional

import redis.asyncio as redis

from config import config

logger = logging.getLogger(__name__)


class RateLimiter:
    """Redis 滑动窗口限流器."""

    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client
        self._window = config.rate_limit_window_seconds

    async def check_and_increment(
        self,
        api_key: str,
        endpoint: str,
        max_rps: int = 100,
    ) -> bool:
        """检查是否允许通过. 返回 True = 允许, False = 限流."""
        key = f"ratelimit:{api_key}:{endpoint}"
        now_ms = int(time.time() * 1000)
        window_start = now_ms - self._window * 1000

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            results = await pipe.execute()

        current_count: int = results[1]  # type: ignore[index]
        if current_count >= max_rps:
            logger.warning("限流触发: key=%s count=%d max=%d", key, current_count, max_rps)
            return False

        await self._redis.zadd(key, {str(uuid.uuid4()): now_ms})
        await self._redis.expire(key, self._window * 2)
        return True
