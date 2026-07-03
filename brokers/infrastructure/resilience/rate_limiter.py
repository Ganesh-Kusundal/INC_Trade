from __future__ import annotations
import time
import threading


class TokenBucketRateLimiter:
    """Thread-safe Token Bucket algorithm for broker 429 errors."""

    def __init__(self, capacity: int, rate_per_second: float):
        self.capacity = capacity
        self.rate_per_second = rate_per_second
        self.tokens = float(capacity)
        self.last_refill_time = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill_time
        if elapsed > 0:
            new_tokens = elapsed * self.rate_per_second
            self.tokens = min(float(self.capacity), self.tokens + new_tokens)
            self.last_refill_time = now

    def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        start_time = time.monotonic()
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False

            time.sleep(0.01)


class MultiBucketRateLimiter:
    def __init__(self, configs: dict[str, TokenBucketRateLimiter]):
        self.limiters = configs

    def acquire(
        self, category: str, tokens: int = 1, timeout: float | None = None
    ) -> bool:
        limiter = self.limiters.get(category)
        if limiter:
            return limiter.acquire(tokens, timeout)
        return True
