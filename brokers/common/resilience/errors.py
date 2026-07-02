"""Custom exceptions for the resilience module and TradeXV2 core.

The root exception (:class:`TradeXV2Error`) and platform-level exceptions
(:class:`DataError`, :class:`ConfigError`, :class:`ValidationError`) live
in ``domain.exceptions`` — the canonical location.  This module re-exports
them for backward compatibility and defines broker-specific subclasses.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

# ── Canonical re-exports from domain ──────────────────────────────────────
from domain.exceptions import (  # noqa: F401  – re-exported for back-compat
    ConfigError as ConfigError,
    DataError as DataError,
    TradeXV2Error as TradeXV2Error,
    ValidationError as ValidationError,
)

logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])


class BrokerError(TradeXV2Error):
    """Base exception for all broker errors."""


class RetryableError(BrokerError):
    """An error that can be retried (transient failure)."""


# Alias used by the centralized retry framework (infrastructure.retry)
# and the global exception handler to distinguish retryable (transient)
# errors from fatal ones.
TradeXV2RecoverableError = RetryableError


class NonRetryableError(BrokerError):
    """An error that should NOT be retried (permanent failure)."""


class RateLimitError(BrokerError):
    """Rate limit exceeded."""


class CircuitBreakerOpenError(BrokerError):
    """The circuit breaker is open — request not allowed."""

    def __init__(self, name: str):
        self.circuit_name = name
        super().__init__(f"Circuit breaker '{name}' is open")


class AuthenticationError(BrokerError):
    """Authentication or authorization failure."""


class InstrumentNotFoundError(BrokerError):
    """Requested instrument not found."""


class OrderError(BrokerError):
    """Order placement, modification, or cancellation error."""


class NotSupportedError(BrokerError):
    """Feature not supported by broker (replaces NotImplementedError at boundaries)."""


class ExitAllError(NotSupportedError):
    """Exit-all (kill switch) operation failed."""


class BrokerDegradedError(BrokerError):
    """All brokers are unavailable and the system is in degraded mode.

    Raised when a write operation (e.g. order placement) is attempted
    while every configured broker is unhealthy. Read operations may
    return stale cached data instead of raising, depending on the
    caller's tolerance for stale data.
    """

    def __init__(
        self,
        message: str = "All brokers are unavailable; system is in degraded mode",
        health_status: dict[str, dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.health_status = health_status or {}


class NetworkError(RetryableError):
    """External network call failed (timeout, DNS, connection refused).

    This is the canonical exception for *transport-level* failures.
    Broker adapters should raise this (or a subclass) when the
    underlying HTTP/TCP call fails, so that the retry framework and
    circuit breakers can distinguish network failures from
    application-level errors.
    """


def convert_network_errors(
    error_factory: Callable[[Exception], NetworkError] | None = None,
) -> Callable[[F], F]:
    """Decorator that converts ``requests.RequestException`` → ``NetworkError``.

    Provides a standard infrastructure-level pattern for broker adapters:
    wrap the raw HTTP call so that callers only see domain exceptions,
    never transport-level ``requests`` exceptions.

    Usage::

        @convert_network_errors()
        def _send_raw_http(self, method, url, json):
            return self._session.request(...)

    Or with a custom error factory (e.g. broker-specific subclass)::

        @convert_network_errors(
            error_factory=lambda exc: DhanNetworkError(f"Dhan HTTP failed: {exc}")
        )
        def _send_raw_http(self, method, url, json):
            return self._session.request(...)

    Args:
        error_factory: Optional callable that creates a ``NetworkError``
            (or subclass) from the original ``RequestException``.
            Defaults to ``NetworkError(str(exc))``.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except ImportError:
                # requests is optional — if not installed, just pass through
                raise
            except Exception as exc:
                # Lazy import to avoid hard dependency on requests at
                # module-load time (some adapters may use httpx).
                try:
                    import requests as _requests
                except ImportError:
                    raise
                if isinstance(exc, _requests.RequestException):
                    if error_factory is not None:
                        raise error_factory(exc) from exc
                    raise NetworkError(
                        f"HTTP request failed: {exc}"
                    ) from exc
                raise

        return wrapper  # type: ignore[return-value]

    return decorator
