"""Retry executor — combines circuit breaker + rate limiter + backoff.

Maps 1:1 to Trade_J's RetryExecutor pattern:
  Circuit Breaker Check -> Rate Limit Acquire -> Execute -> Handle Result
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from brokers.common.resilience.backoff import BackoffStrategy, ExponentialBackoff
from brokers.common.resilience.circuit_breaker import CircuitBreaker
from brokers.common.resilience.errors import (
    CircuitBreakerOpenError,
    NonRetryableError,
    RetryableError,
)
from brokers.common.resilience.rate_limiter import MultiBucketRateLimiter
from domain.constants import MAX_RETRY_ATTEMPTS, MAX_RETRY_DELAY_MS

#: Default exception types considered transient/retryable.
DEFAULT_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = MAX_RETRY_ATTEMPTS
    max_retry_delay_ms: int = MAX_RETRY_DELAY_MS
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: DEFAULT_RETRYABLE_EXCEPTIONS
    )

    def __post_init__(self):
        if self.max_attempts <= 0:
            raise ValueError(f"max_attempts must be positive, got {self.max_attempts}")


class RetryExecutor:
    """Combined circuit breaker + rate limiter + retry executor.

    Execution flow:
    1. Circuit breaker check (fast-fail if open)
    2. Rate limit token acquisition (block until available)
    3. Execute the operation
    4. On success: record success in circuit breaker
    5. On retryable error: backoff and retry
    6. On non-retryable error: immediately fail
    """

    def __init__(
        self,
        config: RetryConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: MultiBucketRateLimiter | None = None,
        rate_limit_category: str | None = None,
        backoff: BackoffStrategy | None = None,
        on_retry: Callable[[int, Exception], None] | None = None,
        on_failure: Callable[[Exception], None] | None = None,
    ):
        self.config = config or RetryConfig()
        self.circuit_breaker = circuit_breaker
        self.rate_limiter = rate_limiter
        self.rate_limit_category = rate_limit_category
        self.backoff = backoff or ExponentialBackoff(
            base_delay_ms=100,
            max_delay_ms=config.max_retry_delay_ms if config else MAX_RETRY_DELAY_MS,
        )
        self._on_retry = on_retry
        self._on_failure = on_failure

    def execute(self, fn: Callable[[], Any]) -> Any:
        """Execute ``fn`` with circuit breaker + rate limiter + retry.

        Args:
            fn: The callable to execute.

        Returns:
            The return value of ``fn``.

        Raises:
            CircuitBreakerOpenError: If the circuit breaker is open.
            NonRetryableError: If fn raises a non-retryable error.
            RetryableError: If all retry attempts are exhausted.
        """
        last_exception = None

        for attempt in range(self.config.max_attempts):
            try:
                # 1. Circuit breaker check
                if self.circuit_breaker and not self.circuit_breaker.allow_request():
                    raise CircuitBreakerOpenError(self.circuit_breaker.name)

                # 2. Rate limit check
                if self.rate_limiter and self.rate_limit_category:
                    self.rate_limiter.acquire(self.rate_limit_category)

                # 3. Execute
                result = fn()

                # 4. Record success
                if self.circuit_breaker:
                    self.circuit_breaker.on_success()

                return result

            except CircuitBreakerOpenError:
                raise

            except NonRetryableError:
                if self.circuit_breaker:
                    self.circuit_breaker.on_failure()
                if self._on_failure:
                    self._on_failure(last_exception or NonRetryableError(""))
                raise

            except RetryableError as e:
                last_exception = e
                if self.circuit_breaker:
                    self.circuit_breaker.on_failure()

                if attempt < self.config.max_attempts - 1:
                    delay = self.backoff.delay(attempt)
                    time.sleep(delay)
                    if self._on_retry:
                        self._on_retry(attempt, e)
                else:
                    if self._on_failure:
                        self._on_failure(e)
                    raise

            except Exception as e:
                # Check if this exception type is retryable
                if isinstance(e, self.config.retryable_exceptions):
                    last_exception = e
                    if self.circuit_breaker:
                        self.circuit_breaker.on_failure()

                    if attempt < self.config.max_attempts - 1:
                        delay = self.backoff.delay(attempt)
                        time.sleep(delay)
                        if self._on_retry:
                            self._on_retry(attempt, e)
                    else:
                        if self._on_failure:
                            self._on_failure(e)
                        raise
                else:
                    # Non-retryable — fail immediately
                    last_exception = e
                    if self.circuit_breaker:
                        self.circuit_breaker.on_failure()
                    if self._on_failure:
                        self._on_failure(e)
                    raise

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
