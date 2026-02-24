from __future__ import annotations

import logging
from collections import defaultdict
from time import time

from app.config import settings

try:
    import redis.asyncio as redis_asyncio
except Exception:  # pragma: no cover - optional dependency fallback
    redis_asyncio = None

logger = logging.getLogger(__name__)


class LoginRateLimiter:
    """Login limiter with Redis-backed counters and local-memory fallback."""

    def __init__(
        self,
        *,
        window_seconds: int,
        max_attempts: int,
        redis_url: str = "",
        redis_error_cooldown_seconds: int = 30,
    ) -> None:
        self.window_seconds = max(1, int(window_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self.redis_error_cooldown_seconds = max(1, int(redis_error_cooldown_seconds))
        self._local_attempts: dict[str, list[float]] = defaultdict(list)
        self._redis_error_until = 0.0
        self._last_local_cleanup = 0.0
        self._redis = None

        if redis_url:
            if redis_asyncio is None:
                logger.warning(
                    "REDIS_URL is set but redis package is unavailable. Falling back to local memory rate limit.",
                )
            else:
                self._redis = redis_asyncio.from_url(
                    redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                )

    async def should_block(self, identity: str) -> bool:
        if self._redis and time() >= self._redis_error_until:
            try:
                return await self._should_block_redis(identity)
            except Exception as exc:  # pragma: no cover - runtime/network contingency
                self._redis_error_until = time() + self.redis_error_cooldown_seconds
                logger.warning(
                    "Redis rate limit unavailable, fallback to local memory for %ss: %s",
                    self.redis_error_cooldown_seconds,
                    exc,
                )
        return self._should_block_local(identity)

    async def add_failure(self, identity: str) -> None:
        if self._redis and time() >= self._redis_error_until:
            try:
                await self._add_failure_redis(identity)
                return
            except Exception as exc:  # pragma: no cover - runtime/network contingency
                self._redis_error_until = time() + self.redis_error_cooldown_seconds
                logger.warning(
                    "Redis rate limit unavailable, fallback to local memory for %ss: %s",
                    self.redis_error_cooldown_seconds,
                    exc,
                )
        self._add_failure_local(identity)

    async def reset(self, identity: str) -> None:
        if self._redis and time() >= self._redis_error_until:
            try:
                await self._reset_redis(identity)
            except Exception as exc:  # pragma: no cover - runtime/network contingency
                self._redis_error_until = time() + self.redis_error_cooldown_seconds
                logger.warning(
                    "Redis rate limit reset failed, fallback to local memory cleanup: %s",
                    exc,
                )
        self._reset_local(identity)

    def clear_local(self) -> None:
        self._local_attempts.clear()

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    def _redis_key(self, identity: str) -> str:
        bucket = int(time() // self.window_seconds)
        return f"rate_limit:login:{identity}:{bucket}"

    async def _should_block_redis(self, identity: str) -> bool:
        key = self._redis_key(identity)
        count = await self._redis.get(key)
        return int(count or 0) >= self.max_attempts

    async def _add_failure_redis(self, identity: str) -> None:
        key = self._redis_key(identity)
        attempts = await self._redis.incr(key)
        if attempts == 1:
            await self._redis.expire(key, self.window_seconds + 5)

    async def _reset_redis(self, identity: str) -> None:
        key = self._redis_key(identity)
        await self._redis.delete(key)

    def _should_block_local(self, identity: str) -> bool:
        now = time()
        self._local_maybe_cleanup(now)
        attempts = self._prune_local_identity(identity, now)
        return len(attempts) >= self.max_attempts

    def _add_failure_local(self, identity: str) -> None:
        now = time()
        self._local_maybe_cleanup(now)
        attempts = self._prune_local_identity(identity, now)
        attempts.append(now)
        self._local_attempts[identity] = attempts

    def _reset_local(self, identity: str) -> None:
        self._local_attempts.pop(identity, None)

    def _prune_local_identity(self, identity: str, now: float) -> list[float]:
        attempts = self._local_attempts.get(identity, [])
        attempts = [ts for ts in attempts if now - ts < self.window_seconds]
        if attempts:
            self._local_attempts[identity] = attempts
        else:
            self._local_attempts.pop(identity, None)
        return attempts

    def _local_maybe_cleanup(self, now: float) -> None:
        if now - self._last_local_cleanup < self.window_seconds:
            return
        self._last_local_cleanup = now
        for identity in list(self._local_attempts.keys()):
            self._prune_local_identity(identity, now)


login_rate_limiter = LoginRateLimiter(
    window_seconds=settings.login_rate_window_seconds,
    max_attempts=settings.login_rate_max_attempts,
    redis_url=settings.redis_url,
)
