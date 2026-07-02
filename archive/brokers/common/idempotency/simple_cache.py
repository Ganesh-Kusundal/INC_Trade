"""Simple thread-safe idempotency cache with optional TTL and locking.

Consolidates the duplicate in-memory idempotency caches previously
scattered across ``brokers.dhan.orders.IdempotencyCache`` and
``brokers.upstox.orders.idempotency.InMemoryIdempotencyCache``.

Both adapters now import and use this single implementation.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Generic, TypeVar

T = TypeVar("T")


class SimpleIdempotencyCache(Generic[T]):
    """Thread-safe in-memory idempotency cache with optional TTL.

    Implements the ``IdempotencyCachePort`` interface (``get``/``put``)
    and additionally exposes a ``lock(key)`` context manager for
    atomic check-then-act sequences (e.g. idempotent order placement).

    Parameters
    ----------
    max_size : int
        Maximum number of entries.  Oldest entry is evicted when exceeded.
    ttl_seconds : int
        Time-to-live for cached entries.  ``0`` disables expiration.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600) -> None:
        self._cache: dict[str, tuple[float, T]] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.RLock()

    # ── IdempotencyCachePort ───────────────────────────────────────────

    def get(self, key: str) -> T | None:
        """Return cached value for *key*, or ``None`` if missing / expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ts, value = entry
            if self._ttl > 0 and time.time() - ts > self._ttl:
                del self._cache[key]
                return None
            return value

    def put(self, key: str, value: T) -> None:
        """Store *value* under *key*, evicting the oldest entry if at capacity."""
        with self._lock:
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
            self._cache[key] = (time.time(), value)

    # ── Extended API (used by Dhan OrdersAdapter) ──────────────────────

    @contextmanager
    def lock(self, _key: str):  # type: ignore[override]
        """Acquire the cache lock for an atomic check-then-act sequence.

        The *key* argument is accepted for API compatibility but the lock
        is process-wide (all keys share one lock) because order placement
        must be globally serialised per correlation_id.
        """
        with self._lock:
            yield self

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._cache.clear()
