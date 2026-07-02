"""Dhan-specific retry executor with exponential backoff.

Provides per-endpoint retry policies:
  - Orders: 3 retries, backoff 1s-8s
  - Market data: 2 retries, backoff 0.5s-4s
  - Portfolio: 3 retries, backoff 1s-8s
  - Admin: 3 retries, backoff 1s-8s

Retryable exceptions: Timeout, ConnectionError, OSError, 5xx responses
Non-retryable: 4xx (except 429 rate limit), authentication errors
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from brokers.common.resilience.backoff import ExponentialBackoff
from brokers.common.resilience.circuit_breaker import CircuitBreaker
from brokers.common.resilience.rate_limiter import (
    MultiBucketRateLimiter,
)
from brokers.common.resilience.retry import RetryConfig, RetryExecutor

logger = logging.getLogger(__name__)


@dataclass
class DhanRetryPolicy:
    """Per-endpoint retry policy for Dhan API.

    Attributes:
        category: Endpoint category name.
        max_attempts: Total attempts including the initial call.
        base_delay_ms: Initial backoff delay in milliseconds.
        max_delay_ms: Maximum backoff delay in milliseconds.
    """

    category: str
    max_attempts: int = 3
    base_delay_ms: float = 1000.0
    max_delay_ms: float = 8000.0

    def to_retry_config(self) -> RetryConfig:
        """Convert to a common RetryConfig."""
        return RetryConfig(
            max_attempts=self.max_attempts,
            max_retry_delay_ms=int(self.max_delay_ms),
        )

    def to_backoff(self) -> ExponentialBackoff:
        """Create an ExponentialBackoff tuned for this policy."""
        return ExponentialBackoff(
            base_delay_ms=self.base_delay_ms,
            max_delay_ms=self.max_delay_ms,
            multiplier=2.0,
            jitter_factor=0.2,
        )


# ── Pre-defined policies per endpoint category ────────────────────────────

#: Orders: 3 retries, backoff 1s-8s (financial operations, cautious)
ORDERS_POLICY = DhanRetryPolicy(
    category="orders",
    max_attempts=3,
    base_delay_ms=1000.0,
    max_delay_ms=8000.0,
)

#: Market data: 2 retries, backoff 0.5s-4s (bursty, recover fast)
MARKET_DATA_POLICY = DhanRetryPolicy(
    category="market_data",
    max_attempts=2,
    base_delay_ms=500.0,
    max_delay_ms=4000.0,
)

#: Portfolio: 3 retries, backoff 1s-8s (important but not time-critical)
PORTFOLIO_POLICY = DhanRetryPolicy(
    category="portfolio",
    max_attempts=3,
    base_delay_ms=1000.0,
    max_delay_ms=8000.0,
)

#: Admin: 3 retries, backoff 1s-8s (token refresh, account info)
ADMIN_POLICY = DhanRetryPolicy(
    category="admin",
    max_attempts=3,
    base_delay_ms=1000.0,
    max_delay_ms=8000.0,
)

#: Mapping of category name to retry policy
_POLICY_MAP: dict[str, DhanRetryPolicy] = {
    "orders": ORDERS_POLICY,
    "market_data": MARKET_DATA_POLICY,
    "portfolio": PORTFOLIO_POLICY,
    "admin": ADMIN_POLICY,
}


class DhanRetryExecutorFactory:
    """Factory for Dhan-specific retry executors.

    Creates RetryExecutor instances pre-configured with the correct
    circuit breaker, rate limiter, and backoff for each endpoint category.
    """

    @staticmethod
    def create(
        category: str,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: MultiBucketRateLimiter | None = None,
    ) -> RetryExecutor:
        """Create a retry executor for the given endpoint category.

        Args:
            category: One of 'orders', 'market_data', 'portfolio', 'admin'.
            circuit_breaker: Optional circuit breaker for this category.
            rate_limiter: Optional shared rate limiter.

        Returns:
            Configured RetryExecutor instance.

        Raises:
            ValueError: If category is not recognized.
        """
        policy = _POLICY_MAP.get(category)
        if policy is None:
            # Default to admin policy for unknown categories
            logger.warning(
                "unknown_dhan_retry_category",
                extra={"category": category, "defaulting_to": "admin"},
            )
            policy = ADMIN_POLICY

        rate_limit_category = category if rate_limiter else None

        return RetryExecutor(
            config=policy.to_retry_config(),
            circuit_breaker=circuit_breaker,
            rate_limiter=rate_limiter,
            rate_limit_category=rate_limit_category,
            backoff=policy.to_backoff(),
            on_retry=lambda attempt, exc: logger.warning(
                "dhan_retry",
                extra={
                    "category": category,
                    "attempt": attempt + 1,
                    "error": str(exc),
                },
            ),
        )


def create_retry_executor(
    category: str,
    circuit_breaker: CircuitBreaker | None = None,
    rate_limiter: MultiBucketRateLimiter | None = None,
) -> RetryExecutor:
    """Convenience function to create a Dhan retry executor.

    Args:
        category: Endpoint category name.
        circuit_breaker: Optional circuit breaker.
        rate_limiter: Optional rate limiter.

    Returns:
        Configured RetryExecutor.
    """
    return DhanRetryExecutorFactory.create(
        category=category,
        circuit_breaker=circuit_breaker,
        rate_limiter=rate_limiter,
    )
