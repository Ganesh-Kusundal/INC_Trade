"""Broker SDK — public API.

The central abstraction is Instrument, not the platform. Users interact with
rich domain objects that delegate IO to an injected Provider.

Usage::

    # Auto-login (recommended)
    from brokers import Platform
    platform = await Platform.connect("dhan")
    reliance = platform.instrument("NSE:RELIANCE")
    quote = await reliance.quote()

    # Manual token
    from brokers import Platform, Exchange
    platform = Platform.dhan(client_id="123", access_token="tok")
    reliance = platform.instrument("RELIANCE", Exchange.NSE)
    response = await reliance.buy(quantity=10)
"""

from brokers.platform import Platform

# Deprecated alias — use Platform instead
from brokers.broker import Broker  # noqa: F401
from brokers.domain.account import Account, RiskDecision
from brokers.domain.capabilities import Capability, ProviderCapabilities
from brokers.domain.enums import (
    AssetClass,
    Exchange,
    OptionType,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from brokers.domain.exceptions import (
    DomainError,
    InstrumentNotFoundError,
    NotSupportedError,
    ProviderError,
    RiskDeniedError,
)
from brokers.domain.historical import (
    DateRange,
    HistoricalBar,
    HistoricalSeries,
)
from brokers.domain.instrument import Instrument, InstrumentIdentity
from brokers.domain.option_chain import (
    FutureChain,
    FutureContract,
    OptionChain,
    OptionContract,
)
from brokers.domain.order import Order
from brokers.domain.requests import ModifyOrderRequest, OrderRequest
from brokers.domain.values import (
    Balance,
    DepthLevel,
    Greeks,
    Holding,
    MarketDepth,
    OrderResponse,
    Position,
    Quote,
    Subscription,
    Trade,
)
from brokers.provider.extensions import ExtensionAccess
from brokers.provider.protocol import (
    ExecutionProvider,
    LifecycleProvider,
    MarketDataProvider,
    Provider,
    StreamingProvider,
)
from brokers.provider.routing import RoutingStrategy
from brokers.risk import RiskPolicy

__all__ = [
    # Public API entry point
    "Platform",
    "Broker",  # Deprecated alias
    # Domain objects
    "Account",
    "Instrument",
    "InstrumentIdentity",
    "Order",
    "OptionChain",
    "OptionContract",
    "FutureChain",
    "FutureContract",
    # Provider (interface-segregated)
    "ExecutionProvider",
    "LifecycleProvider",
    "MarketDataProvider",
    "Provider",
    "StreamingProvider",
    "ProviderCapabilities",
    "Capability",
    "RoutingStrategy",
    "ExtensionAccess",
    # Risk
    "RiskPolicy",
    "RiskDecision",
    # Enums
    "AssetClass",
    "Exchange",
    "OptionType",
    "OrderStatus",
    "OrderType",
    "ProductType",
    "Side",
    "Validity",
    # Value objects
    "Balance",
    "DepthLevel",
    "Greeks",
    "Holding",
    "MarketDepth",
    "OrderResponse",
    "Position",
    "Quote",
    "Subscription",
    "Trade",
    # Requests
    "OrderRequest",
    "ModifyOrderRequest",
    # Historical
    "DateRange",
    "HistoricalBar",
    "HistoricalSeries",
    # Exceptions
    "DomainError",
    "InstrumentNotFoundError",
    "NotSupportedError",
    "ProviderError",
    "RiskDeniedError",
]
