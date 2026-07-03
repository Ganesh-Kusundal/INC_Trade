"""Dhan-specific exceptions mapping to domain exceptions."""

from brokers.domain.exceptions import (
    AuthenticationError,
    BrokerError,
    BrokerServerError,
    NetworkError,
    OrderRejectedError,
    RateLimitError,
)


class DhanError(BrokerError):
    """Base exception for all Dhan-specific errors."""


class DhanAuthenticationError(AuthenticationError):
    """Dhan authentication failed or token invalid."""


class DhanRateLimitError(RateLimitError):
    """Dhan API rate limit exceeded."""


class DhanOrderRejectedError(OrderRejectedError):
    """Dhan rejected the order."""


class DhanConnectionError(NetworkError):
    """Dhan network/connection failure."""


class DhanServerError(BrokerServerError):
    """Dhan API returned a 5xx error."""
