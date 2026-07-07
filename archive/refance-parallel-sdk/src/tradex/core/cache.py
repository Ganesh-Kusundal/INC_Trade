"""Cache framework with TTL and LRU eviction.

Provides a generic async-safe cache used by providers
for security masters, instrument lookups, quotes, etc.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """Thread-safe TTL cache with LRU eviction.

    Uses OrderedDict for O(1) access and eviction.
    All operations are protected by an asyncio lock.
    """

    def __init__(self, max_size: int = 10000, default_ttl: float = 60.0) -> None:
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cache: OrderedDict[K, tuple[V, float]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: K, ttl: Optional[float] = None) -> Optional[V]:
        """Get a value from the cache. Returns None if missing or expired."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            value, expiry = entry
            if time.monotonic() > expiry:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    async def put(self, key: K, value: V, ttl: Optional[float] = None) -> None:
        """Put a value into the cache."""
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expiry = time.monotonic() + effective_ttl

        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, expiry)

            # Evict oldest entries if over capacity
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    async def invalidate(self, key: K) -> bool:
        """Remove a specific key. Returns True if it existed."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all entries."""
        async with self._lock:
            self._cache.clear()

    async def size(self) -> int:
        """Current number of entries (including expired not yet evicted)."""
        async with self._lock:
            return len(self._cache)

    @property
    def stats(self) -> dict[str, Any]:
        """Cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }

    async def cleanup(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        now = time.monotonic()
        removed = 0
        async with self._lock:
            expired_keys = [k for k, (_, exp) in self._cache.items() if now > exp]
            for k in expired_keys:
                del self._cache[k]
                removed += 1
        return removed


class MultiTierCache:
    """Two-level cache: fast in-memory + slower backing store.

    L1: In-memory TTLCache (hot data)
    L2: Pluggable async cache (warm data — e.g., Redis, SQLite)
    """

    def __init__(
        self,
        l1_max_size: int = 1000,
        l1_ttl: float = 60.0,
    ) -> None:
        self._l1 = TTLCache[K, V](max_size=l1_max_size, default_ttl=l1_ttl)
        self._l2: Optional[TTLCache[K, V]] = None

    def set_l2(self, cache: TTLCache[K, V]) -> None:
        """Attach a second-level cache."""
        self._l2 = cache

    async def get(self, key: K, l1_ttl: Optional[float] = None) -> Optional[V]:
        """Get from L1, falling back to L2."""
        value = await self._l1.get(key, ttl=l1_ttl)
        if value is not None:
            return value

        if self._l2:
            value = await self._l2.get(key)
            if value is not None:
                # Promote to L1
                await self._l1.put(key, value, ttl=l1_ttl)
                return value

        return None

    async def put(self, key: K, value: V, l1_ttl: Optional[float] = None) -> None:
        """Put into both L1 and L2."""
        await self._l1.put(key, value, ttl=l1_ttl)
        if self._l2:
            await self._l2.put(key, value)

    async def invalidate(self, key: K) -> None:
        """Invalidate in both tiers."""
        await self._l1.invalidate(key)
        if self._l2:
            await self._l2.invalidate(key)
