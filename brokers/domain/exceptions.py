"""Domain exceptions — single hierarchy with no external dependencies.

Every exception that crosses a layer boundary is a subclass of
:class:`DomainError`.  Infrastructure errors (HTTP, WebSocket) are caught
by the provider and re-raised as :class:`ProviderError`.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-layer errors."""


class InstrumentNotFoundError(DomainError):
    """Instrument not found in the broker's instrument master."""

    def __init__(self, symbol: str, exchange: str = "") -> None:
        self.symbol = symbol
        self.exchange = exchange
        super().__init__(f"Instrument not found: {symbol}:{exchange}" if exchange else symbol)


class NotSupportedError(DomainError):
    """The provider does not support this operation.

    Data-only providers (CSV, Yahoo) raise this for execution methods
    rather than implementing a separate protocol.
    """

    def __init__(self, operation: str, provider: str = "") -> None:
        self.operation = operation
        self.provider = provider
        msg = f"Operation not supported: {operation}"
        if provider:
            msg += f" (provider: {provider})"
        super().__init__(msg)


class ProviderError(DomainError):
    """Provider infrastructure error (HTTP, WebSocket, auth)."""

    def __init__(self, message: str, *, error_code: str = "") -> None:
        self.error_code = error_code
        super().__init__(message)


class RiskDeniedError(DomainError):
    """Risk policy denied an order.

    Raised by :class:`RiskPolicy.check()` when a pre-trade rule is violated.
    Account catches this and converts it to ``OrderResponse.fail()``.
    """

    def __init__(self, reason: str, *, error_code: str = "") -> None:
        self.reason = reason
        self.error_code = error_code
        super().__init__(reason)


class SubscriptionError(DomainError):
    """Streaming subscription error."""


__all__ = [
    "DomainError",
    "InstrumentNotFoundError",
    "NotSupportedError",
    "ProviderError",
    "RiskDeniedError",
    "SubscriptionError",
]
