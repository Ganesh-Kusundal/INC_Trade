"""Domain exceptions — full hierarchy rooted at TradeXV2Error.

Inner-layer exceptions that every layer can raise/catch without reaching
into infrastructure. Broker-specific errors inherit from BrokerError;
platform-level errors (config, data, validation) inherit directly from
TradeXV2Error.
"""

from __future__ import annotations

from typing import Any

from brokers.domain.error_codes import (
    AUTH_ERROR,
    BROKER_DEGRADED,
    BROKER_SERVER,
    CIRCUIT_OPEN,
    IDEMPOTENCY_CONFLICT,
    INSTRUMENT_NOT_FOUND,
    INVALID_INPUT,
    LIVE_ORDERS_DISABLED,
    NETWORK_ERROR,
    NOT_SUPPORTED,
    ORDER_REJECTED,
    RATE_LIMITED,
)


class TradeXV2Error(Exception):
    """Root exception for all TradeXV2 errors."""


class ConfigError(TradeXV2Error):
    """Configuration error (missing or invalid settings)."""


class DataError(TradeXV2Error):
    """Data processing or datalake error."""


class ValidationError(TradeXV2Error):
    """Input validation error."""


class BrokerError(TradeXV2Error):
    """Base broker error with optional error code."""

    def __init__(self, message: str, code: str = "") -> None:
        self.code = code
        super().__init__(message)


class RetryableError(BrokerError):
    """Transient error that may succeed on retry."""


class NonRetryableError(BrokerError):
    """Permanent error that will not succeed on retry."""


class NetworkError(RetryableError):
    """Transport-level failure (connection reset, timeout, DNS)."""

    def __init__(self, message: str, code: str = NETWORK_ERROR) -> None:
        super().__init__(message, code=code)


class BrokerServerError(BrokerError):
    """HTTP 5xx or unexpected server response."""

    def __init__(self, message: str, code: str = BROKER_SERVER) -> None:
        super().__init__(message, code=code)


class OrderRejectedError(BrokerError):
    """Order rejected by validation or broker."""

    def __init__(self, message: str, order_id: str = "", code: str = ORDER_REJECTED) -> None:
        self.order_id = order_id
        super().__init__(message, code=code)


class RateLimitError(BrokerError):
    """HTTP 429 — broker rate limit exceeded."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(message, code=RATE_LIMITED)


class CircuitOpenError(BrokerError):
    """Circuit breaker is open — requests blocked."""

    def __init__(self, message: str = "Circuit breaker is open") -> None:
        super().__init__(message, code=CIRCUIT_OPEN)


class AuthenticationError(BrokerError):
    """Token expired or invalid credentials."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, code=AUTH_ERROR)


class TokenRateLimitError(BrokerError):
    """Token generation rate limit exceeded (e.g., Dhan's 2-minute cooldown)."""

    def __init__(self, message: str = "Token generation rate limit exceeded") -> None:
        super().__init__(message, code=RATE_LIMITED)


class InstrumentNotFoundError(BrokerError):
    """Symbol could not be resolved to a broker instrument."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(f"Instrument not found: {symbol}", code=INSTRUMENT_NOT_FOUND)


class NotSupportedError(BrokerError):
    """Operation not supported by this broker or adapter."""

    def __init__(self, message: str = "Operation not supported") -> None:
        super().__init__(message, code=NOT_SUPPORTED)


class BrokerDegradedError(BrokerError):
    """Broker is in a degraded state (health below threshold)."""

    def __init__(
        self, message: str, health_status: dict[str, Any] | None = None
    ) -> None:
        self.health_status = health_status or {}
        super().__init__(message, code=BROKER_DEGRADED)


class InvalidInputError(BrokerError):
    """Invalid input provided to broker API."""

    def __init__(self, message: str = "Invalid input") -> None:
        super().__init__(message, code=INVALID_INPUT)


class IdempotencyConflictError(BrokerError):
    """Duplicate order detected — idempotency key already used."""

    def __init__(self, message: str = "Idempotency conflict") -> None:
        super().__init__(message, code=IDEMPOTENCY_CONFLICT)


class LiveOrdersDisabledError(BrokerError):
    """Live orders are disabled for this broker or session."""

    def __init__(self, message: str = "Live orders disabled") -> None:
        super().__init__(message, code=LIVE_ORDERS_DISABLED)
