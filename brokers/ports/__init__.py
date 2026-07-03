"""Ports layer — interfaces for dependency inversion.

All ports are Protocols (structural typing). Broker adapters implement
these interfaces. Services depend on these abstractions, not concretions.
"""

from brokers.domain.constants.capabilities import (
    FEATURE_ALERTS,
    FEATURE_AUTH,
    FEATURE_BASKET_ORDERS,
    FEATURE_BRACKET_ORDERS,
    FEATURE_COVER_ORDERS,
    FEATURE_DEPTH200,
    FEATURE_EDIS,
    FEATURE_EXIT_ALL,
    FEATURE_FOREVER_ORDERS,
    FEATURE_GTT,
    FEATURE_HISTORICAL,
    FEATURE_INSTRUMENTS,
    FEATURE_MARGIN_CALCULATOR,
    FEATURE_MARKET_DATA,
    FEATURE_MTF,
    FEATURE_NEWS,
    FEATURE_ORDERS,
    FEATURE_PORTFOLIO,
    FEATURE_SLICE_ORDERS,
    FEATURE_STREAMING,
    FEATURE_SUPER_ORDERS,
)
from brokers.ports.auth import AuthPort
from brokers.ports.broker import BrokerGateway
from brokers.ports.capabilities import (
    Capabilities,
    ForeverOrderProvider,
    KillSwitchProvider,
    MarginProvider,
    NewsProvider,
    SliceOrderProvider,
    SuperOrderProvider,
)
from brokers.ports.clock import ClockPort, SystemClock
from brokers.ports.connection_lifecycle import ConnectionLifecyclePort
from brokers.ports.event_publisher import EventPublisherPort
from brokers.ports.extension_registry import ExtensionRegistry, ExtensionRegistryPort
from brokers.ports.historical import HistoricalPort
from brokers.ports.http_client_port import HttpClientPort
from brokers.ports.instruments import InstrumentInfo, InstrumentPort
from brokers.ports.market_data import MarketDataPort
from brokers.ports.options import OptionsPort
from brokers.ports.order_execution import OrderExecutionPort
from brokers.ports.portfolio import PortfolioPort
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
    "Capabilities",
    "FEATURE_ALERTS",
    "FEATURE_AUTH",
    "FEATURE_BASKET_ORDERS",
    "FEATURE_BRACKET_ORDERS",
    "FEATURE_COVER_ORDERS",
    "FEATURE_DEPTH200",
    "FEATURE_EDIS",
    "FEATURE_EXIT_ALL",
    "FEATURE_FOREVER_ORDERS",
    "FEATURE_GTT",
    "FEATURE_HISTORICAL",
    "FEATURE_INSTRUMENTS",
    "FEATURE_MARGIN_CALCULATOR",
    "FEATURE_MARKET_DATA",
    "FEATURE_MTF",
    "FEATURE_NEWS",
    "FEATURE_ORDERS",
    "FEATURE_PORTFOLIO",
    "FEATURE_SLICE_ORDERS",
    "FEATURE_STREAMING",
    "FEATURE_SUPER_ORDERS",
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
