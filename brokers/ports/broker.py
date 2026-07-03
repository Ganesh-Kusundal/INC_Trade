"""Broker gateway port — composition of narrow ports (ISP).

This is the main interface that broker adapters implement. It composes
narrow ports rather than defining a fat interface, following the
Interface Segregation Principle.

Usage::

    from brokers.ports.broker import BrokerGateway

    def process(gw: BrokerGateway):
        price = gw.market_data.ltp("RELIANCE")
        resp = gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from brokers.domain.capabilities import BrokerCapabilities
from brokers.domain.enums import BrokerID
from brokers.ports.auth import AuthPort
from brokers.ports.historical import HistoricalPort
from brokers.ports.instruments import InstrumentPort
from brokers.ports.market_data import MarketDataPort
from brokers.ports.order_execution import OrderExecutionPort
from brokers.ports.portfolio import PortfolioPort
from brokers.ports.streaming import StreamingPort
from brokers.ports.options import OptionsPort


@runtime_checkable
class BrokerGateway(Protocol):
    @property
    def broker_id(self) -> BrokerID: ...

    """Canonical broker identifier (e.g., 'dhan', 'upstox')."""

    @property
    def orders(self) -> OrderExecutionPort: ...

    @property
    def market_data(self) -> MarketDataPort: ...

    @property
    def portfolio(self) -> PortfolioPort: ...

    @property
    def instruments(self) -> InstrumentPort: ...

    @property
    def auth(self) -> AuthPort: ...

    @property
    def historical(self) -> HistoricalPort: ...

    @property
    def streaming(self) -> StreamingPort: ...

    @property
    def options(self) -> OptionsPort: ...

    def capabilities(self) -> BrokerCapabilities: ...

    """Return broker capability matrix for feature discovery."""

    def close(self) -> None: ...
