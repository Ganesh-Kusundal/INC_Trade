"""Upstox capability groups — deep modules composing adapter clusters."""

from brokers.upstox.capabilities.instruments import InstrumentsCapability
from brokers.upstox.capabilities.market_data import MarketDataCapability
from brokers.upstox.capabilities.orders import OrdersCapability
from brokers.upstox.capabilities.portfolio import PortfolioCapability
from brokers.upstox.capabilities.snapshot import upstox_capabilities
from brokers.upstox.capabilities.streaming import StreamingCapability

__all__ = [
    "InstrumentsCapability",
    "MarketDataCapability",
    "OrdersCapability",
    "PortfolioCapability",
    "StreamingCapability",
    "upstox_capabilities",
]
