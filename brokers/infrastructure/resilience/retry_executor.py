from __future__ import annotations
import time
import logging
import random
from typing import Callable, TypeVar

from .circuit_breaker import CircuitBreaker
from .rate_limiter import MultiBucketRateLimiter

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryExecutor:
    """Unifies circuit breaker and rate limiter, applies exponential backoff for transient errors."""

    def __init__(
        self,
        max_attempts: int,
        base_delay: float,
        max_delay: float,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: MultiBucketRateLimiter | None = None,
        rate_limit_category: str | None = None,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.circuit_breaker = circuit_breaker
        self.rate_limiter = rate_limiter
        self.rate_limit_category = rate_limit_category

    def execute(self, func: Callable[[], T]) -> T:
        attempts = 0
        while attempts < self.max_attempts:
            if self.circuit_breaker and not self.circuit_breaker.allow_request():
                raise Exception("Circuit breaker is OPEN")

            if self.rate_limiter and self.rate_limit_category:
                if not self.rate_limiter.acquire(
                    self.rate_limit_category, timeout=self.max_delay
                ):
                    raise Exception("Rate limit exceeded")

            try:
                result = func()
                if self.circuit_breaker:
                    self.circuit_breaker.record_success()
                return result
            except Exception as e:
                attempts += 1

                error_msg = str(e).lower()
                is_5xx = "5" in error_msg and (
                    "error" in error_msg or "code" in error_msg
                )
                is_429 = "429" in error_msg or "rate limit" in error_msg
                is_transient = (
                    is_5xx
                    or is_429
                    or "timeout" in error_msg
                    or "connection" in error_msg
                )

                if self.circuit_breaker and is_5xx:
                    self.circuit_breaker.record_failure()

                if not is_transient or attempts >= self.max_attempts:
                    raise

                delay = min(self.max_delay, self.base_delay * (2 ** (attempts - 1)))
                jitter = delay * 0.2 * random.uniform(-1, 1)
                time.sleep(delay + jitter)
