"""Domain layer — enterprise business rules with zero external dependencies.

Re-exports all domain types for convenient access::

    from brokers.domain import Order, Side, OrderStatus, BrokerError
"""

from brokers.domain.entities import (
    Balance,
    Candle,
    DepthLevel,
    Holding,
    MarketDepth,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)
from brokers.domain.enums import (
    AuthMode,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from brokers.domain.exceptions import (
    AuthenticationError,
    BrokerDegradedError,
    BrokerError,
    BrokerServerError,
    CircuitOpenError,
    ConfigError,
    DataError,
    InstrumentNotFoundError,
    NetworkError,
    NonRetryableError,
    NotSupportedError,
    OrderRejectedError,
    RateLimitError,
    RetryableError,
    TradeXV2Error,
    ValidationError,
)
from brokers.domain.order_lifecycle import OrderStateError

__all__ = [
    "AuthenticationError",
    "AuthMode",
    "Balance",
    "BrokerDegradedError",
    "BrokerError",
    "BrokerServerError",
    "Candle",
    "CircuitOpenError",
    "ConfigError",
    "DataError",
    "DepthLevel",
    "Holding",
    "InstrumentNotFoundError",
    "MarketDepth",
    "NetworkError",
    "NonRetryableError",
    "NotSupportedError",
    "Order",
    "OrderRejectedError",
    "OrderResponse",
    "OrderStateError",
    "OrderStatus",
    "OrderType",
    "Position",
    "ProductType",
    "Quote",
    "RateLimitError",
    "RetryableError",
    "Side",
    "Trade",
    "TradeXV2Error",
    "ValidationError",
    "Validity",
]
