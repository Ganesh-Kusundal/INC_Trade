"""Dhan broker exceptions.

All Dhan-specific exceptions extend from the canonical ``BrokerError``
hierarchy in ``brokers.common.resilience.errors``.  Where a Dhan exception
shadows a common exception by name (e.g. ``AuthenticationError``), it uses
**multiple inheritance** to also extend the common counterpart — ensuring
that ``isinstance`` checks in the global exception handler and retry
framework match correctly.

The only exception class defined here that also exists in common is
``RateLimitError`` — we alias it to the canonical one to avoid the
silent-bug risk of catching the wrong class.

Usage::

    from brokers.dhan.exceptions import OrderError, InstrumentNotFoundError
    from brokers.common.resilience.errors import RateLimitError  # canonical
"""

from __future__ import annotations

from brokers.common.resilience.errors import (
    AuthenticationError as _CommonAuthenticationError,
)
from brokers.common.resilience.errors import (
    BrokerError,
    RateLimitError,
)
from brokers.common.resilience.errors import (
    ExitAllError as _CommonExitAllError,
)
from brokers.common.resilience.errors import (
    InstrumentNotFoundError as _CommonInstrumentNotFoundError,
)
from brokers.common.resilience.errors import (
    OrderError as _CommonOrderError,
)

# Re-export canonical RateLimitError so existing imports still work.
# New code should import directly from brokers.common.resilience.errors.
__all__ = [
    "AuthenticationError",
    "ConditionalTriggerError",
    "ConfigurationError",
    "DhanError",
    "DhanIdentityError",
    "EDISError",
    "ExitAllError",
    "ForeverOrderError",
    "IPManagementError",
    "InstrumentNotFoundError",
    "LedgerError",
    "MarketDataError",
    "OrderError",
    "RateLimitError",  # alias to canonical
    "SuperOrderError",
    "UserProfileError",
]


class DhanError(BrokerError):
    """Base exception for all Dhan broker errors.

    Extends the canonical ``BrokerError`` so that catching ``BrokerError``
    catches exceptions from any broker adapter.
    """


class InstrumentNotFoundError(DhanError, _CommonInstrumentNotFoundError):
    """Instrument not found in resolver cache.

    Inherits from both ``DhanError`` (broker scope) and the common
    ``InstrumentNotFoundError`` so that the global exception handler's
    ``isinstance`` check maps it to HTTP 404.
    """


class MarketDataError(DhanError):
    """Market data fetch failure."""


class OrderError(DhanError, _CommonOrderError):
    """Order placement/modification/cancellation failure.

    Inherits from both ``DhanError`` and the common ``OrderError`` so
    that the global exception handler maps it to HTTP 400.
    """


class AuthenticationError(DhanError, _CommonAuthenticationError):
    """Token expired or rejected.

    Inherits from both ``DhanError`` and the common ``AuthenticationError``
    so that the global exception handler maps it to HTTP 401.
    """


class ConfigurationError(DhanError):
    """Missing or invalid configuration."""


class DhanIdentityError(DhanError):
    """Non-Dhan identifier leaked into a Dhan payload or identity validation failure."""


# ── Feature-specific exceptions ──────────────────────────────────────────


class SuperOrderError(DhanError):
    """Super order placement/modification/cancellation failure."""


class ForeverOrderError(DhanError):
    """Forever order placement/modification/cancellation failure."""


class ConditionalTriggerError(DhanError):
    """Conditional trigger creation/modification/deletion failure."""


class LedgerError(DhanError):
    """Ledger fetch failure."""


class UserProfileError(DhanError):
    """User profile fetch failure."""


class IPManagementError(DhanError):
    """IP management operation failure."""


class ExitAllError(DhanError, _CommonExitAllError):
    """Exit all operation failure.

    Inherits from both ``DhanError`` and the common ``ExitAllError``
    (which extends ``NotSupportedError``) so that the global exception
    handler maps it to HTTP 501.
    """


class EDISError(DhanError):
    """eDIS/TPIN operation failure."""
