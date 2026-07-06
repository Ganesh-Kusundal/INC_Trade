"""In-memory cache implementation — thread-safe, TTL-based, LRU-eviction."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class _CacheEntry:
    """Internal cache entry with TTL tracking."""

    __slots__ = ("created_at", "expires_at", "value")

    def __init__(self, value: Any, ttl_seconds: float | None = None) -> None:
        self.value = value
        self.created_at = time.monotonic()
        if ttl_seconds is not None:
            self.expires_at = self.created_at + ttl_seconds
        else:
            self.expires_at = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.monotonic() > self.expires_at

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.created_at


class MemoryCache:
    """Thread-safe in-memory cache with TTL expiration and LRU eviction.

    Args:
        max_entries: Maximum number of entries before LRU eviction.
            Defaults to 10,000.
        default_ttl_seconds: Default TTL for entries that don't specify one.
            None means no expiration by default.
    """

    def __init__(
        self,
        max_entries: int = 10_000,
        default_ttl_seconds: float | None = None,
    ) -> None:
        self._max_entries = max_entries
        self._default_ttl = default_ttl_seconds
        self._lock = threading.RLock()
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()

    def get(self, key: str) -> Any | None:
        """Retrieve a value from cache.

        Args:
            key: Cache key.

        Returns:
            Cached value if found and not expired, None otherwise.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.is_expired:
                del self._store[key]
                return None
            # Move to end (most recently used) for LRU tracking
            self._store.move_to_end(key)
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: float | None = None,
    ) -> None:
        """Store a value in cache with optional TTL.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl_seconds: Time-to-live in seconds. None = use default.
        """
        with self._lock:
            ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
            self._store[key] = _CacheEntry(value, ttl)
            self._store.move_to_end(key)
            self._evict_if_needed()

    def delete(self, key: str) -> bool:
        """Remove a value from cache.

        Args:
            key: Cache key.

        Returns:
            True if the key existed and was deleted, False otherwise.
        """
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._store.clear()

    def get_stale(self, key: str, max_age_seconds: float) -> tuple[Any, bool]:
        """Get a value even if stale, with staleness indicator.

        Implements the stale-while-revalidate pattern.

        Args:
            key: Cache key.
            max_age_seconds: Maximum age before value is considered stale.

        Returns:
            Tuple of (value, is_stale). Value may be None if not in cache.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None, False
            if entry.is_expired:
                del self._store[key]
                return None, False
            is_stale = entry.age_seconds > max_age_seconds
            self._store.move_to_end(key)
            return entry.value, is_stale

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Retrieve multiple values at once.

        Args:
            keys: List of cache keys.

        Returns:
            Dict of key->value for found entries. Missing keys are omitted.
        """
        with self._lock:
            result: dict[str, Any] = {}
            for key in keys:
                entry = self._store.get(key)
                if entry is not None and not entry.is_expired:
                    result[key] = entry.value
                    self._store.move_to_end(key)
                elif entry is not None and entry.is_expired:
                    del self._store[key]
            return result

    def set_many(self, items: dict[str, Any], ttl_seconds: float | None = None) -> None:
        """Store multiple values at once.

        Args:
            items: Dict of key->value pairs to cache.
            ttl_seconds: Time-to-live in seconds. None = use default.
        """
        with self._lock:
            ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
            for key, value in items.items():
                self._store[key] = _CacheEntry(value, ttl)
                self._store.move_to_end(key)
            self._evict_if_needed()

    @property
    def size(self) -> int:
        """Current number of entries in cache."""
        with self._lock:
            return len(self._store)

    def _evict_if_needed(self) -> None:
        """Evict oldest entries if over max_entries (LRU)."""
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)  # Remove oldest (first)
