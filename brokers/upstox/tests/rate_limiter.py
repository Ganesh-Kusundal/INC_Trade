"""Rate limiter decorator for Upstox integration tests.

Limits function calls to ``max_rps`` requests per second using time.sleep.

Usage::

    from brokers.upstox.tests.rate_limiter import rate_limited

    @rate_limited(max_rps=10)
    def test_fetch_quotes():
        ...
"""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class _RateBucket:
    """Thread-safe sliding-window rate limiter bucket."""

    def __init__(self, max_rps: float) -> None:
        self._min_interval = 1.0 / max_rps if max_rps > 0 else 0.0
        self._last_call = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()


_buckets: dict[float, _RateBucket] = {}
_bucket_lock = threading.Lock()


def _get_bucket(max_rps: float) -> _RateBucket:
    with _bucket_lock:
        if max_rps not in _buckets:
            _buckets[max_rps] = _RateBucket(max_rps)
        return _buckets[max_rps]


def rate_limited(max_rps: float = 5.0) -> Callable[[F], F]:
    """Decorator that limits a function to ``max_rps`` calls per second.

    Args:
        max_rps: Maximum requests per second (default 5).

    Returns:
        Decorated function that sleeps when necessary to enforce the limit.
    """

    def decorator(func: F) -> F:
        bucket = _get_bucket(max_rps)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bucket.acquire()
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
