"""Domain entities — frozen value objects representing trading concepts.

All entities are immutable dataclasses. They have zero dependencies on
infrastructure, frameworks, or external packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from brokers.domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)


@dataclass(frozen=True)
class Order:
    order_id: str
    symbol: str
    exchange: str
    side: Side
    quantity: int
    status: OrderStatus
    price: Decimal = Decimal("0")
    trigger_price: Decimal = Decimal("0")
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    filled_quantity: int = 0
    message: str = ""
    timestamp: datetime | None = None
    correlation_id: str = ""


@dataclass(frozen=True)
class OrderResponse:
    order_id: str = ""
    success: bool = False
    message: str = ""
    status: OrderStatus = OrderStatus.PENDING
    error_code: str = ""

    @classmethod
    def fail(cls, message: str, error_code: str = "") -> OrderResponse:
        return cls(success=False, message=message, error_code=error_code)

    @classmethod
    def ok(cls, order_id: str, status: OrderStatus = OrderStatus.PENDING) -> OrderResponse:
        return cls(order_id=order_id, success=True, status=status)

    @classmethod
    def live_orders_disabled(cls) -> OrderResponse:
        return cls(
            success=False,
            message="Live order submission is disabled",
            error_code="LIVE_ORDERS_DISABLED",
        )

    @classmethod
    def already_executed(cls, order_id: str) -> OrderResponse:
        return cls(
            order_id=order_id,
            success=False,
            message="Order already executed (idempotency conflict)",
            error_code="IDEMPOTENCY_CONFLICT",
        )


@dataclass(frozen=True)
class Quote:
    symbol: str
    ltp: Decimal
    exchange: str = ""
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    timestamp: datetime | None = None


@dataclass(frozen=True)
class DepthLevel:
    price: Decimal
    quantity: int
    orders: int = 0


@dataclass(frozen=True)
class MarketDepth:
    symbol: str
    bids: tuple[DepthLevel, ...] = ()
    asks: tuple[DepthLevel, ...] = ()
    exchange: str = ""
    timestamp: datetime | None = None

    def __init__(
        self,
        symbol: str,
        bids: list[DepthLevel] | tuple[DepthLevel, ...] = (),
        asks: list[DepthLevel] | tuple[DepthLevel, ...] = (),
        exchange: str = "",
        timestamp: datetime | None = None,
    ):
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "bids", tuple(bids))
        object.__setattr__(self, "asks", tuple(asks))
        object.__setattr__(self, "exchange", exchange)
        object.__setattr__(self, "timestamp", timestamp)


@dataclass(frozen=True)
class Trade:
    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal
    timestamp: datetime | None = None


@dataclass(frozen=True)
class Position:
    symbol: str
    exchange: str
    quantity: int
    product_type: ProductType = ProductType.INTRADAY
    average_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")


@dataclass(frozen=True)
class Holding:
    symbol: str
    exchange: str
    quantity: int
    average_price: Decimal = Decimal("0")
    isin: str = ""
    t1_quantity: int = 0


@dataclass(frozen=True)
class Balance:
    available_cash: Decimal
    utilized_margin: Decimal = Decimal("0")
    total_margin: Decimal = Decimal("0")


@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

