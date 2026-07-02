"""IdempotencyService — main interface for idempotency caching.

This service provides a unified interface for idempotency operations, supporting
multiple cache backends (Redis, file system, in-memory) with automatic fallback.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Generic, TypeVar

from brokers.common.idempotency.exceptions import IdempotencyError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class IdempotencyCacheBackend(ABC, Generic[T]):
    """Abstract base class for idempotency cache backends."""

    @abstractmethod
    def get(self, key: str) -> T | None:
        """Retrieve a value by key."""
        ...

    @abstractmethod
    def put(self, key: str, value: T, ttl_seconds: int | None = None) -> None:
        """Store a value by key with optional TTL."""
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a value by key. Returns True if key existed."""
        ...

    @abstractmethod
    def clear(self) -> int:
        """Clear all entries. Returns number of entries cleared."""
        ...

    @abstractmethod
    def contains(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the cache backend is healthy and available."""
        ...

    @abstractmethod
    def cleanup_expired(self) -> int:
        """Clean up expired entries. Returns number of entries removed."""
        ...


class IdempotencyService(Generic[T]):
    """Main idempotency service with fallback support.
    
    Provides a unified interface for idempotency operations with support for:
    - Primary cache backend (typically Redis)
    - Fallback cache backend (typically file system)
    - Automatic fallback on primary failure
    - Thread-safe operations
    - TTL-based expiration
    - Distributed locking (when supported by backend)
    """

    def __init__(
        self,
        primary_backend: IdempotencyCacheBackend[T],
        fallback_backend: IdempotencyCacheBackend[T] | None = None,
        default_ttl_seconds: int = 86400,  # 24 hours default
        enable_fallback: bool = True,
    ):
        """Initialize the idempotency service.
        
        Args:
            primary_backend: Primary cache backend (e.g., RedisIdempotencyCache)
            fallback_backend: Fallback cache backend for when primary fails
            default_ttl_seconds: Default TTL for cached entries in seconds
            enable_fallback: Whether to enable automatic fallback to secondary backend
        """
        self._primary = primary_backend
        self._fallback = fallback_backend
        self._default_ttl = default_ttl_seconds
        self._enable_fallback = enable_fallback
        self._lock = threading.RLock()
        
        # Track metrics for observability
        self._metrics = {
            "get_hits": 0,
            "get_misses": 0,
            "put_operations": 0,
            "fallback_operations": 0,
            "primary_failures": 0,
        }

    def get(self, key: str) -> T | None:
        """Retrieve a value by key, with automatic fallback."""
        with self._lock:
            try:
                value = self._primary.get(key)
                if value is not None:
                    self._metrics["get_hits"] += 1
                    return value
                self._metrics["get_misses"] += 1
                
                # Try fallback if enabled
                if self._enable_fallback and self._fallback is not None:
                    self._metrics["fallback_operations"] += 1
                    value = self._fallback.get(key)
                    if value is not None:
                        # Cache in primary if we got it from fallback
                        try:
                            self._primary.put(key, value, self._default_ttl)
                        except Exception as exc:
                            logger.warning(f"Failed to cache fallback value in primary: {exc}")
                        return value
                
                return None
                
            except Exception as exc:
                self._metrics["primary_failures"] += 1
                logger.warning(f"Primary cache get failed for key {key}: {exc}")
                
                if self._enable_fallback and self._fallback is not None:
                    self._metrics["fallback_operations"] += 1
                    try:
                        return self._fallback.get(key)
                    except Exception as fallback_exc:
                        logger.error(f"Fallback cache get also failed for key {key}: {fallback_exc}")
                
                return None

    def put(self, key: str, value: T, ttl_seconds: int | None = None) -> None:
        """Store a value by key with automatic fallback."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        
        with self._lock:
            self._metrics["put_operations"] += 1
            
            try:
                self._primary.put(key, value, ttl)
            except Exception as exc:
                self._metrics["primary_failures"] += 1
                logger.warning(f"Primary cache put failed for key {key}: {exc}")
                
                if self._enable_fallback and self._fallback is not None:
                    self._metrics["fallback_operations"] += 1
                    try:
                        self._fallback.put(key, value, ttl)
                    except Exception as fallback_exc:
                        logger.error(f"Fallback cache put also failed for key {key}: {fallback_exc}")
                        raise IdempotencyError(f"Failed to store idempotency key {key}: {fallback_exc}")
                else:
                    raise IdempotencyError(f"Failed to store idempotency key {key}: {exc}")

    def delete(self, key: str) -> bool:
        """Delete a value by key from all backends."""
        with self._lock:
            primary_deleted = False
            fallback_deleted = False
            
            try:
                primary_deleted = self._primary.delete(key)
            except Exception as exc:
                logger.warning(f"Primary cache delete failed for key {key}: {exc}")
            
            if self._fallback is not None:
                try:
                    fallback_deleted = self._fallback.delete(key)
                except Exception as exc:
                    logger.warning(f"Fallback cache delete failed for key {key}: {exc}")
            
            return primary_deleted or fallback_deleted

    def clear(self) -> int:
        """Clear all entries from all backends."""
        with self._lock:
            primary_cleared = 0
            fallback_cleared = 0
            
            try:
                primary_cleared = self._primary.clear()
            except Exception as exc:
                logger.warning(f"Primary cache clear failed: {exc}")
            
            if self._fallback is not None:
                try:
                    fallback_cleared = self._fallback.clear()
                except Exception as exc:
                    logger.warning(f"Fallback cache clear failed: {exc}")
            
            return primary_cleared + fallback_cleared

    def contains(self, key: str) -> bool:
        """Check if a key exists in any backend."""
        with self._lock:
            try:
                if self._primary.contains(key):
                    return True
            except Exception as exc:
                logger.warning(f"Primary cache contains check failed for key {key}: {exc}")
            
            if self._fallback is not None:
                try:
                    return self._fallback.contains(key)
                except Exception as exc:
                    logger.warning(f"Fallback cache contains check failed for key {key}: {exc}")
            
            return False

    def health_check(self) -> dict[str, bool]:
        """Check health of all backends."""
        health = {}
        
        try:
            health["primary"] = self._primary.health_check()
        except Exception:
            health["primary"] = False
        
        if self._fallback is not None:
            try:
                health["fallback"] = self._fallback.health_check()
            except Exception:
                health["fallback"] = False
        
        return health

    def get_metrics(self) -> dict[str, int]:
        """Get service metrics."""
        with self._lock:
            return self._metrics.copy()

    def cleanup_expired(self) -> int:
        """Clean up expired entries from all backends."""
        with self._lock:
            primary_cleaned = 0
            fallback_cleaned = 0
            
            try:
                primary_cleaned = self._primary.cleanup_expired()
            except Exception as exc:
                logger.warning(f"Primary cache cleanup failed: {exc}")
            
            if self._fallback is not None:
                try:
                    fallback_cleaned = self._fallback.cleanup_expired()
                except Exception as exc:
                    logger.warning(f"Fallback cache cleanup failed: {exc}")
            
            return primary_cleaned + fallback_cleaned

    def get_backend_info(self) -> dict[str, Any]:
        """Get information about the configured backends."""
        info = {
            "primary": type(self._primary).__name__,
            "fallback": type(self._fallback).__name__ if self._fallback else None,
            "default_ttl_seconds": self._default_ttl,
            "fallback_enabled": self._enable_fallback,
        }
        
        # Add backend-specific info if available
        if hasattr(self._primary, 'get_info'):
            try:
                info["primary_details"] = self._primary.get_info()
            except Exception:
                pass
        
        if self._fallback and hasattr(self._fallback, 'get_info'):
            try:
                info["fallback_details"] = self._fallback.get_info()
            except Exception:
                pass
        
        return info