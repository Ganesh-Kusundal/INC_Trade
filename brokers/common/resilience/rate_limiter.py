"""Rate limiting with token bucket algorithm — thread-safe, burst-aware."""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    """Configuration for a rate limiter bucket."""

    rate_per_second: float = 10.0
    capacity: int = 10

    def __post_init__(self):
        if self.rate_per_second <= 0:
            raise ValueError(f"rate_per_second must be positive, got {self.rate_per_second}")
        if self.capacity <= 0:
            raise ValueError(f"capacity must be positive, got {self.capacity}")


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter.

    Tokens are refilled at ``rate_per_second`` and burst up to ``capacity``.
    Use ``acquire()`` to block until a token is available.

    Inspired by Trade_J's TokenBucketRateLimiter with ReentrantLock.
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self._tokens: float = float(self.config.capacity)
        self._last_refill_nanos: float = time.monotonic_ns()
        self._capacity: float = float(self.config.capacity)
        self._lock = threading.Lock()

    @property
    def available_tokens(self) -> float:
        with self._lock:
            # Read-only estimation — does NOT mutate state
            now_ns = time.monotonic_ns()
            elapsed_sec = (now_ns - self._last_refill_nanos) / 1_000_000_000.0
            estimated = self._tokens + (elapsed_sec * self.config.rate_per_second)
            return min(self._capacity, estimated)

    @property
    def rate(self) -> float:
        return self.config.rate_per_second

    @rate.setter
    def rate(self, value: float) -> None:
        with self._lock:
            self.config.rate_per_second = value

    def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        """Acquire ``tokens`` from the bucket.

        Args:
            tokens: Number of tokens to consume.
            timeout: Maximum time to wait in seconds. ``None`` blocks forever.

        Returns:
            ``True`` if tokens were acquired, ``False`` if timeout reached.
        """
        if tokens > self._capacity:
            return False

        deadline = (time.monotonic() + timeout) if timeout is not None else None

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True

            # Not enough tokens — wait or timeout
            if deadline is not None and time.monotonic() >= deadline:
                return False

            # Sleep for a fraction of the refill time
            sleep_time = min(
                timeout if timeout is not None else 0.001,
                1.0 / self.config.rate_per_second if self.config.rate_per_second > 0 else 0.001,
            )
            sleep_time = max(sleep_time, 0.001)
            time.sleep(sleep_time)

    async def acquire_async(self, tokens: int = 1, timeout: float | None = None) -> bool:
        """Async variant of ``acquire`` that never blocks the event loop."""
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

            sleep_time = min(
                timeout if timeout is not None else 0.001,
                1.0 / self.config.rate_per_second if self.config.rate_per_second > 0 else 0.001,
            )
            sleep_time = max(sleep_time, 0.001)
            await asyncio.sleep(sleep_time)

    def reset(self) -> None:
        """Reset the bucket to full capacity."""
        with self._lock:
            self._tokens = float(self.config.capacity)
            self._last_refill_nanos = time.monotonic_ns()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now_ns = time.monotonic_ns()
        elapsed_sec = (now_ns - self._last_refill_nanos) / 1_000_000_000.0
        if elapsed_sec > 0:
            new_tokens = elapsed_sec * self.config.rate_per_second
            self._tokens = min(self._capacity, self._tokens + new_tokens)
            self._last_refill_nanos = now_ns

    def __repr__(self) -> str:
        return (
            f"TokenBucketRateLimiter(rate={self.config.rate_per_second}, "
            f"capacity={self.config.capacity}, "
            f"available={self._tokens:.1f})"
        )


class MultiBucketRateLimiter:
    """Manages multiple rate limit buckets by category (e.g. orders, quotes, data).

    Maps 1:1 to Trade_J's MultiBucketRateLimiter pattern.
    """

    def __init__(self, configs: dict[str, RateLimitConfig]):
        self._buckets: dict[str, TokenBucketRateLimiter] = {}
        for category, config in configs.items():
            self._buckets[category] = TokenBucketRateLimiter(config)
        self._categories = tuple(configs.keys())

    def acquire(self, category: str, tokens: int = 1, timeout: float | None = None) -> bool:
        """Acquire tokens for a given category bucket."""
        bucket = self._buckets.get(category)
        if bucket is None:
            raise ValueError(f"Unknown category: {category}")
        return bucket.acquire(tokens, timeout)

    async def acquire_async(
        self,
        category: str,
        tokens: int = 1,
        timeout: float | None = None,
    ) -> bool:
        """Acquire tokens for a given category bucket without blocking the event loop."""
        bucket = self._buckets.get(category)
        if bucket is None:
            raise ValueError(f"Unknown category: {category}")
        return await bucket.acquire_async(tokens, timeout)

    def categories(self) -> list[str]:
        """Return a list of all category names."""
        return list(self._categories)

    def get_bucket(self, category: str) -> TokenBucketRateLimiter:
        """Get the underlying bucket for inspection."""
        bucket = self._buckets.get(category)
        if bucket is None:
            raise ValueError(f"Unknown category: {category}")
        return bucket

    def reduce_rate(self, category: str, factor: float) -> None:
        """Reduce the rate for a category (e.g., after 429 response)."""
        bucket = self.get_bucket(category)
        bucket.rate = bucket.rate * factor

    def increase_rate(self, category: str, factor: float) -> None:
        """Increase the rate for a category."""
        bucket = self.get_bucket(category)
        bucket.rate = bucket.rate * factor


class EndpointRateLimiter:
    """Per-endpoint rate limiter with blocking acquire.

    Wraps MultiBucketRateLimiter to provide a simple per-endpoint
    interface compatible with broker adapters that track rate limits
    per URL endpoint.

    Usage::

        limiter = EndpointRateLimiter(rate_per_second=10.0)
        limiter.acquire("/market-quote/RELIANCE")  # blocks until allowed
    """

    def __init__(self, rate_per_second: float = 10.0, capacity: int = 10):
        config = RateLimitConfig(rate_per_second=rate_per_second, capacity=capacity)
        self._multi = MultiBucketRateLimiter({"_default": config})
        self._rate_per_second = rate_per_second
        self._capacity = capacity

    def acquire(self, endpoint: str = "default", timeout: float | None = None) -> None:
        """Block until a request to the given endpoint is allowed.

        Args:
            endpoint: Endpoint identifier for per-endpoint tracking.
            timeout: Maximum wait time in seconds. None blocks forever.
        """
        if endpoint not in self._multi._buckets:
            config = RateLimitConfig(
                rate_per_second=self._rate_per_second,
                capacity=self._capacity,
            )
            self._multi._buckets[endpoint] = TokenBucketRateLimiter(config)
        self._multi.acquire(endpoint, tokens=1, timeout=timeout)

    @property
    def rate(self) -> float:
        return self._rate_per_second

    @rate.setter
    def rate(self, value: float) -> None:
        self._rate_per_second = value
        for bucket in self._multi._buckets.values():
            bucket.rate = value
