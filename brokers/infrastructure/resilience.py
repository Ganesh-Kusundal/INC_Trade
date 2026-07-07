"""Resilience decorators — @rate_limit and @circuit_breaker.

Simple, composable decorators that wrap sync/async functions.
No factory classes, no DI containers — just pure Python decorators.

Usage::

    from brokers.infrastructure import rate_limit, circuit_breaker

    @circuit_breaker(failures=3, reset_timeout=30)
    @rate_limit(calls=10, per_second=1)
    def post_order(self, payload: dict) -> dict:
        ...

Strategy:
    - @rate_limit uses a TokenBucket per decorated function. Separate pools
      for market-data vs order-execution endpoints are achieved by applying
      the decorator with different parameters to different methods.
    - @circuit_breaker opens the circuit after N consecutive failures,
      blocks all calls for reset_timeout seconds, then probes with a single
      half-open attempt. Success closes the circuit; failure re-opens it.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ── Token Bucket (core of @rate_limit) ────────────────────────────────────


class _TokenBucket:
    """Thread-safe token bucket for a single limit configuration."""

    __slots__ = ("_rate", "_capacity", "_tokens", "_last_refill", "_lock")

    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = rate  # tokens per second
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 0.0) -> bool:
        """Try to consume one token. Returns True if acquired, False if denied."""
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
            if timeout <= 0:
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(remaining, 0.05))

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    @property
    def available(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


# ── @rate_limit decorator ─────────────────────────────────────────────────


def rate_limit(*, calls: int, per_second: float = 1.0, timeout: float = 0.0):
    """Limit the decorated function to *calls* per *per_second* seconds.

    Each decorated function gets its own token bucket.  For different limits
    on different endpoints, decorate separate methods with different params.

    Args:
        calls: Maximum number of calls allowed in the window.
        per_second: Window size in seconds (default 1.0 → rate per second).
        timeout: Max seconds to block waiting for a token (default 0 = fail fast).
    """
    bucket = _TokenBucket(rate=calls / per_second, capacity=calls)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not bucket.acquire(timeout=timeout):
                raise RateLimitExceeded(
                    f"Rate limit exceeded for {func.__name__}"
                    f" ({calls} calls per {per_second}s)"
                )
            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not bucket.acquire(timeout=timeout):
                raise RateLimitExceeded(
                    f"Rate limit exceeded for {func.__name__}"
                    f" ({calls} calls per {per_second}s)"
                )
            return await func(*args, **kwargs)

        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return wrapper  # type: ignore[return-value]

    return decorator


# ── Circuit Breaker state machine ──────────────────────────────────────────


class _CircuitState:
    __slots__ = ("_failures", "_last_failure", "_state", "_lock")
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self) -> None:
        self._failures: int = 0
        self._last_failure: float = 0.0
        self._state: str = self.CLOSED
        self._lock = threading.Lock()

    def record_success(self) -> None:
        with self._lock:
            self._state = self.CLOSED
            self._failures = 0

    def record_failure(self, threshold: int) -> str:
        with self._lock:
            self._failures += 1
            self._last_failure = time.monotonic()
            if self._state == self.HALF_OPEN or self._failures >= threshold:
                self._state = self.OPEN
        return self._state

    def allow_request(self, reset_timeout: float) -> bool:
        with self._lock:
            if self._state == self.CLOSED:
                return True
            if self._state == self.OPEN:
                elapsed = time.monotonic() - self._last_failure
                if elapsed >= reset_timeout:
                    self._state = self.HALF_OPEN
                    return True
                return False
            # HALF_OPEN — allow one probe, success/failure will decide
            return True


# ── @circuit_breaker decorator ────────────────────────────────────────────


def circuit_breaker(*, failures: int = 3, reset_timeout: float = 30.0):
    """Open the circuit after *failures* consecutive failures.

    Once open, all calls are blocked for *reset_timeout* seconds.  After
    the timeout, the next call is a half-open probe: success closes the
    circuit; failure re-opens it.

    Args:
        failures: Consecutive failures before opening the circuit.
        reset_timeout: Seconds to wait before probing (half-open).
    """
    state = _CircuitState()

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not state.allow_request(reset_timeout):
                raise CircuitBreakerOpen(
                    f"Circuit open for {func.__name__} "
                    f"(reset in {reset_timeout:.0f}s)"
                )
            try:
                result = func(*args, **kwargs)
            except Exception:
                state.record_failure(failures)
                raise
            state.record_success()
            return result

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not state.allow_request(reset_timeout):
                raise CircuitBreakerOpen(
                    f"Circuit open for {func.__name__} "
                    f"(reset in {reset_timeout:.0f}s)"
                )
            try:
                result = await func(*args, **kwargs)
            except Exception:
                state.record_failure(failures)
                raise
            state.record_success()
            return result

        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return wrapper  # type: ignore[return-value]

    return decorator


# ── Error types ────────────────────────────────────────────────────────────


class RateLimitExceeded(RuntimeError):
    """Raised when a rate-limited function is called too quickly."""


class CircuitBreakerOpen(RuntimeError):
    """Raised when a circuit-broken function is called while the circuit is open."""
