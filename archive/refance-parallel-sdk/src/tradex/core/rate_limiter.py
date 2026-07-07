"""Rate limiting framework with token bucket and sliding window.

Provider-agnostic rate limiting. Providers declare their limits,
the framework enforces them transparently.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass

from tradex.core.config import RateLimitConfig


@dataclass
class TokenBucket:
    """Token bucket rate limiter.

    Allows burst up to bucket capacity, then refills at a steady rate.
    """

    capacity: int
    refill_rate: float  # tokens per second
    _tokens: float = 0.0
    _last_refill: float = 0.0
    _lock: asyncio.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._tokens = float(self.capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> float:
        """Acquire tokens, waiting if necessary. Returns wait time."""
        async with self._lock:
            self._refill()

            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0

            # Calculate wait time
            deficit = tokens - self._tokens
            wait_time = deficit / self.refill_rate
            self._tokens = 0.0
            return wait_time

    async def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without waiting."""
        async with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now

    @property
    def available(self) -> float:
        """Current available tokens (approximate)."""
        self._refill()
        return self._tokens


class SlidingWindowCounter:
    """Sliding window rate limiter.

    Tracks request timestamps in a sliding window for precise counting.
    """

    def __init__(self, window_seconds: float, max_requests: int) -> None:
        self._window = window_seconds
        self._max_requests = max_requests
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Acquire permission, waiting if necessary. Returns wait time."""
        async with self._lock:
            now = time.monotonic()
            self._evict(now)

            if len(self._timestamps) < self._max_requests:
                self._timestamps.append(now)
                return 0.0

            # Wait until the oldest request expires
            wait_time = self._timestamps[0] + self._window - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                now = time.monotonic()
                self._evict(now)

            self._timestamps.append(now)
            return wait_time

    async def try_acquire(self) -> bool:
        """Try without waiting."""
        async with self._lock:
            now = time.monotonic()
            self._evict(now)
            if len(self._timestamps) < self._max_requests:
                self._timestamps.append(now)
                return True
            return False

    def _evict(self, now: float) -> None:
        """Remove timestamps outside the window."""
        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    @property
    def current_count(self) -> int:
        """Current requests in window."""
        now = time.monotonic()
        self._evict(now)
        return len(self._timestamps)


class RateLimiter:
    """Composite rate limiter supporting multiple time windows.

    Enforces per-second, per-minute, per-hour, and per-day limits
    using token buckets for burst handling and sliding windows for
    precise long-window enforcement.
    """

    def __init__(self, config: RateLimitConfig, category: str = "default") -> None:
        self._config = config
        self._category = category

        # Per-second: token bucket for burst handling
        self._per_second = TokenBucket(
            capacity=config.per_second,
            refill_rate=float(config.per_second),
        )

        # Per-minute, per-hour, per-day: sliding window counters
        self._per_minute = SlidingWindowCounter(60.0, config.per_minute)
        self._per_hour = SlidingWindowCounter(3600.0, config.per_hour)
        self._per_day = SlidingWindowCounter(86400.0, config.per_day)

    async def acquire(self) -> float:
        """Acquire permission across all windows. Returns total wait time."""
        total_wait = 0.0

        # Check each window from shortest to longest
        wait = await self._per_second.acquire()
        total_wait += wait

        wait = await self._per_minute.acquire()
        total_wait += wait

        wait = await self._per_hour.acquire()
        total_wait += wait

        wait = await self._per_day.acquire()
        total_wait += wait

        return total_wait

    async def try_acquire(self) -> bool:
        """Try to acquire without waiting. Returns False if any window is full."""
        return (
            await self._per_second.try_acquire()
            and await self._per_minute.try_acquire()
            and await self._per_hour.try_acquire()
            and await self._per_day.try_acquire()
        )

    @property
    def stats(self) -> dict[str, object]:
        """Current rate limiter state."""
        return {
            "category": self._category,
            "per_second_available": self._per_second.available,
            "per_minute_count": self._per_minute.current_count,
            "per_hour_count": self._per_hour.current_count,
            "per_day_count": self._per_day.current_count,
        }
