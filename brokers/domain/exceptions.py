"""Domain exceptions — broker-agnostic error types.

These exceptions represent business-level failures that any broker adapter
can raise. They form a hierarchy rooted at BrokerError.
"""

from __future__ import annotations


class BrokerError(Exception):
    def __init__(self, message: str, code: str = "") -> None:
        self.code = code
        super().__init__(message)


class BrokerServerError(BrokerError):
    pass


class OrderRejectedError(BrokerError):
    def __init__(self, message: str, order_id: str = "", code: str = "") -> None:
        self.order_id = order_id
        super().__init__(message, code=code)


class RateLimitError(BrokerError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(message, code="RATE_LIMITED")


class CircuitOpenError(BrokerError):
    def __init__(self, message: str = "Circuit breaker is open") -> None:
        super().__init__(message, code="CIRCUIT_OPEN")


class AuthenticationError(BrokerError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, code="AUTH_ERROR")


class InstrumentNotFoundError(BrokerError):
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(f"Instrument not found: {symbol}", code="INSTRUMENT_NOT_FOUND")
