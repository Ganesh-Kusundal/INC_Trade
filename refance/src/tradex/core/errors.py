"""Error model and exception hierarchy.

Every error in the SDK flows through this hierarchy.
Provider-specific errors are mapped to these canonical types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ErrorContext:
    """Additional context attached to any error."""

    provider: str = ""
    endpoint: str = ""
    request_id: str = ""
    http_status: int = 0
    raw_response: Any = None
    retryable: bool = False


class BrokerError(Exception):
    """Base exception for all Broker SDK errors."""

    def __init__(
        self,
        message: str,
        code: str = "",
        context: Optional[ErrorContext] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = context or ErrorContext()

    @property
    def retryable(self) -> bool:
        return self.context.retryable

    def with_context(self, **kwargs: Any) -> BrokerError:
        """Return a new error with updated context."""
        ctx = ErrorContext(
            provider=kwargs.get("provider", self.context.provider),
            endpoint=kwargs.get("endpoint", self.context.endpoint),
            request_id=kwargs.get("request_id", self.context.request_id),
            http_status=kwargs.get("http_status", self.context.http_status),
            raw_response=kwargs.get("raw_response", self.context.raw_response),
            retryable=kwargs.get("retryable", self.context.retryable),
        )
        return type(self)(self.args[0], code=self.code, context=ctx)


class AuthenticationError(BrokerError):
    """Invalid credentials, expired tokens, auth failures."""


class AccessError(BrokerError):
    """Insufficient permissions, inactive subscriptions, segment not activated."""


class ValidationError(BrokerError):
    """Invalid request parameters, missing fields, bad values."""


class OrderError(BrokerError):
    """Order cannot be processed — rejected, insufficient margin, etc."""


class RateLimitError(BrokerError):
    """Rate limit exceeded. Always retryable."""


class NetworkError(BrokerError):
    """Connection failure, timeout, DNS resolution failure."""


class IPWhitelistError(BrokerError):
    """Static IP not whitelisted for trading APIs."""


class DataError(BrokerError):
    """Data unavailable, parameters invalid for data endpoint."""


class InternalError(BrokerError):
    """Server-side failure at the broker."""


class ProviderError(BrokerError):
    """Catch-all for unmapped provider errors."""


class StreamError(BrokerError):
    """WebSocket connection, subscription, or parsing error."""


class SessionExpiredError(AuthenticationError):
    """Session has expired and requires re-authentication."""


class ConfigurationError(BrokerError):
    """Invalid configuration, missing required settings."""


# --- Error mapping helpers ---

_ERROR_MAP: dict[str, type[BrokerError]] = {
    "DH-901": AuthenticationError,
    "DH-902": AccessError,
    "DH-903": AccessError,
    "DH-904": RateLimitError,
    "DH-905": ValidationError,
    "DH-906": OrderError,
    "DH-907": DataError,
    "DH-908": InternalError,
    "DH-909": NetworkError,
    "DH-910": ProviderError,
    "DH-911": IPWhitelistError,
    "800": InternalError,
    "804": ValidationError,
    "805": RateLimitError,
    "806": AccessError,
    "807": AuthenticationError,
    "808": AuthenticationError,
    "809": AuthenticationError,
    "810": AuthenticationError,
    "811": ValidationError,
    "812": ValidationError,
    "813": ValidationError,
    "814": ValidationError,
}

_RETRYABLE_CODES: set[str] = {"DH-904", "800", "805", "DH-908", "DH-909"}


def map_provider_error(
    code: str,
    message: str,
    provider: str = "",
    http_status: int = 0,
    raw_response: Any = None,
) -> BrokerError:
    """Map a provider-specific error code to the canonical BrokerError hierarchy."""
    error_cls = _ERROR_MAP.get(code, ProviderError)
    retryable = code in _RETRYABLE_CODES
    ctx = ErrorContext(
        provider=provider,
        http_status=http_status,
        raw_response=raw_response,
        retryable=retryable,
    )
    return error_cls(message, code=code, context=ctx)
