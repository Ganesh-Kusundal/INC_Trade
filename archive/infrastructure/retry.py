"""Unified retry framework with exponential backoff and circuit breaker integration.

Provides a single, configurable retry mechanism for all external calls
(broker APIs, database, websockets, etc.).

Usage::

    from infrastructure.retry import retry, RetryPolicy

    # Default policy
    @retry
    async def call_broker_api():
        ...

    # Custom policy
    @retry(policy=RetryPolicy(max_attempts=5, backoff_factor=2.0))
    def call_database():
        ...

Safety guards:
    * **Double-wrap detection** — applying ``@retry`` twice on the same
      function raises ``TypeError`` at decoration time.
    * **Nesting detection** — calling a ``@retry``-decorated function
      from inside another ``@retry`` loop logs a warning and sets the
      ``retry.nested`` structured-log event so CI can catch regressions.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, TypeVar

from brokers.common.resilience.errors import TradeXV2RecoverableError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ── Nesting detection ────────────────────────────────────────────────────
# Tracks whether the current execution context is already inside a @retry
# loop.  A second @retry entry while this is True indicates a nested-retry
# bug (e.g. @retry on a method called from a manual retry loop).
_retry_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_retry_active", default=False
)

# Sentinel attribute name used to detect double-wrapped functions.
_RETRY_MARKER = "_is_retry_wrapped"


class BackoffStrategy(Enum):
    """Backoff strategies for retry delays."""
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    RANDOM = "random"


@dataclass
class RetryPolicy:
    """Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts (including first try).
        backoff_factor: Multiplier for delay between retries.
        initial_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds.
        backoff_strategy: Strategy for calculating delays.
        retryable_exceptions: Tuple of exception types to retry on.
        jitter: Add random jitter to delays to avoid thundering herd.
    """

    max_attempts: int = 3
    backoff_factor: float = 2.0
    initial_delay: float = 1.0
    max_delay: float = 60.0
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    retryable_exceptions: tuple[type[Exception], ...] = (TradeXV2RecoverableError,)
    jitter: bool = True

    def __post_init__(self) -> None:
        """Validate policy parameters."""
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.initial_delay < 0:
            raise ValueError(f"initial_delay must be >= 0, got {self.initial_delay}")
        if self.max_delay < self.initial_delay:
            raise ValueError(
                f"max_delay ({self.max_delay}) must be >= initial_delay ({self.initial_delay})"
            )


def _get_func_name(func: Callable[..., Any]) -> str:
    """Safely extract function name for logging (handles partials, callables)."""
    return getattr(func, "__qualname__", getattr(func, "__name__", repr(func)))


# Pre-defined policies for common use cases (immutable to prevent accidental mutation)
POLICIES: MappingProxyType[str, RetryPolicy] = MappingProxyType({
    "default": RetryPolicy(),
    "aggressive": RetryPolicy(
        max_attempts=5,
        backoff_factor=2.0,
        initial_delay=0.5,
        max_delay=30.0,
    ),
    "conservative": RetryPolicy(
        max_attempts=2,
        backoff_factor=1.5,
        initial_delay=2.0,
        max_delay=60.0,
    ),
    "fast": RetryPolicy(
        max_attempts=3,
        backoff_factor=1.0,
        initial_delay=0.1,
        max_delay=5.0,
    ),
    "slow": RetryPolicy(
        max_attempts=10,
        backoff_factor=3.0,
        initial_delay=5.0,
        max_delay=300.0,
    ),
})


def _calculate_delay(
    attempt: int,
    policy: RetryPolicy,
) -> float:
    """Calculate delay for given attempt number."""

    if policy.backoff_strategy == BackoffStrategy.FIXED:
        delay = policy.initial_delay

    elif policy.backoff_strategy == BackoffStrategy.LINEAR:
        delay = policy.initial_delay * (attempt + 1)

    elif policy.backoff_strategy == BackoffStrategy.EXPONENTIAL:
        delay = policy.initial_delay * (policy.backoff_factor ** attempt)

    elif policy.backoff_strategy == BackoffStrategy.RANDOM:
        delay = random.uniform(policy.initial_delay, policy.max_delay)

    else:
        delay = policy.initial_delay

    # Cap at max_delay
    delay = min(delay, policy.max_delay)

    # Add jitter to avoid thundering herd
    if policy.jitter:
        jitter_range = delay * 0.1  # 10% jitter
        delay += random.uniform(-jitter_range, jitter_range)
        delay = max(0, delay)  # Ensure non-negative

    return delay


async def _async_retry(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    policy: RetryPolicy,
) -> Any:
    """Execute async function with retry logic."""

    # Nesting detection — if we're already inside a @retry loop, warn.
    if _retry_active.get():
        logger.warning(
            "retry.nested",
            extra={"function": _get_func_name(func)},
        )

    last_exception: Exception | None = None
    token = _retry_active.set(True)

    try:
        for attempt in range(policy.max_attempts):
            try:
                return await func(*args, **kwargs)

            except policy.retryable_exceptions as exc:
                last_exception = exc

                if attempt < policy.max_attempts - 1:
                    delay = _calculate_delay(attempt, policy)

                    logger.warning(
                        "Retry attempt %d/%d for %s after %s: %s",
                        attempt + 1,
                        policy.max_attempts,
                        _get_func_name(func),
                        type(exc).__name__,
                        str(exc),
                    )

                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "All %d attempts failed for %s: %s",
                        policy.max_attempts,
                        _get_func_name(func),
                        str(exc),
                    )

            except Exception as exc:
                # Non-retryable exception
                logger.error(
                    "Non-retryable exception in %s: %s",
                    _get_func_name(func),
                    str(exc),
                )
                raise

        # All retries exhausted
        raise last_exception  # type: ignore[misc]
    finally:
        _retry_active.reset(token)


def _sync_retry(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    policy: RetryPolicy,
) -> Any:
    """Execute sync function with retry logic."""

    # Nesting detection — if we're already inside a @retry loop, warn.
    if _retry_active.get():
        logger.warning(
            "retry.nested",
            extra={"function": _get_func_name(func)},
        )

    last_exception: Exception | None = None
    token = _retry_active.set(True)

    try:
        for attempt in range(policy.max_attempts):
            try:
                return func(*args, **kwargs)

            except policy.retryable_exceptions as exc:
                last_exception = exc

                if attempt < policy.max_attempts - 1:
                    delay = _calculate_delay(attempt, policy)

                    logger.warning(
                        "Retry attempt %d/%d for %s after %s: %s",
                        attempt + 1,
                        policy.max_attempts,
                        _get_func_name(func),
                        type(exc).__name__,
                        str(exc),
                    )

                    time.sleep(delay)
                else:
                    logger.error(
                        "All %d attempts failed for %s: %s",
                        policy.max_attempts,
                        _get_func_name(func),
                        str(exc),
                    )

            except Exception as exc:
                # Non-retryable exception
                logger.error(
                    "Non-retryable exception in %s: %s",
                    _get_func_name(func),
                    str(exc),
                )
                raise

        # All retries exhausted
        raise last_exception  # type: ignore[misc]
    finally:
        _retry_active.reset(token)


def retry(
    func: F | None = None,
    policy: RetryPolicy | str | None = None,
) -> F | Callable[[F], F]:
    """Decorator for adding retry logic to functions.

    Can be used in three ways:

    1. With default policy:
        @retry
        async def my_func():
            ...

    2. With custom policy:
        @retry(policy=RetryPolicy(max_attempts=5))
        async def my_func():
            ...

    3. With named policy:
        @retry(policy="aggressive")
        async def my_func():
            ...

    Args:
        func: Function to decorate (when used as @retry).
        policy: RetryPolicy instance or name of predefined policy.

    Returns:
        Decorated function or decorator.
    """

    # Guard against misuse: @retry(RetryPolicy(...)) passes policy as func
    if func is not None and not callable(func):
        raise TypeError(
            f"@retry expected a callable or None, got {type(func).__name__}. "
            "Use @retry(policy=...) instead."
        )

    # Handle @retry (no parentheses)
    if func is not None:
        # Double-wrap detection — prevent @retry applied twice.
        if getattr(func, _RETRY_MARKER, False):
            raise TypeError(
                f"{_get_func_name(func)} is already wrapped by @retry. "
                "Applying @retry twice causes multiplicative attempt explosion."
            )
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await _async_retry(func, args, kwargs, POLICIES["default"])
            async_wrapper._is_retry_wrapped = True  # type: ignore[attr-defined]
            return async_wrapper  # type: ignore[return-value]
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                return _sync_retry(func, args, kwargs, POLICIES["default"])
            sync_wrapper._is_retry_wrapped = True  # type: ignore[attr-defined]
            return sync_wrapper  # type: ignore[return-value]

    # Handle @retry() or @retry(policy=...)
    def decorator(f: F) -> F:
        # Double-wrap detection — prevent @retry applied twice.
        if getattr(f, _RETRY_MARKER, False):
            raise TypeError(
                f"{_get_func_name(f)} is already wrapped by @retry. "
                "Applying @retry twice causes multiplicative attempt explosion."
            )

        # Resolve policy
        if policy is None:
            resolved_policy = POLICIES["default"]
        elif isinstance(policy, str):
            if policy not in POLICIES:
                raise ValueError(
                    f"Unknown policy '{policy}'. Available: {list(POLICIES.keys())}"
                )
            resolved_policy = POLICIES[policy]
        else:
            resolved_policy = policy

        if asyncio.iscoroutinefunction(f):
            @functools.wraps(f)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await _async_retry(f, args, kwargs, resolved_policy)
            async_wrapper._is_retry_wrapped = True  # type: ignore[attr-defined]
            return async_wrapper  # type: ignore[return-value]

        else:
            @functools.wraps(f)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                return _sync_retry(f, args, kwargs, resolved_policy)
            sync_wrapper._is_retry_wrapped = True  # type: ignore[attr-defined]
            return sync_wrapper  # type: ignore[return-value]

    return decorator


__all__ = [
    "POLICIES",
    "BackoffStrategy",
    "RetryPolicy",
    "retry",
]
