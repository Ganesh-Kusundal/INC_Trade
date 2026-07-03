"""Generic in-memory idempotency cache for broker order placement."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Generic, TypeVar

T = TypeVar("T")


class TypedIdempotencyCache(Generic[T]):
    def __init__(self, *, max_size: int = 1000, ttl_seconds: float = 3600.0) -> None:
        self._cache: dict[str, tuple[T, float]] = {}
        self._lock = threading.RLock()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, correlation_id: str) -> T | None:
        with self._lock:
            entry = self._cache.get(correlation_id)
            if entry is None:
                return None
            value, ts = entry
            if self._ttl > 0 and time.monotonic() - ts > self._ttl:
                del self._cache[correlation_id]
                return None
            return value

    def put(self, correlation_id: str, value: T) -> None:
        with self._lock:
            while len(self._cache) >= self._max_size:
                oldest = min(self._cache, key=lambda k: self._cache[k][1])
                del self._cache[oldest]
            self._cache[correlation_id] = (value, time.monotonic())

    @contextmanager
    def lock(self, _key: str):
        """Process-wide lock for atomic check-then-act on a correlation id."""
        with self._lock:
            yield self

    def check_and_set(self, correlation_id: str) -> bool:
        """Atomically check if key exists; if not, set a sentinel and return True.

        Returns True if the key is new (caller should proceed), False if duplicate.
        """
        with self._lock:
            existing = self.get(correlation_id)
            if existing is not None:
                return False
            self._cache[correlation_id] = (None, time.monotonic())  # type: ignore[assignment]
            return True

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


OrderResultCache = TypedIdempotencyCache
