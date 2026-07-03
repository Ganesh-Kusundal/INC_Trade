"""Ports layer — interfaces for dependency inversion.

All ports are Protocols (structural typing). Broker adapters implement
these interfaces. Services depend on these abstractions, not concretions.
"""

from brokers.ports.auth import AuthPort
from brokers.ports.broker import BrokerGateway
from brokers.ports.capabilities import (
    ConditionalTriggerProvider,
    EDISTransferProvider,
    ForeverOrderProvider,
    IPManagementProvider,
    LedgerProvider,
    MarginProvider,
    ReconciliationProvider,
    SuperOrderProvider,
    UserProfileProvider,
)
from brokers.ports.clock import ClockPort, SystemClock
from brokers.ports.extensions import BrokerExtension, get_extension, supports_extension
from brokers.ports.historical import HistoricalPort
from brokers.ports.instruments import InstrumentInfo, InstrumentPort
from brokers.ports.market_data import MarketDataPort
from brokers.ports.order_execution import OrderExecutionPort
from brokers.ports.portfolio import PortfolioPort
from brokers.ports.risk_manager import RiskManagerPort
from brokers.ports.streaming import StreamingPort

__all__ = [
    "AuthPort",
    "BrokerExtension",
    "BrokerGateway",
    "ClockPort",
    "ConditionalTriggerProvider",
    "EDISTransferProvider",
    "ForeverOrderProvider",
    "HistoricalPort",
    "InstrumentInfo",
    "InstrumentPort",
    "IPManagementProvider",
    "LedgerProvider",
    "MarginProvider",
    "MarketDataPort",
    "OrderExecutionPort",
    "PortfolioPort",
    "ReconciliationProvider",
    "RiskManagerPort",
    "StreamingPort",
    "SuperOrderProvider",
    "SystemClock",
    "UserProfileProvider",
    "get_extension",
    "supports_extension",
]
