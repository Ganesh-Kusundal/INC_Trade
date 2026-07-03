"""Core broker gateway interface.

This is the primary contract that all broker adapters must implement.
It provides access to all core services through properties, enabling
dependency injection and capability-based feature discovery.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from brokers.ports.auth import AuthPort
from brokers.ports.capabilities import Capabilities
from brokers.ports.extension_registry import ExtensionRegistryPort
from brokers.ports.historical import HistoricalPort
from brokers.ports.instruments import InstrumentPort
from brokers.ports.market_data import MarketDataPort
from brokers.ports.options import OptionsPort
from brokers.ports.order_execution import OrderExecutionPort
from brokers.ports.portfolio import PortfolioPort
from brokers.ports.streaming import StreamingPort


@runtime_checkable
class BrokerGateway(Protocol):
    """Primary interface for all broker adapters.

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
