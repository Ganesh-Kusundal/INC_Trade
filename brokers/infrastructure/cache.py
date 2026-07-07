"""Caching abstraction — ABC, in-memory implementation, and @cached decorator.

Zero external dependencies. Thread-safe with TTL and maxsize eviction.

Usage::

    from brokers.infrastructure.cache import MemoryCache, cached

    cache = MemoryCache(default_ttl=300, maxsize=10_000)
    cache.set("key", {"data": 123}, ttl=60)
    value = cache.get("key")

    @cached(ttl=60)
    def get_quote(symbol: str) -> dict:
        ...
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


class Cache(ABC):
    """Abstract cache interface."""

    @abstractmethod
    def get(self, key: str) -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def has(self, key: str) -> bool: ...


class MemoryCache(Cache):
    """Thread-safe in-memory cache with TTL and maxsize eviction.

    When the cache exceeds *maxsize* entries, expired entries are evicted
    first, then oldest entries are removed.
    """

    def __init__(self, default_ttl: int = 300, maxsize: int = 10_000) -> None:
        self._default_ttl = default_ttl
        self._maxsize = maxsize
        self._store: dict[str, tuple[Any, float]] = {}
        self._insertion_order: dict[str, int] = {}
        self._counter: int = 0
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key not in self._store:
                return None
            value, expires_at = self._store[key]
            if expires_at and time.monotonic() > expires_at:
                self._remove(key)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            ttl_seconds = ttl if ttl is not None else self._default_ttl
            expires_at = time.monotonic() + ttl_seconds if ttl_seconds > 0 else 0
            self._store[key] = (value, expires_at)
            self._insertion_order[key] = self._counter
            self._counter += 1
            if len(self._store) > self._maxsize:
                self._evict_expired()
            if len(self._store) > self._maxsize:
                self._evict_oldest()

    def delete(self, key: str) -> None:
        with self._lock:
            self._remove(key)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._insertion_order.clear()

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of all non-expired entries."""
        with self._lock:
            now = time.monotonic()
            return {
                k: v
                for k, (v, expires_at) in self._store.items()
                if not expires_at or now <= expires_at
            }

    def _remove(self, key: str) -> None:
        self._store.pop(key, None)
        self._insertion_order.pop(key, None)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if exp and now > exp]
        for k in expired:
            self._remove(k)

    def _evict_oldest(self) -> None:
        sorted_keys = sorted(
            self._store.keys(), key=lambda k: self._insertion_order.get(k, 0)
        )
        to_remove = len(self._store) - self._maxsize
        for k in sorted_keys[:to_remove]:
            self._remove(k)


def cached(cache: Cache | None = None, ttl: int = 300) -> Callable[[F], F]:
    """Decorator to cache function results."""

    def decorator(func: F) -> F:
        cache_instance = cache or MemoryCache()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = f"{func.__name__}:{json.dumps(args, default=str)}:{json.dumps(kwargs, default=str)}"
            result = cache_instance.get(key)
            if result is not None:
                return result
            result = func(*args, **kwargs)
            cache_instance.set(key, result, ttl=ttl)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def async_cached(cache: Cache | None = None, ttl: int = 300) -> Callable[[F], F]:
    """Decorator to cache async function results."""

    def decorator(func: F) -> F:
        cache_instance = cache or MemoryCache()

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = f"{func.__name__}:{json.dumps(args, default=str)}:{json.dumps(kwargs, default=str)}"
            result = cache_instance.get(key)
            if result is not None:
                return result
            result = await func(*args, **kwargs)
            cache_instance.set(key, result, ttl=ttl)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


# Module-level default cache
memory_cache = MemoryCache()


__all__ = [
    "Cache",
    "MemoryCache",
    "async_cached",
    "cached",
    "memory_cache",
]
