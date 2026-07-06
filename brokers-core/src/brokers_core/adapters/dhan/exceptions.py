"""Dhan-specific exceptions mapping to domain exceptions.

All Dhan exceptions extend from the canonical BrokerError hierarchy.
Multiple inheritance ensures isinstance checks work correctly in global handlers.
"""

from brokers_core.domain.exceptions import (
    AuthenticationError,
    BrokerError,
    BrokerServerError,
    InstrumentNotFoundError,
    NetworkError,
    NotSupportedError,
    OrderRejectedError,
    RateLimitError,
)


class DhanError(BrokerError):
    """Base exception for all Dhan-specific errors."""

    pass


class DhanAuthenticationError(AuthenticationError, DhanError):
    """Dhan authentication failed or token invalid.

    Multiple inheritance allows catching via either AuthenticationError or DhanError.
    """

    pass


class DhanRateLimitError(RateLimitError, DhanError):
    """Dhan API rate limit exceeded."""

    pass


class DhanOrderRejectedError(OrderRejectedError, DhanError):
    """Dhan rejected the order."""

    pass


class DhanConnectionError(NetworkError, DhanError):
    """Dhan network/connection failure."""

    pass


class DhanServerError(BrokerServerError, DhanError):
    """Dhan API returned a 5xx error."""

    pass


class DhanInstrumentNotFoundError(InstrumentNotFoundError, DhanError):
    """Instrument not found in resolver cache."""

    pass


class DhanExitAllError(NotSupportedError, DhanError):
    """Exit all operation failure."""

    pass


class DhanOrderError(DhanError):
    """Order placement/modification/cancellation failure."""

    pass


class DhanMarketDataError(DhanError):
    """Market data fetch failure."""

    pass


class DhanConditionalTriggerError(DhanError):
    """Conditional trigger creation/modification/deletion failure."""

    pass


class DhanSuperOrderError(DhanError):
    """Super order placement/modification/cancellation failure."""

    pass


class DhanForeverOrderError(DhanError):
    """Forever order placement/modification/cancellation failure."""

    pass


class DhanLedgerError(DhanError):
    """Ledger fetch failure."""

    pass


class DhanUserProfileError(DhanError):
    """User profile fetch failure."""

    pass


class DhanIPManagementError(DhanError):
    """IP management operation failure."""

    pass


class DhanEDISError(DhanError):
    """eDIS/TPIN operation failure."""

    pass


class DhanConfigurationError(DhanError):
    """Missing or invalid configuration."""

    pass
