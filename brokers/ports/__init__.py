"""Ports layer — interfaces for dependency inversion.

All ports are Protocols (structural typing). Broker adapters implement
these interfaces. Services depend on these abstractions, not concretions.
"""

from brokers.ports.auth import AuthPort
from brokers.ports.broker import BrokerGateway
from brokers.ports.capabilities import (
    ForeverOrderProvider,
    MarginProvider,
    SuperOrderProvider,
    KillSwitchProvider,
    SliceOrderProvider,
    NewsProvider,
)
from brokers.ports.clock import ClockPort, SystemClock
from brokers.ports.connection_lifecycle import ConnectionLifecyclePort
from brokers.ports.event_publisher import EventPublisherPort
from brokers.ports.extension_registry import ExtensionRegistry, ExtensionRegistryPort
from brokers.ports.historical import HistoricalPort
from brokers.ports.http_client_port import HttpClientPort
from brokers.ports.instruments import InstrumentInfo, InstrumentPort
from brokers.ports.market_data import MarketDataPort
from brokers.ports.order_execution import OrderExecutionPort
from brokers.ports.portfolio import PortfolioPort
from brokers.ports.options import OptionsPort
from brokers.ports.risk_manager import RiskManagerPort
from brokers.ports.streaming import StreamHandle, StreamingPort
from brokers.ports.token_store import TokenStorePort as TokenStorePort

__all__ = [
    "AuthPort",
    "BrokerGateway",
    "ClockPort",
    "ConnectionLifecyclePort",
    "EventPublisherPort",
    "ExtensionRegistry",
    "ExtensionRegistryPort",
    "ForeverOrderProvider",
    "HistoricalPort",
    "HttpClientPort",
    "InstrumentInfo",
    "InstrumentPort",
    "MarginProvider",
    "MarketDataPort",
    "OrderExecutionPort",
    "OptionsPort",
    "PortfolioPort",
    "RiskManagerPort",
    "StreamHandle",
    "StreamingPort",
    "SuperOrderProvider",
    "KillSwitchProvider",
    "SliceOrderProvider",
    "NewsProvider",
    "SystemClock",
    "TokenStorePort",
]
