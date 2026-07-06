"""Cache port — abstract caching interface for domain services.

This is a narrow Protocol (ISP) for cache operations. Implementations
can be in-memory, Redis, or any other caching backend.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CachePort(Protocol):
    """Cache interface for historical and market data caching.

    Supports TTL-based expiration, stale-while-revalidate pattern,
    and bulk operations.
    """

    def get(self, key: str) -> Any | None:
        """Retrieve a value from cache.

        Args:
            key: Cache key.

        Returns:
            Cached value if found and not expired, None otherwise.
        """
        ...

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
            ttl_seconds: Time-to-live in seconds. None = no expiration.
        """
        ...

    def delete(self, key: str) -> bool:
        """Remove a value from cache.

        Args:
            key: Cache key.

        Returns:
            True if the key existed and was deleted, False otherwise.
        """
        ...

    def clear(self) -> None:
        """Clear all cached entries."""
        ...

    def get_stale(self, key: str, max_age_seconds: float) -> tuple[Any, bool]:
        """Get a value even if stale, with staleness indicator.

        Implements the stale-while-revalidate pattern.

        Args:
            key: Cache key.
            max_age_seconds: Maximum age before value is considered stale.

        Returns:
            Tuple of (value, is_stale). Value may be None if not in cache.
        """
        ...

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Retrieve multiple values at once.

        Args:
            keys: List of cache keys.

        Returns:
            Dict of key->value for found entries. Missing keys are omitted.
        """
        ...

    def set_many(self, items: dict[str, Any], ttl_seconds: float | None = None) -> None:
        """Store multiple values at once.

        Args:
            items: Dict of key->value pairs to cache.
            ttl_seconds: Time-to-live in seconds. None = no expiration.
        """
        ...
