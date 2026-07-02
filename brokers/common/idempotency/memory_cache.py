"""Memory-based idempotency cache for development and testing.

This implementation stores data in memory with TTL support. It's suitable for:
- Development environments
- Testing scenarios
- Single-instance deployments

For production multi-instance deployments, use RedisIdempotencyCache instead.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Generic, TypeVar

from brokers.common.idempotency.service import IdempotencyCacheBackend

T = TypeVar("T")


class CacheEntry(Generic[T]):
    """Cache entry with value and expiration time."""
    
    def __init__(self, value: T, expires_at: float):
        self.value = value
        self.expires_at = expires_at  # Unix timestamp
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class MemoryIdempotencyCache(IdempotencyCacheBackend[T]):
    """Thread-safe in-memory idempotency cache with TTL support.
    
    This cache stores entries in a dictionary with automatic TTL expiration.
    All operations are thread-safe using a reentrant lock.
    """

    def __init__(self, default_ttl_seconds: int = 86400, max_size: int = 10000):
        """Initialize the memory cache.
        
        Args:
            default_ttl_seconds: Default TTL for entries in seconds (default: 24 hours)
            max_size: Maximum number of entries to store (LRU eviction when exceeded)
        """
        self._cache: dict[str, CacheEntry[T]] = {}
        self._lock = threading.RLock()
        self._default_ttl = default_ttl_seconds
        self._max_size = max_size
        self._access_order: list[str] = []  # For LRU eviction
        
        # Metrics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _evict_if_needed(self) -> None:
        """Evict oldest entries if cache exceeds max size."""
        while len(self._cache) > self._max_size and self._access_order:
            # Remove least recently used
            oldest_key = self._access_order.pop(0)
            if oldest_key in self._cache:
                del self._cache[oldest_key]
                self._evictions += 1

    def _update_access_order(self, key: str) -> None:
        """Update access order for LRU tracking."""
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    def get(self, key: str) -> T | None:
        """Retrieve a value by key, returning None if not found or expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            
            if entry.is_expired():
                # Remove expired entry
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                self._misses += 1
                return None
            
            self._update_access_order(key)
            self._hits += 1
            return entry.value

    def put(self, key: str, value: T, ttl_seconds: int | None = None) -> None:
        """Store a value by key with optional TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = time.time() + ttl
        
        with self._lock:
            self._evict_if_needed()
            self._cache[key] = CacheEntry(value, expires_at)
            self._update_access_order(key)

    def delete(self, key: str) -> bool:
        """Delete a value by key. Returns True if key existed."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return True
            return False

    def clear(self) -> int:
        """Clear all entries. Returns number of entries cleared."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._access_order.clear()
            return count

    def contains(self, key: str) -> bool:
        """Check if a key exists and is not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            
            if entry.is_expired():
                # Remove expired entry
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return False
            
            return True

    def health_check(self) -> bool:
        """Check if the cache is healthy (always true for memory cache)."""
        return True

    def cleanup_expired(self) -> int:
        """Clean up expired entries. Returns number of entries removed."""
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() 
                if entry.is_expired()
            ]
            
            for key in expired_keys:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
            
            return len(expired_keys)

    def get_info(self) -> dict[str, Any]:
        """Get cache information and statistics."""
        with self._lock:
            return {
                "type": "memory",
                "size": len(self._cache),
                "max_size": self._max_size,
                "default_ttl_seconds": self._default_ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0.0,
                "evictions": self._evictions,
            }

    def reset_metrics(self) -> None:
        """Reset cache metrics."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    @property
    def stats(self) -> dict[str, Any]:
        """Get current cache statistics."""
        return self.get_info()


__all__ = ["MemoryIdempotencyCache", "CacheEntry"]