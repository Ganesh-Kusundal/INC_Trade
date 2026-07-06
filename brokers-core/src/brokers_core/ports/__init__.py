"""Ports layer — interfaces for dependency inversion.

All ports are Protocols (structural typing). Broker adapters implement
these interfaces. Services depend on these abstractions, not concretions.
"""

from brokers_core.domain.constants.capabilities import (
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
from brokers_core.extensions import DepthExtension, Extension
from brokers_core.ports.auth import AuthPort
from brokers_core.ports.capabilities import (
    Capabilities,
    ForeverOrderProvider,
    KillSwitchProvider,
    MarginProvider,
    NewsProvider,
    SliceOrderProvider,
    SuperOrderProvider,
)
from brokers_core.ports.clock import ClockPort, SystemClock
from brokers_core.ports.connection_lifecycle import ConnectionLifecyclePort
from brokers_core.ports.event_publisher import EventPublisherPort
from brokers_core.ports.extension_registry import ExtensionRegistry, ExtensionRegistryPort
from brokers_core.ports.historical import HistoricalPort
from brokers_core.ports.http_client_port import HttpClientPort
from brokers_core.ports.instruments import InstrumentInfo, InstrumentPort
from brokers_core.ports.market_data import MarketDataPort
from brokers_core.ports.options import OptionsPort
from brokers_core.ports.order_execution import OrderExecutionPort
from brokers_core.ports.order_guard import OrderGuardPort
from brokers_core.ports.portfolio import PortfolioPort
from brokers_core.ports.risk_manager import RiskManagerPort
from brokers_core.ports.streaming import StreamHandle, StreamingPort
from brokers_core.ports.subscription import SubscriptionPort
from brokers_core.ports.token_store import TokenStorePort as TokenStorePort
from brokers_core.ports.wire_mapper import WireMapper

__all__ = [
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
    "AuthPort",
    "Capabilities",
    "ClockPort",
    "ConnectionLifecyclePort",
    "DepthExtension",
    "EventPublisherPort",
    "Extension",
    "ExtensionRegistry",
    "ExtensionRegistryPort",
    "ForeverOrderProvider",
    "HistoricalPort",
    "HttpClientPort",
    "InstrumentInfo",
    "InstrumentPort",
    "KillSwitchProvider",
    "MarginProvider",
    "MarketDataPort",
    "NewsProvider",
    "OptionsPort",
    "OrderExecutionPort",
    "OrderGuardPort",
    "PortfolioPort",
    "RiskManagerPort",
    "SliceOrderProvider",
    "StreamHandle",
    "StreamingPort",
    "SubscriptionPort",
    "SuperOrderProvider",
    "SystemClock",
    "TokenStorePort",
    "WireMapper",
]
