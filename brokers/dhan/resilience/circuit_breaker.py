"""Dhan-specific circuit breaker configuration.

Provides per-category circuit breakers aligned with Dhan API
endpoint groups: orders, market_data, portfolio, admin.

Thresholds follow the task specification:
  - Failure threshold: 5 consecutive failures
  - Recovery timeout: 30 seconds
  - Half-open max attempts (success_threshold): 3

Orders category uses a lower threshold (3) because financial
operations are more sensitive to failures.
"""

from __future__ import annotations

from dataclasses import dataclass

from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

#: Failure threshold for order-related endpoints (lower = more sensitive)
ORDERS_FAILURE_THRESHOLD = 3

#: Failure threshold for market data, portfolio, admin endpoints
DEFAULT_FAILURE_THRESHOLD = 5

#: Recovery timeout in milliseconds (30 seconds)
RECOVERY_TIMEOUT_MS = 30_000

#: Number of consecutive successes needed to close a half-open circuit
SUCCESS_THRESHOLD = 3


@dataclass
class DhanCircuitBreakerFactory:
    """Factory for Dhan-specific circuit breakers.

    Provides pre-configured circuit breakers for each endpoint category
    with thresholds tuned for Dhan API behavior.
    """

    @staticmethod
    def create_orders() -> CircuitBreaker:
        """Circuit breaker for order endpoints (place, modify, cancel, get).

        Lower failure threshold (3) because order operations involve
        real money and must fail fast on repeated errors.
        """
        return CircuitBreaker(
            "dhan-orders",
            CircuitBreakerConfig(
                failure_threshold=ORDERS_FAILURE_THRESHOLD,
                success_threshold=SUCCESS_THRESHOLD,
                open_duration_ms=RECOVERY_TIMEOUT_MS,
            ),
        )

    @staticmethod
    def create_market_data() -> CircuitBreaker:
        """Circuit breaker for market data endpoints (quotes, historical).

        Standard threshold (5) — market data failures are bursty and
        often recover quickly; should not trip on transient spikes.
        """
        return CircuitBreaker(
            "dhan-market-data",
            CircuitBreakerConfig(
                failure_threshold=DEFAULT_FAILURE_THRESHOLD,
                success_threshold=SUCCESS_THRESHOLD,
                open_duration_ms=RECOVERY_TIMEOUT_MS,
            ),
        )

    @staticmethod
    def create_portfolio() -> CircuitBreaker:
        """Circuit breaker for portfolio endpoints (holdings, positions).

        Standard threshold (5) — portfolio reads are non-critical
        and often succeed even during market data outages.
        """
        return CircuitBreaker(
            "dhan-portfolio",
            CircuitBreakerConfig(
                failure_threshold=DEFAULT_FAILURE_THRESHOLD,
                success_threshold=SUCCESS_THRESHOLD,
                open_duration_ms=RECOVERY_TIMEOUT_MS,
            ),
        )

    @staticmethod
    def create_admin() -> CircuitBreaker:
        """Circuit breaker for admin endpoints (token refresh, account info).

        Standard threshold (5) — admin operations are infrequent
        but critical; open duration is 30s to allow recovery.
        """
        return CircuitBreaker(
            "dhan-admin",
            CircuitBreakerConfig(
                failure_threshold=DEFAULT_FAILURE_THRESHOLD,
                success_threshold=SUCCESS_THRESHOLD,
                open_duration_ms=RECOVERY_TIMEOUT_MS,
            ),
        )


def create_circuit_breakers() -> dict[str, CircuitBreaker]:
    """Create all Dhan circuit breakers and return as a dict.

    Returns:
        Dict mapping category name to CircuitBreaker instance.
        Keys: 'orders', 'market_data', 'portfolio', 'admin'
    """
    return {
        "orders": DhanCircuitBreakerFactory.create_orders(),
        "market_data": DhanCircuitBreakerFactory.create_market_data(),
        "portfolio": DhanCircuitBreakerFactory.create_portfolio(),
        "admin": DhanCircuitBreakerFactory.create_admin(),
    }
