"""Domain layer — enterprise business rules with zero external dependencies.

Re-exports all domain types for convenient access::

    from brokers.domain import Order, Side, OrderStatus, BrokerError
"""

from brokers.domain.entities import (
    Balance,
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
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from brokers.domain.exceptions import (
    AuthenticationError,
    BrokerError,
    BrokerServerError,
    CircuitOpenError,
    InstrumentNotFoundError,
    OrderRejectedError,
    RateLimitError,
)

__all__ = [
    "AuthenticationError",
    "Balance",
    "BrokerError",
    "BrokerServerError",
    "CircuitOpenError",
    "DepthLevel",
    "Holding",
    "InstrumentNotFoundError",
    "MarketDepth",
    "Order",
    "OrderRejectedError",
    "OrderResponse",
    "OrderStatus",
    "OrderType",
    "Position",
    "ProductType",
    "Quote",
    "RateLimitError",
    "Side",
    "Trade",
    "Validity",
]
