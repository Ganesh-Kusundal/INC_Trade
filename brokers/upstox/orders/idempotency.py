"""In-memory idempotency cache for order placement safety.

Mirrors ``brokers.dhan.orders.idempotency.InMemoryIdempotencyCache``.
"""

from __future__ import annotations

import threading
from typing import Generic, TypeVar

T = TypeVar("T")


class InMemoryIdempotencyCache(Generic[T]):
    def __init__(self) -> None:
        self._store: dict[str, T] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> T | None:
        with self._lock:
            return self._store.get(key)

    def put(self, key: str, value: T) -> None:
        with self._lock:
            self._store[key] = value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
