"""Resilience constants — retry, circuit breaker, and backoff configuration.

All constants governing retry logic, circuit breaker thresholds, and
exponential backoff parameters.
"""

from __future__ import annotations

# ── Resilience timing ──────────────────────────────────────────────────────

#: Maximum delay between retry attempts (milliseconds). Must match
#: ``ExponentialBackoff._max_delay_ms`` and ``RetryConfig.max_retry_delay_ms``.
MAX_RETRY_DELAY_MS: int = 30_000

#: Base delay between retry attempts (milliseconds).
RETRY_BASE_DELAY_MS: int = 1_000

#: Maximum number of retry attempts.
MAX_RETRY_ATTEMPTS: int = 3

#: Default number of consecutive failures that opens the circuit breaker.
CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5

#: Number of consecutive successes in HALF_OPEN that closes the breaker.
CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 3

#: How long the breaker stays OPEN before allowing a probe (milliseconds).
CIRCUIT_BREAKER_OPEN_DURATION_MS: int = 30_000

#: Multiplier between successive backoff delays.
BACKOFF_MULTIPLIER: float = 2.0

#: ±Jitter applied to backoff delays (0.0 = no jitter, 0.2 = ±20%).
BACKOFF_JITTER: float = 0.2

__all__ = [
    "BACKOFF_JITTER",
    "BACKOFF_MULTIPLIER",
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "CIRCUIT_BREAKER_OPEN_DURATION_MS",
    "CIRCUIT_BREAKER_SUCCESS_THRESHOLD",
    "MAX_RETRY_ATTEMPTS",
    "MAX_RETRY_DELAY_MS",
    "RETRY_BASE_DELAY_MS",
]
