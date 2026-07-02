"""Ports layer — interfaces for dependency inversion.

All ports are Protocols (structural typing). Broker adapters implement
these interfaces. Services depend on these abstractions, not concretions.
"""

from brokers.ports.auth import AuthPort
from brokers.ports.broker import BrokerGateway
from brokers.ports.clock import ClockPort, SystemClock
from brokers.ports.instruments import InstrumentInfo, InstrumentPort
from brokers.ports.market_data import MarketDataPort
from brokers.ports.order_execution import OrderExecutionPort
from brokers.ports.portfolio import PortfolioPort

__all__ = [
    "AuthPort",
    "BrokerGateway",
    "ClockPort",
    "InstrumentInfo",
    "InstrumentPort",
    "MarketDataPort",
    "OrderExecutionPort",
    "PortfolioPort",
    "SystemClock",
]
