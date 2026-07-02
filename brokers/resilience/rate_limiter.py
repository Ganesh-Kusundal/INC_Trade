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
        self._condition = threading.Condition(threading.Lock())

    @property
    def available_tokens(self) -> float:
        with self._condition:
            self._refill()
            return self._tokens

    def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        if tokens > self._capacity:
            return False

        deadline = (time.monotonic() + timeout) if timeout is not None else None

        with self._condition:
            while True:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True

                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    return False

                # Calculate time to wait until enough tokens are available
                needed = tokens - self._tokens
                wait_time = needed / self._rate
                
                if deadline is not None:
                    wait_time = min(wait_time, deadline - now)
                
                # Wait until condition is notified or wait_time elapses
                self._condition.wait(timeout=wait_time)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

