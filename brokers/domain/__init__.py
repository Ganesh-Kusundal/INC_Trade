"""Domain layer — pure business entities, value objects, and enums.

Zero dependencies on external libraries, frameworks, or broker APIs.
All entities are rich domain objects with behavior. No anemic data bags.
"""

# Enums
from brokers.domain.enums import (
    AssetClass,
    Exchange,
    InstrumentType,
    OptionType,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)

# Exceptions
from brokers.domain.exceptions import (
    DomainError,
    InstrumentNotFoundError,
    NotSupportedError,
    ProviderError,
    RiskDeniedError,
    SubscriptionError,
)

# Value objects
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

# Requests
from brokers.domain.requests import (
    ModifyOrderRequest,
    OrderRequest,
)

# Historical
from brokers.domain.historical import (
    BarLabelConvention,
    DateRange,
    Gap,
    HistoricalBar,
    HistoricalSeries,
)

# Capabilities
from brokers.domain.capabilities import (
    Capability,
    ProviderCapabilities,
)

# Rich domain objects (imported lazily to avoid circular deps at module level)
from brokers.domain.instrument import Instrument, InstrumentIdentity
from brokers.domain.order import Order, InvalidOrderTransitionError
from brokers.domain.account import Account
from brokers.domain.option_chain import (
    FutureChain,
    FutureContract,
    OptionChain,
    OptionContract,
)

# Events (retained from existing — still correct)
from brokers.domain.events import (
    EVENT_PAYLOADS,
    DomainEvent,
    EventPayload,
    EventType,
    canonical_event_types,
    make_payload,
)

# Exchange segments (retained — still correct)
from brokers.domain.exchange_segments import (
    ExchangeSegment,
    canonical_exchange_short,
    is_commodity_segment,
    is_currency_segment,
    is_derivative_segment,
    is_equity_segment,
    parse_segment,
    wire_value,
)

# Symbols (retained — still correct)
from brokers.domain.symbols import (
    make_instrument_key,
    make_position_key,
    normalize_exchange,
    normalize_symbol,
)

# Stream health (retained — still correct)
from brokers.domain.stream_health import (
    FreshnessState,
    StreamHealth,
    StreamSession,
    StreamStateSummary,
    SubscriptionState,
    TransportState,
)

__all__ = [
    # Enums
    "AssetClass",
    "Exchange",
    "OptionType",
    "OrderStatus",
    "OrderType",
    "ProductType",
    "Side",
    "Validity",
    "InstrumentType",
    # Exceptions
    "DomainError",
    "InstrumentNotFoundError",
    "NotSupportedError",
    "ProviderError",
    "RiskDeniedError",
    "SubscriptionError",
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
    "ModifyOrderRequest",
    "OrderRequest",
    # Historical
    "BarLabelConvention",
    "DateRange",
    "Gap",
    "HistoricalBar",
    "HistoricalSeries",
    # Capabilities
    "Capability",
    "ProviderCapabilities",
    # Rich domain objects
    "Account",
    "Instrument",
    "InstrumentIdentity",
    "InvalidOrderTransitionError",
    "Order",
    "FutureChain",
    "FutureContract",
    "OptionChain",
    "OptionContract",
    # Events
    "EVENT_PAYLOADS",
    "DomainEvent",
    "EventPayload",
    "EventType",
    "canonical_event_types",
    "make_payload",
    # Exchange segments
    "ExchangeSegment",
    "canonical_exchange_short",
    "is_commodity_segment",
    "is_currency_segment",
    "is_derivative_segment",
    "is_equity_segment",
    "parse_segment",
    "wire_value",
    # Symbols
    "make_instrument_key",
    "make_position_key",
    "normalize_exchange",
    "normalize_symbol",
    # Stream health
    "FreshnessState",
    "StreamHealth",
    "StreamSession",
    "StreamStateSummary",
    "SubscriptionState",
    "TransportState",
]
