"""Core broker gateway interface.

This is the primary contract that all broker adapters must implement.
It provides access to all core services through properties, enabling
dependency injection and capability-based feature discovery.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from inc_trade.ports.auth import AuthPort
from inc_trade.ports.capabilities import Capabilities
from inc_trade.ports.extension_registry import ExtensionRegistryPort
from inc_trade.ports.historical import HistoricalPort
from inc_trade.ports.instruments import InstrumentPort
from inc_trade.ports.market_data import MarketDataPort
from inc_trade.ports.options import OptionsPort
from inc_trade.ports.order_execution import OrderExecutionPort
from inc_trade.ports.portfolio import PortfolioPort
from inc_trade.ports.streaming import StreamingPort


@runtime_checkable
class BrokerGateway(Protocol):
    """Primary interface for all broker adapters.

    .. deprecated::
        ``BrokerGateway`` is being replaced by :class:`BrokerSession`.
        New code should use ``BrokerSession`` as the composition root and
        access individual ports (``session.orders``, ``session.market_data``,
        etc.) directly. The gateway pattern will be removed in a future release.

    Brokers implement this interface to provide access to their services.
    Clients should depend on this abstraction, not on concrete broker implementations.
    """

    @property
    def broker_id(self) -> str:
        """Unique identifier for this broker (e.g., 'dhan', 'upstox')."""
        ...

    def capabilities(self) -> Capabilities:
        """Feature discovery interface."""
        ...

    @property
    def orders(self) -> OrderExecutionPort:
        """Order execution service."""
        ...

    @property
    def market_data(self) -> MarketDataPort:
        """Market data service."""
        ...

    @property
    def portfolio(self) -> PortfolioPort:
        """Portfolio and positions service."""
        ...

    @property
    def historical(self) -> HistoricalPort:
        """Historical data service."""
        ...

    @property
    def instruments(self) -> InstrumentPort:
        """Instrument master service."""
        ...

    @property
    def options(self) -> OptionsPort | None:
        """Options/derivatives service (None if not supported)."""
        ...

    @property
    def auth(self) -> AuthPort:
        """Authentication service."""
        ...

    @property
    def streaming(self) -> StreamingPort:
        """Streaming/real-time data service."""
        ...

    @property
    def extensions(self) -> ExtensionRegistryPort:
        """Broker-specific extensions registry."""
        ...

    def close(self) -> None:
        """Close connections and release resources."""
        ...
