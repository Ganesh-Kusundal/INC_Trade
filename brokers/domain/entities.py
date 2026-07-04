"""Domain entities — frozen value objects representing trading concepts.

All entities are immutable dataclasses. They have zero dependencies on
infrastructure, frameworks, or external packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from brokers.domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from brokers.domain.error_codes import IDEMPOTENCY_CONFLICT, LIVE_ORDERS_DISABLED
from brokers.domain.validators.order_validator import (
    validate_exchange,
    validate_limit_price,
    validate_price,
    validate_quantity,
    validate_symbol,
    validate_trigger_price,
)


@dataclass(frozen=True)
class OrderRequest:
    """Value object for order placement request — replaces PlaceOrderRequest in use cases."""

    symbol: str
    exchange: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    price: Decimal = Decimal("0")
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    trigger_price: Decimal = Decimal("0")
    correlation_id: str = ""


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

    def validate(self) -> None:
        """Validate order business rules.

        Delegates to composable domain validators.

        Raises:
            ValidationError: If any validation rule is violated.
        """
        validate_symbol(self.symbol)
        validate_exchange(self.exchange)
        validate_quantity(self.quantity)
        validate_price(self.price)
        if self.order_type is OrderType.LIMIT:
            validate_limit_price(self.price)
        validate_trigger_price(self.trigger_price, self.order_type)

    def is_completed(self) -> bool:
        """Check if order lifecycle is complete (terminal state)."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )

    def is_active(self) -> bool:
        """Check if order is still active (can be modified/cancelled)."""
        return self.status in (
            OrderStatus.PENDING,
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
        )

    def can_modify(self) -> bool:
        """Check if order can be modified based on current state."""
        return self.is_active()

    def can_cancel(self) -> bool:
        """Check if order can be cancelled based on current state."""
        return self.is_active()

    def estimated_value(self) -> Decimal:
        """Calculate estimated order value (price × quantity)."""
        return self.price * self.quantity if self.price > 0 else Decimal("0")

    def remaining_quantity(self) -> int:
        """Calculate remaining quantity to be filled."""
        return max(0, self.quantity - self.filled_quantity)

    def fill_percentage(self) -> Decimal:
        """Calculate fill percentage as Decimal (0-100)."""
        if self.quantity <= 0:
            return Decimal("0")
        return Decimal(str(self.filled_quantity)) / Decimal(str(self.quantity)) * Decimal("100")


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
            error_code=LIVE_ORDERS_DISABLED,
        )

    @classmethod
    def already_executed(cls, order_id: str) -> OrderResponse:
        return cls(
            order_id=order_id,
            success=False,
            message="Order already executed (idempotency conflict)",
            error_code=IDEMPOTENCY_CONFLICT,
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
    seq_no: int = 0  # Monotonic sequence number (Kleppmann ordering guarantee)

    def is_stale(self, max_age_seconds: float = 5.0) -> bool:
        """Check if quote data is stale based on timestamp."""
        if self.timestamp is None:
            return True

        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > max_age_seconds

    def spread(self) -> Decimal:
        """Calculate bid-ask spread (returns 0 if data unavailable)."""
        return Decimal("0")  # Default for simplified Quote; MarketDepth has full spread

    def vwap(self) -> Decimal:
        """Calculate volume-weighted average price approximation."""
        if self.volume <= 0:
            return self.ltp
        return self.ltp  # Simplified; real VWAP needs trade-by-trade data


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

    def pnl_percentage(self) -> Decimal:
        """Calculate P&L as percentage of investment."""
        if self.average_price <= 0:
            return Decimal("0")
        return (self.unrealized_pnl / self.average_price) * Decimal("100")

    def is_profitable(self) -> bool:
        """Check if position is in profit."""
        return self.unrealized_pnl > 0

    def is_lossy(self) -> bool:
        """Check if position is in loss."""
        return self.unrealized_pnl < 0

    def net_quantity(self) -> int:
        """Calculate net position quantity."""
        return self.quantity


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
class InstrumentInfo:
    symbol: str
    exchange: str
    segment: str = ""
    name: str = ""
    lot_size: int = 1


@dataclass(frozen=True)
class RiskCheckRequest:
    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal = Decimal("0")
    order_type: OrderType = OrderType.MARKET


@dataclass(frozen=True)
class RiskCheckResult:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class UserProfile:
    user_id: str = ""
    name: str = ""
    email: str = ""
    mobile: str = ""
    broker: str = ""


@dataclass(frozen=True)
class IpoInfo:
    company_name: str = ""
    symbol: str = ""
    status: str = ""
    price_min: Decimal = Decimal("0")
    price_max: Decimal = Decimal("0")


@dataclass(frozen=True)
class MutualFundHolding:
    name: str = ""
    units: Decimal = Decimal("0")
    current_value: Decimal = Decimal("0")


@dataclass(frozen=True)
class OptionLeg:
    """Single option leg (call or put) at a given strike."""

    ltp: Decimal | None
    oi: int
    volume: int
    iv: Decimal | None
    delta: Decimal | None
    theta: Decimal | None
    gamma: Decimal | None
    vega: Decimal | None
    security_id: int | None
    symbol: str


@dataclass(frozen=True)
class OptionStrike:
    """One row in the option chain — a strike price with CE and PE legs."""

    strike: Decimal
    call: OptionLeg
    put: OptionLeg


@dataclass(frozen=True)
class OptionChain:
    """Full option chain result."""

    underlying: str
    expiry: str
    spot: Decimal
    strikes: tuple[OptionStrike, ...]


@dataclass(frozen=True)
class NewsItem:
    headline: str = ""
    summary: str = ""
    source: str = ""
    timestamp: datetime | None = None
