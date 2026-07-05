"""Backward-compatible BrokerGateway protocol — moved from ports/.

.. deprecated:: 3.0.0
   ``BrokerGateway`` was the legacy monolithic gateway interface. New code
   should use the ``BrokerSession`` (returned by ``brokers.connect()``) and
   access capabilities via named port properties (``session.orders``,
   ``session.market``, ``session.streaming``, etc.).

   The protocol is retained here for adapter compatibility during migration.
   It will be removed in a future release.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from inc_trade.domain.capabilities import BrokerCapabilities
from inc_trade.ports.auth import AuthPort
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

    Brokers implement this interface to provide access to their services.
    Clients should depend on this abstraction, not on concrete broker implementations.

    .. deprecated:: 3.0.0
       Use ``BrokerSession`` returned by ``brokers.connect()`` instead.
    """

    @property
    def broker_id(self) -> str:
        """Unique identifier for this broker (e.g., 'dhan', 'upstox')."""
        ...

    def capabilities(self) -> BrokerCapabilities:
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
