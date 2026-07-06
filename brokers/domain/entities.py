"""Domain entities — frozen value objects representing trading concepts.

All entities are immutable dataclasses. They have zero dependencies on
infrastructure, frameworks, or external packages.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal

from brokers.domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from brokers.domain.error_codes import IDEMPOTENCY_CONFLICT, LIVE_ORDERS_DISABLED


@dataclass(frozen=True, kw_only=True)
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

    def propose_transition(self, new_status: OrderStatus) -> Order:
        """Return a new ``Order`` with ``new_status`` if the transition is legal.

        Validates against the canonical state machine in
        :mod:`brokers.domain.order_lifecycle`. The original is never mutated.

        Args:
            new_status: The proposed next status.

        Returns:
            A new ``Order`` with the updated status (all other fields preserved).

        Raises:
            OrderStateError: If the transition is illegal for the current status.
        """
        from brokers.domain.order_lifecycle import validate_transition

        validate_transition(self.status, new_status)
        return replace(self, status=new_status)


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
    """Rich immutable quote value object with computed properties."""

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
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    bid_qty: int = 0
    ask_qty: int = 0
    oi: int = 0

    def is_stale(self, max_age_seconds: float = 5.0) -> bool:
        """Check if quote data is stale based on timestamp."""
        if self.timestamp is None:
            return True
        age = (datetime.now(UTC) - self.timestamp).total_seconds()
        return age > max_age_seconds

    @property
    def spread(self) -> Decimal:
        """Bid-ask spread (ask - bid). Returns 0 if data unavailable."""
        if self.bid > 0 and self.ask > 0:
            return self.ask - self.bid
        return Decimal("0")

    @property
    def spread_bps(self) -> Decimal:
        """Bid-ask spread in basis points relative to mid price."""
        if self.bid > 0 and self.ask > 0:
            mid = (self.bid + self.ask) / 2
            if mid > 0:
                return (self.ask - self.bid) / mid * Decimal("10000")
        return Decimal("0")

    @property
    def vwap(self) -> Decimal:
        """Volume-weighted average price approximation."""
        if self.volume <= 0:
            return self.ltp
        return (self.high + self.low + self.ltp) / 3

    @property
    def change(self) -> Decimal:
        """Price change from previous close."""
        if self.close > 0:
            return self.ltp - self.close
        return Decimal("0")

    @property
    def change_pct(self) -> Decimal:
        """Percentage change from previous close."""
        if self.close > 0:
            return (self.ltp - self.close) / self.close * Decimal("100")
        return Decimal("0")

    @property
    def mid_price(self) -> Decimal:
        """Mid price between bid and ask. Falls back to ltp."""
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.ltp


@dataclass(frozen=True)
class DepthLevel:
    price: Decimal
    quantity: int
    orders: int = 0


@dataclass(frozen=True)
class MarketDepth:
    """Rich immutable market depth (order book) value object."""

    symbol: str
    bids: tuple[DepthLevel, ...] = ()
    asks: tuple[DepthLevel, ...] = ()
    exchange: str = ""
    timestamp: datetime | None = None
    oi: int = 0
    ltp: Decimal = Decimal("0")

    def __init__(
        self,
        symbol: str,
        bids: list[DepthLevel] | tuple[DepthLevel, ...] = (),
        asks: list[DepthLevel] | tuple[DepthLevel, ...] = (),
        exchange: str = "",
        timestamp: datetime | None = None,
        oi: int = 0,
        ltp: Decimal = Decimal("0"),
    ):
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "bids", tuple(bids))
        object.__setattr__(self, "asks", tuple(asks))
        object.__setattr__(self, "exchange", exchange)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "oi", oi)
        object.__setattr__(self, "ltp", ltp)

    @property
    def levels(self) -> int:
        """Number of depth levels available."""
        return max(len(self.bids), len(self.asks))

    @property
    def total_bid_qty(self) -> int:
        return sum(level.quantity for level in self.bids)

    @property
    def total_ask_qty(self) -> int:
        return sum(level.quantity for level in self.asks)

    @property
    def best_bid(self) -> Decimal:
        if not self.bids:
            return Decimal("0")
        return max(level.price for level in self.bids)

    @property
    def best_ask(self) -> Decimal:
        if not self.asks:
            return Decimal("0")
        return min(level.price for level in self.asks)

    @property
    def spread(self) -> Decimal:
        bb, ba = self.best_bid, self.best_ask
        if bb > 0 and ba > 0:
            return ba - bb
        return Decimal("0")

    @property
    def spread_bps(self) -> Decimal:
        bb, ba = self.best_bid, self.best_ask
        if bb > 0 and ba > 0:
            mid = (bb + ba) / 2
            if mid > 0:
                return (ba - bb) / mid * Decimal("10000")
        return Decimal("0")

    @property
    def bid_ask_ratio(self) -> Decimal:
        tbq, taq = self.total_bid_qty, self.total_ask_qty
        if taq > 0:
            return Decimal(str(tbq)) / Decimal(str(taq))
        return Decimal("0")

    @property
    def depth_imbalance(self) -> Decimal:
        tbq, taq = self.total_bid_qty, self.total_ask_qty
        total = tbq + taq
        if total > 0:
            return Decimal(str(tbq - taq)) / Decimal(str(total))
        return Decimal("0")


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
class FillResult:
    """Result of a fill detected by the broker's fill detection adapter.

    Attributes:
        order_id: Broker-assigned order identifier.
        symbol: Trading symbol filled.
        fill_quantity: Quantity filled in this execution.
        fill_price: Price at which the fill executed (or blank string if unknown).
        remaining_quantity: Quantity remaining after this fill.
        is_complete: True if the order is fully filled after this fill.
        exchange: Exchange code (optional, for multi-exchange fill tracking).
        fill_timestamp: The fill timestamp (or None if unknown).
    """

    order_id: str = ""
    symbol: str = ""
    fill_quantity: int = 0
    fill_price: str = ""
    remaining_quantity: int = 0
    is_complete: bool = False
    exchange: str = ""
    fill_timestamp: datetime | None = None


@dataclass(frozen=True)
class AggregatedExposure:
    """Net/gross exposure across multiple positions of one instrument.

    Computed by :meth:`~brokers.market.instrument.Instrument.aggregate_positions`.
    Zero-exposure instances are returned when no positions match the instrument.

    Attributes:
        symbol: Canonical instrument symbol.
        exchange: Exchange code.
        net_quantity: Long minus short (positive = net long; negative = net short).
        gross_quantity: Long plus short (always >= 0).
        long_quantity: Total long quantity (always >= 0).
        short_quantity: Total short quantity (always >= 0).
        position_count: Number of positions contributing to this aggregation.
    """

    symbol: str = ""
    exchange: str = ""
    net_quantity: int = 0
    gross_quantity: int = 0
    long_quantity: int = 0
    short_quantity: int = 0
    position_count: int = 0

    @property
    def is_flat(self) -> bool:
        """True when net_quantity is zero."""
        return self.net_quantity == 0


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
