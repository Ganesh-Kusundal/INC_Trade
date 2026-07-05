"""Idempotency cache for order deduplication.

If the same correlation_id is submitted twice within the TTL window,
the cached response is returned without re-executing.

Protects against network retries, duplicate clicks, and replayed requests.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class IdempotencyCache:
    """Bounded LRU idempotency cache with TTL expiry.

    Args:
        max_size: Maximum number of cached entries.
        ttl_seconds: Time-to-live for each entry in seconds.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: float = 300) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, correlation_id: str) -> Any | None:
        """Look up a cached response by correlation_id.

        Returns None if not found or expired.
        """
        with self._lock:
            entry = self._cache.get(correlation_id)
            if entry is None:
                return None
            response, timestamp = entry
            if time.monotonic() - timestamp > self._ttl:
                del self._cache[correlation_id]
                return None
            self._cache.move_to_end(correlation_id)
            return response

    def put(self, correlation_id: str, response: Any) -> None:
        """Cache a response for a correlation_id."""
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[correlation_id] = (response, time.monotonic())

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)
