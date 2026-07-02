"""Dhan-specific rate limiter with token bucket algorithm.

Per-endpoint rate limits from Dhan API documentation:
  - Non-Trading APIs: 20 requests/second
  - Order APIs: 25 requests/second
  - Data APIs: 10 requests/second
  - Quote APIs: 1 request/second (using 0.15s safety interval → ~6.67/s capacity)

Features:
  - Token bucket rate limiting via MultiBucketRateLimiter
  - Per-category buckets (orders, market_data, portfolio, admin)
  - Graceful degradation with timeout-based acquire
  - Metrics collection (requests/sec estimation, available tokens)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from brokers.common.resilience.rate_limiter import (
    MultiBucketRateLimiter,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)


# ── Dhan API rate limits (requests per second) ──────────────────────────

#: Order APIs: Up to 25 requests per second
ORDERS_RATE_PER_SECOND = 25.0
ORDERS_CAPACITY = 25

#: Data APIs: Up to 10 requests per second
MARKET_DATA_RATE_PER_SECOND = 10.0
MARKET_DATA_CAPACITY = 10

#: Quote APIs: 1 request per second (conservative: use 6.67 for bucket math)
QUOTE_RATE_PER_SECOND = 6.67
QUOTE_CAPACITY = 7

#: Non-Trading APIs: Up to 20 requests per second
PORTFOLIO_RATE_PER_SECOND = 20.0
PORTFOLIO_CAPACITY = 20

#: Admin APIs: Moderate rate (token refresh is infrequent)
ADMIN_RATE_PER_SECOND = 10.0
ADMIN_CAPACITY = 10


@dataclass
class DhanRateLimiterFactory:
    """Factory for Dhan-specific rate limiters.

    Creates a MultiBucketRateLimiter with per-category buckets
    configured for Dhan API rate limits.
    """

    @staticmethod
    def create_config(category: str) -> RateLimitConfig:
        """Get the rate limit config for a category.

        Args:
            category: One of 'orders', 'market_data', 'portfolio', 'admin'.

        Returns:
            RateLimitConfig tuned for the category.
        """
        configs = {
            "orders": RateLimitConfig(
                rate_per_second=ORDERS_RATE_PER_SECOND,
                capacity=ORDERS_CAPACITY,
            ),
            "market_data": RateLimitConfig(
                rate_per_second=MARKET_DATA_RATE_PER_SECOND,
                capacity=MARKET_DATA_CAPACITY,
            ),
            "portfolio": RateLimitConfig(
                rate_per_second=PORTFOLIO_RATE_PER_SECOND,
                capacity=PORTFOLIO_CAPACITY,
            ),
            "admin": RateLimitConfig(
                rate_per_second=ADMIN_RATE_PER_SECOND,
                capacity=ADMIN_CAPACITY,
            ),
        }
        config = configs.get(category)
        if config is None:
            logger.warning(
                "unknown_rate_limit_category",
                extra={"category": category, "defaulting_to": "admin"},
            )
            config = configs["admin"]
        return config

    @staticmethod
    def create() -> MultiBucketRateLimiter:
        """Create a MultiBucketRateLimiter with all Dhan categories.

        Returns:
            MultiBucketRateLimiter with orders, market_data, portfolio,
            and admin buckets configured.
        """
        configs = {
            "orders": DhanRateLimiterFactory.create_config("orders"),
            "market_data": DhanRateLimiterFactory.create_config("market_data"),
            "portfolio": DhanRateLimiterFactory.create_config("portfolio"),
            "admin": DhanRateLimiterFactory.create_config("admin"),
        }
        return MultiBucketRateLimiter(configs)


def create_rate_limiter() -> MultiBucketRateLimiter:
    """Convenience function to create Dhan rate limiter.

    Returns:
        MultiBucketRateLimiter with all categories configured.
    """
    return DhanRateLimiterFactory.create()


class DhanRateLimiterMetrics:
    """Collects rate limiter metrics for observability.

    Tracks:
      - Request timestamps per category (for requests/sec calculation)
      - Queue depth (waiting acquire calls)
      - Rate limit rejections (timeouts)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._request_timestamps: dict[str, list[float]] = {}
        self._queue_depth: dict[str, int] = {}
        self._rejections: dict[str, int] = {}

    def record_request(self, category: str) -> None:
        """Record a successful rate limit acquisition."""
        with self._lock:
            timestamps = self._request_timestamps.setdefault(category, [])
            # Keep only last 60 seconds of data
            cutoff = time.monotonic() - 60.0
            timestamps[:] = [t for t in timestamps if t > cutoff]
            timestamps.append(time.monotonic())

    def record_rejection(self, category: str) -> None:
        """Record a rate limit rejection (timeout)."""
        with self._lock:
            self._rejections[category] = self._rejections.get(category, 0) + 1

    def increment_queue_depth(self, category: str) -> None:
        """Increment queue depth for a category."""
        with self._lock:
            self._queue_depth[category] = self._queue_depth.get(category, 0) + 1

    def decrement_queue_depth(self, category: str) -> None:
        """Decrement queue depth for a category."""
        with self._lock:
            depth = self._queue_depth.get(category, 0)
            if depth > 0:
                self._queue_depth[category] = depth - 1

    def get_requests_per_second(self, category: str) -> float:
        """Get current request rate for a category (last 10 seconds)."""
        with self._lock:
            timestamps = self._request_timestamps.get(category, [])
            if not timestamps:
                return 0.0
            cutoff = time.monotonic() - 10.0
            recent = [t for t in timestamps if t > cutoff]
            if len(recent) < 2:
                return float(len(recent))
            duration = recent[-1] - recent[0]
            if duration <= 0:
                return float(len(recent))
            return (len(recent) - 1) / duration

    def get_queue_depth(self, category: str) -> int:
        """Get current queue depth for a category."""
        with self._lock:
            return self._queue_depth.get(category, 0)

    def get_rejections(self, category: str) -> int:
        """Get total rejections for a category."""
        with self._lock:
            return self._rejections.get(category, 0)

    def snapshot(self) -> dict[str, Any]:
        """Get a full metrics snapshot for all categories."""
        with self._lock:
            all_categories = set(self._request_timestamps.keys()) | set(self._queue_depth.keys())
            result = {}
            for cat in all_categories:
                result[cat] = {
                    "requests_per_second": self._calc_rps_unsafe(cat),
                    "queue_depth": self._queue_depth.get(cat, 0),
                    "rejections": self._rejections.get(cat, 0),
                }
            return result

    def _calc_rps_unsafe(self, category: str) -> float:
        """Calculate RPS without acquiring lock (caller must hold lock)."""
        timestamps = self._request_timestamps.get(category, [])
        if not timestamps:
            return 0.0
        cutoff = time.monotonic() - 10.0
        recent = [t for t in timestamps if t > cutoff]
        if len(recent) < 2:
            return float(len(recent))
        duration = recent[-1] - recent[0]
        if duration <= 0:
            return float(len(recent))
        return (len(recent) - 1) / duration
