"""Retry framework with exponential backoff and jitter.

Provider-agnostic retry logic that works with any async callable.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Awaitable, Callable, Optional, TypeVar

from tradex.core.config import RetryConfig
from tradex.core.errors import BrokerError

T = TypeVar("T")


class RetryExhausted(BrokerError):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, last_error: BrokerError, attempts: int) -> None:
        super().__init__(
            f"Retry exhausted after {attempts} attempts: {last_error}",
            code=last_error.code,
            context=last_error.context,
        )
        self.last_error = last_error
        self.attempts = attempts


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    config: Optional[RetryConfig] = None,
    retryable_check: Optional[Callable[[BrokerError], bool]] = None,
    **kwargs: Any,
) -> T:
    """Execute an async function with retry logic.

    Args:
        func: The async callable to execute.
        *args: Positional arguments for the callable.
        config: Retry configuration. Uses defaults if None.
        retryable_check: Custom check for whether an error is retryable.
            If None, uses error.retryable property.
        **kwargs: Keyword arguments for the callable.

    Returns:
        The result of the callable.

    Raises:
        RetryExhausted: If all retries are exhausted.
        BrokerError: If the error is not retryable.
    """
    cfg = config or RetryConfig()
    last_error: Optional[BrokerError] = None

    for attempt in range(cfg.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except BrokerError as e:
            last_error = e

            # Check if retryable
            is_retryable = retryable_check(e) if retryable_check else e.retryable

            if not is_retryable or attempt >= cfg.max_retries:
                raise

            # Calculate delay with exponential backoff
            delay = min(
                cfg.base_delay * (cfg.exponential_base**attempt),
                cfg.max_delay,
            )

            # Add jitter
            if cfg.jitter:
                delay = delay * (0.5 + random.random() * 0.5)

            await asyncio.sleep(delay)

    # Should not reach here, but safety net
    raise RetryExhausted(last_error, cfg.max_retries + 1)  # type: ignore[misc]


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failure threshold reached, requests fail fast
    - HALF_OPEN: After cooldown, one test request allowed
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_period: float = 60.0,
        half_open_max: int = 1,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_period = cooldown_period
        self._half_open_max = half_open_max
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._state = "closed"
        self._half_open_count = 0

    @property
    def state(self) -> str:
        """Current circuit breaker state."""
        if self._state == "open":
            import time

            if time.monotonic() - self._last_failure_time >= self._cooldown_period:
                self._state = "half_open"
                self._half_open_count = 0
        return self._state

    @property
    def is_open(self) -> bool:
        """Whether the circuit is open (blocking requests)."""
        return self.state == "open"

    async def record_success(self) -> None:
        """Record a successful call."""
        if self._state in ("half_open", "open"):
            # Allow recovery: a success after open can reset
            self._success_count += 1
            if self._success_count >= self._half_open_max:
                self._state = "closed"
                self._failure_count = 0
                self._success_count = 0
        else:
            self._failure_count = max(0, self._failure_count - 1)

    async def record_failure(self) -> None:
        """Record a failed call."""
        import time

        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == "half_open":
            self._state = "open"
        elif self._failure_count >= self._failure_threshold:
            self._state = "open"

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self._state = "closed"
        self._failure_count = 0
        self._success_count = 0
