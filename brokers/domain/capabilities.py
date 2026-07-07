"""Provider capabilities — declares what a provider supports.

Each provider declares a :class:`ProviderCapabilities` frozen dataclass.
The :class:`Instrument` and :class:`Account` objects check capabilities
before calling provider methods that may not be supported.

This replaces the old ``BrokerCapabilities`` class from ``common/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Capability(str, Enum):
    """Capability identifiers for feature gating.

    Core capabilities are supported by all real brokers.
    Extended capabilities are broker-specific and accessed via extensions.
    """

    # Core
    MARKET_DATA = "MARKET_DATA"
    HISTORICAL_DATA = "HISTORICAL_DATA"
    DEPTH = "DEPTH"
    OPTION_CHAIN = "OPTION_CHAIN"
    FUTURE_CHAIN = "FUTURE_CHAIN"
    STREAMING = "STREAMING"
    ORDER_PLACEMENT = "ORDER_PLACEMENT"
    ORDER_MODIFICATION = "ORDER_MODIFICATION"
    PORTFOLIO = "PORTFOLIO"
    INSTRUMENT_SEARCH = "INSTRUMENT_SEARCH"

    # Extended (accessed via extensions, not core API)
    DEPTH_20 = "DEPTH_20"
    DEPTH_30 = "DEPTH_30"
    FOREVER_ORDERS = "FOREVER_ORDERS"
    SUPER_ORDERS = "SUPER_ORDERS"
    GTT_ORDERS = "GTT_ORDERS"
    COVER_ORDERS = "COVER_ORDERS"
    SLICE_ORDERS = "SLICE_ORDERS"
    IPO = "IPO"
    MUTUAL_FUNDS = "MUTUAL_FUNDS"
    MARGIN_CALCULATION = "MARGIN_CALCULATION"
    EXIT_ALL = "EXIT_ALL"
    LEDGER = "LEDGER"
    EDIS = "EDIS"
    ALERTS = "ALERTS"
    NEWS = "NEWS"
    FUNDAMENTALS = "FUNDAMENTALS"
    MARKET_STATUS = "MARKET_STATUS"
    MARKET_INTELLIGENCE = "MARKET_INTELLIGENCE"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Declares what a provider supports.

    ``supported`` is a frozenset of :class:`Capability` values.
    ``supports()`` is the single check method used by Instrument/Account.
    """

    broker_id: str
    supported: frozenset[Capability] = field(default_factory=frozenset)
    is_primary: bool = False
    max_depth_levels: int = 5
    max_stream_symbols: int = 200

    def supports(self, capability: Capability | str) -> bool:
        """Check if a capability is supported."""
        if isinstance(capability, str):
            try:
                capability = Capability(capability)
            except ValueError:
                return False
        return capability in self.supported

    def supports_any(self, *capabilities: Capability) -> bool:
        """Check if any of the given capabilities are supported."""
        return any(c in self.supported for c in capabilities)

    @staticmethod
    def full(broker_id: str, **kwargs: Any) -> ProviderCapabilities:
        """All core capabilities supported (for real brokers)."""
        core = frozenset(
            {
                Capability.MARKET_DATA,
                Capability.HISTORICAL_DATA,
                Capability.DEPTH,
                Capability.OPTION_CHAIN,
                Capability.FUTURE_CHAIN,
                Capability.STREAMING,
                Capability.ORDER_PLACEMENT,
                Capability.ORDER_MODIFICATION,
                Capability.PORTFOLIO,
                Capability.INSTRUMENT_SEARCH,
            }
        )
        return ProviderCapabilities(
            broker_id=broker_id,
            supported=core,
            **kwargs,
        )

    @staticmethod
    def data_only(broker_id: str, **kwargs: Any) -> ProviderCapabilities:
        """Only market data, no execution (for CSV/Yahoo providers)."""
        return ProviderCapabilities(
            broker_id=broker_id,
            supported=frozenset(
                {Capability.MARKET_DATA, Capability.HISTORICAL_DATA}
            ),
            **kwargs,
        )

    @staticmethod
    def paper(broker_id: str = "paper", **kwargs: Any) -> ProviderCapabilities:
        """All core capabilities (paper trading simulates everything)."""
        return ProviderCapabilities.full(broker_id, **kwargs)


__all__ = [
    "Capability",
    "ProviderCapabilities",
]
