"""Redis cache backend for TradeXV2.

Uses ``redis.asyncio`` for non-blocking async I/O.  Falls back to
``MemoryCache`` when the ``redis`` package is not installed or when
the ``REDIS_URL`` environment variable is absent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from infrastructure.cache import (
    Cache,
    MemoryCache,
    _cache_evictions,
    _cache_hits,
    _cache_misses,
    _cache_size,
)

try:
    import redis.asyncio as aioredis  # type: ignore[import-untyped]

    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class RedisCache(Cache):
    """Async Redis-backed cache implementing the :class:`Cache` ABC.

    Parameters
    ----------
    url:
        Redis connection string (e.g. ``redis://localhost:6379``).
    default_ttl:
        Default time-to-live in seconds for entries without an explicit TTL.
    prefix:
        Key prefix to namespace TradeXV2 entries in Redis.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        default_ttl: int = 300,
        prefix: str = "tradexv2:",
    ) -> None:
        if not _REDIS_AVAILABLE:
            raise ImportError(
                "The 'redis' package is required for RedisCache. "
                "Install it with: pip install redis"
            )
        self._url = url
        self._default_ttl = default_ttl
        self._prefix = prefix
        self._pool: aioredis.ConnectionPool = aioredis.ConnectionPool.from_url(
            url, decode_responses=True
        )
        self._client: aioredis.Redis = aioredis.Redis(connection_pool=self._pool)
        self._lock = asyncio.Lock()

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    # ------------------------------------------------------------------
    # Synchronous Cache ABC stubs (bridge to async)
    #
    # The Cache ABC declares sync signatures.  For Redis we need async I/O.
    # We run the async operations in a new event-loop thread when called
    # synchronously, and provide ``aget``/``aset``/``adelete``/``aclear``/``ahas``
    # for callers that can ``await``.
    # ------------------------------------------------------------------

    def _run_sync(self, coro):  # type: ignore[no-untyped-def]
        """Execute an async coroutine from sync context."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're already inside a running loop – spin up a thread.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=30)
        else:
            return asyncio.run(coro)

    # ------------------------------------------------------------------
    # Async public API
    # ------------------------------------------------------------------

    async def aget(self, key: str) -> Any | None:
        raw = await self._client.get(self._key(key))
        if raw is None:
            _cache_misses.inc()
            return None
        _cache_hits.inc()
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def aset(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl_seconds = ttl if ttl is not None else self._default_ttl
        try:
            payload = json.dumps(value)
        except (TypeError, ValueError):
            payload = str(value)
        if ttl_seconds and ttl_seconds > 0:
            await self._client.set(self._key(key), payload, ex=ttl_seconds)
        else:
            await self._client.set(self._key(key), payload)

    async def adelete(self, key: str) -> None:
        await self._client.delete(self._key(key))

    async def aclear(self) -> None:
        async with self._lock:
            keys = []
            async for k in self._client.scan_iter(f"{self._prefix}*"):
                keys.append(k)
            if keys:
                await self._client.delete(*keys)
                _cache_evictions.inc(len(keys))
                _cache_size.set(0)

    async def ahas(self, key: str) -> bool:
        return await self._client.exists(self._key(key)) > 0

    # ------------------------------------------------------------------
    # Sync Cache ABC implementation (delegates to async)
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any | None:
        return self._run_sync(self.aget(key))

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self._run_sync(self.aset(key, value, ttl))

    def delete(self, key: str) -> None:
        self._run_sync(self.adelete(key))

    def clear(self) -> None:
        self._run_sync(self.aclear())

    def has(self, key: str) -> bool:
        return self._run_sync(self.ahas(key))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        await self._client.aclose()

    def close(self) -> None:
        self._run_sync(self.aclose())


def get_redis_cache() -> Cache:  # type: ignore[return]
    """Factory that returns a :class:`RedisCache` if possible, else :class:`MemoryCache`.

    Checks ``REDIS_URL`` env var and ``redis`` package availability.
    """
    redis_url = os.environ.get("REDIS_URL")
    if redis_url and _REDIS_AVAILABLE:
        logger.info("Using Redis cache at %s", redis_url)
        return RedisCache(url=redis_url)
    logger.info("Redis not available; falling back to MemoryCache")
    return MemoryCache()
