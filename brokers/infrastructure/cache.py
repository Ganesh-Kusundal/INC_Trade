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
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
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

    Uses ``OrderedDict`` for O(1) oldest-entry eviction.
    """

    def __init__(self, default_ttl: int = 300, maxsize: int = 10_000) -> None:
        self._default_ttl = default_ttl
        self._maxsize = maxsize
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
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
            # Move to end if key already exists
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, expires_at)
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

    def has(self, key: str) -> bool:
        """Return True if a non-expired entry exists for *key*.

        Unlike ``get()``, this does NOT treat a stored ``None`` as absent —
        a live entry whose value happens to be ``None`` still counts as
        present.
        """
        with self._lock:
            if key not in self._store:
                return False
            _, expires_at = self._store[key]
            if expires_at and time.monotonic() > expires_at:
                self._remove(key)
                return False
            return True

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

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if exp and now > exp]
        for k in expired:
            self._remove(k)

    def _evict_oldest(self) -> None:
        """Evict oldest entries using OrderedDict.popitem(last=False) — O(1)."""
        to_remove = len(self._store) - self._maxsize
        for _ in range(to_remove):
            if self._store:
                self._store.popitem(last=False)


def _build_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """Build a cache key using repr() — faster than json.dumps."""
    parts = [func_name]
    if args:
        parts.append(repr(args))
    if kwargs:
        parts.append(repr(tuple(sorted(kwargs.items()))))
    return ":".join(parts)


def cached(cache: Cache | None = None, ttl: int = 300) -> Callable[[F], F]:
    """Decorator to cache function results."""

    def decorator(func: F) -> F:
        cache_instance = cache or MemoryCache()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _build_cache_key(func.__name__, args, kwargs)
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
            key = _build_cache_key(func.__name__, args, kwargs)
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
