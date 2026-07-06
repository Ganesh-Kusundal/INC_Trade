"""Ports layer — interfaces for dependency inversion.

All ports are Protocols (structural typing). Broker adapters implement
these interfaces. Services depend on these abstractions, not concretions.
"""

from inc_trade.domain.constants.capabilities import (
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
from inc_trade.extensions import DepthExtension, Extension
from inc_trade.ports.auth import AuthPort
from inc_trade.ports.capabilities import (
    Capabilities,
    ForeverOrderProvider,
    KillSwitchProvider,
    MarginProvider,
    NewsProvider,
    SliceOrderProvider,
    SuperOrderProvider,
)
from inc_trade.ports.clock import ClockPort, SystemClock
from inc_trade.ports.connection_lifecycle import ConnectionLifecyclePort
from inc_trade.ports.event_publisher import EventPublisherPort
from inc_trade.ports.extension_registry import ExtensionRegistry, ExtensionRegistryPort
from inc_trade.ports.historical import HistoricalPort
from inc_trade.ports.http_client_port import HttpClientPort
from inc_trade.ports.instruments import InstrumentInfo, InstrumentPort
from inc_trade.ports.market_data import MarketDataPort
from inc_trade.ports.options import OptionsPort
from inc_trade.ports.order_execution import OrderExecutionPort
from inc_trade.ports.portfolio import PortfolioPort
from inc_trade.ports.risk_manager import RiskManagerPort
from inc_trade.ports.streaming import StreamHandle, StreamingPort
from inc_trade.ports.token_store import TokenStorePort as TokenStorePort
from inc_trade.ports.wire_mapper import WireMapper

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
    "PortfolioPort",
    "RiskManagerPort",
    "SliceOrderProvider",
    "StreamHandle",
    "StreamingPort",
    "SuperOrderProvider",
    "SystemClock",
    "TokenStorePort",
    "WireMapper",
]
