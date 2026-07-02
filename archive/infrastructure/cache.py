"""Single caching abstraction for TradeXV2.

Provides a unified cache interface with multiple backends (memory, Redis, file).
Supports TTL, cache invalidation, and decorators.

Usage:
    from infrastructure.cache import Cache, memory_cache

    # Use default memory cache
    cache = memory_cache
    cache.set("key", {"data": 123}, ttl=300)
    value = cache.get("key")
"""

from __future__ import annotations

import functools
import json
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

from infrastructure.metrics.registry import metrics_registry

_cache_hits = metrics_registry.counter("cache_hits_total", "Total cache hits")
_cache_misses = metrics_registry.counter("cache_misses_total", "Total cache misses")
_cache_evictions = metrics_registry.counter("cache_evictions_total", "Total cache evictions")
_cache_size = metrics_registry.gauge("cache_size", "Current number of entries in cache")


class Cache(ABC):
    """Abstract cache interface."""

    @abstractmethod
    def get(self, key: str) -> Any | None:
        ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...

    @abstractmethod
    def has(self, key: str) -> bool:
        ...


class MemoryCache(Cache):
    """Thread-safe in-memory cache implementation.

    P1-4 fix: Added maxsize to prevent unbounded memory growth. When the
    cache exceeds maxsize entries, the oldest expired entries are evicted.
    If no expired entries exist, the oldest entries are removed.
    """

    def __init__(self, default_ttl: int = 300, maxsize: int = 10_000) -> None:
        self._default_ttl = default_ttl
        self._maxsize = maxsize
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.RLock()
        # Track insertion order for correct LRU eviction
        self._insertion_counter: int = 0
        self._insertion_order: dict[str, int] = {}

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key not in self._store:
                _cache_misses.inc()
                return None
            value, expires_at = self._store[key]
            if expires_at and time.monotonic() > expires_at:
                del self._store[key]
                _cache_evictions.inc()
                _cache_size.set(len(self._store))
                _cache_misses.inc()
                return None
            _cache_hits.inc()
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            ttl_seconds = ttl if ttl is not None else self._default_ttl
            expires_at = time.monotonic() + ttl_seconds if ttl_seconds > 0 else 0
            self._store[key] = (value, expires_at)
            self._insertion_order[key] = self._insertion_counter
            self._insertion_counter += 1
            _cache_size.set(len(self._store))
            # P1-4: Evict expired entries when cache exceeds maxsize
            if len(self._store) > self._maxsize:
                self._evict_expired()
            # If still over limit after expired eviction, remove oldest entries
            if len(self._store) > self._maxsize:
                self._evict_oldest()

    def _evict_expired(self) -> None:
        """Remove all expired entries. Must be called with lock held."""
        now = time.monotonic()
        expired_keys = [
            k for k, (_, expires_at) in self._store.items()
            if expires_at and now > expires_at
        ]
        for k in expired_keys:
            del self._store[k]
            _cache_evictions.inc()
        _cache_size.set(len(self._store))

    def _evict_oldest(self) -> None:
        """Remove oldest entries (by insertion time) to bring cache under maxsize.

        Must be called with lock held.
        """
        # Sort by insertion order (oldest first), not by expiration time
        sorted_keys = sorted(
            self._store.keys(),
            key=lambda k: self._insertion_order.get(k, 0),
        )
        to_remove = len(self._store) - self._maxsize
        for k in sorted_keys[:to_remove]:
            del self._store[k]
            self._insertion_order.pop(k, None)
            _cache_evictions.inc()
        _cache_size.set(len(self._store))

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)
            self._insertion_order.pop(key, None)
            _cache_size.set(len(self._store))

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._insertion_order.clear()
            _cache_size.set(0)

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {k: v[0] for k, v in self._store.items()}


def cached(cache: Cache | None = None, ttl: int = 300) -> Callable[[F], F]:
    """Decorator to cache function results."""
    cache_instance = cache or memory_cache

    def decorator(func: F) -> F:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = f"{func.__name__}:{json.dumps(args)}:{json.dumps(kwargs)}"
            result = cache_instance.get(key)
            if result is not None:
                return result
            result = func(*args, **kwargs)
            cache_instance.set(key, result, ttl=ttl)
            return result
        return wrapper  # type: ignore
    return decorator


def async_cached(cache: Cache | None = None, ttl: int = 300) -> Callable[[F], F]:
    """Decorator to cache async function results."""
    cache_instance = cache or memory_cache

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = f"{func.__name__}:{json.dumps(args)}:{json.dumps(kwargs)}"
            result = cache_instance.get(key)
            if result is not None:
                return result
            result = await func(*args, **kwargs)
            cache_instance.set(key, result, ttl=ttl)
            return result
        return wrapper  # type: ignore
    return decorator


memory_cache = MemoryCache()


def create_cache() -> Cache:
    """Pick Redis or Memory cache based on environment.

    Returns :class:`RedisCache` when ``REDIS_URL`` is set **and** the
    ``redis`` package is installed; otherwise returns :class:`MemoryCache`.
    """
    from infrastructure.cache_redis import get_redis_cache

    return get_redis_cache()
