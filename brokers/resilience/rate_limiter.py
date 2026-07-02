"""Token bucket rate limiter — thread-safe, burst-aware.

Tokens refill at a fixed rate. Burst up to capacity is allowed.
Use acquire() to block until a token is available.
"""

from __future__ import annotations

import threading
import time


class TokenBucketRateLimiter:
    def __init__(self, rate_per_second: float = 10.0, capacity: int = 10):
        if rate_per_second <= 0:
            raise ValueError(f"rate_per_second must be positive, got {rate_per_second}")
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")

        self._rate = rate_per_second
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    @property
    def available_tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        if tokens > self._capacity:
            return False

        deadline = (time.monotonic() + timeout) if timeout is not None else None

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True

            if deadline is not None and time.monotonic() >= deadline:
                return False

            time.sleep(0.001)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now
