"""Execution domain — orders, legs, trades, and fills."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from tradex.domain.enums import (
    AMOTime,
    OrderLegName,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)


@dataclass
class OrderLeg:
    """A single leg of an order (for super/bracket orders).

    Super orders and bracket orders contain multiple legs: an entry
    leg, a target (take-profit) leg, and a stop-loss leg. Each leg
    has its own parameters and lifecycle.

    Attributes:
        leg_name: The leg role — ENTRY_LEG, TARGET_LEG, or STOP_LOSS_LEG.
        security_id: Broker-assigned security ID.
        side: Order side (BUY or SELL).
        order_type: Order type for this leg.
        product_type: Product type for this leg.
        quantity: Quantity for this leg.
        price: Limit price for this leg.
        trigger_price: Trigger price for SL legs.
        disclosed_quantity: Disclosed quantity.
        status: Current status of this leg.
    """

    leg_name: OrderLegName = OrderLegName.ENTRY_LEG
    security_id: str = ""
    side: Side = Side.BUY
    order_type: OrderType = OrderType.LIMIT
    product_type: ProductType = ProductType.INTRADAY
    quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal = Decimal("0")
    disclosed_quantity: int = 0
    status: OrderStatus = OrderStatus.PENDING

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrderLeg:
        """Construct an OrderLeg from a raw dictionary.

        Maps broker-specific field names to the canonical model.

        Args:
            data: Raw dictionary from broker API response.

        Returns:
            Populated OrderLeg instance.
        """
        return cls(
            leg_name=OrderLegName(data.get("legName", "ENTRY_LEG")),
            security_id=str(data.get("securityId", "")),
            side=Side(data.get("transactionType", "BUY")),
            order_type=OrderType(data.get("orderType", "LIMIT")),
            product_type=ProductType(data.get("productType", "INTRADAY")),
            quantity=int(data.get("quantity", 0)),
            price=Decimal(str(data.get("price", 0))),
            trigger_price=Decimal(str(data.get("triggerPrice", 0))),
            disclosed_quantity=int(data.get("disclosedQuantity", 0)),
            status=OrderStatus(data.get("orderStatus", "PENDING")),
        )


@dataclass
class Trade:
    """A single executed trade (fill).

    Represents one or more shares/contracts that were matched and
    executed on the exchange. A single order can produce multiple
    trades (partial fills).

    Attributes:
        trade_id: Broker-assigned unique trade ID.
        order_id: The order that produced this trade.
        correlation_id: User-defined correlation ID from the order.
        security_id: Broker-assigned security ID.
        trading_symbol: Human-readable trading symbol.
        side: Trade side (BUY or SELL).
        quantity: Number of shares/contracts traded.
        price: Execution price per unit.
        exchange_trade_id: Exchange-assigned trade identifier.
        traded_at: Timestamp of the trade.
        raw: Raw broker response data.
    """

    trade_id: str = ""
    order_id: str = ""
    correlation_id: str = ""
    security_id: str = ""
    trading_symbol: str = ""
    side: Side = Side.BUY
    quantity: int = 0
    price: Decimal = Decimal("0")
    exchange_trade_id: str = ""
    traded_at: Optional[datetime] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dhan(cls, data: dict[str, Any]) -> Trade:
        """Construct a Trade from a Dhan API response.

        Args:
            data: Raw dictionary from Dhan trade book API.

        Returns:
            Populated Trade instance.
        """
        return cls(
            trade_id=str(data.get("tradeNo", "")),
            order_id=str(data.get("orderId", "")),
            security_id=str(data.get("securityId", "")),
            trading_symbol=data.get("tradingSymbol", ""),
            side=Side(data.get("transactionType", "BUY")),
            quantity=int(data.get("quantity", 0)),
            price=Decimal(str(data.get("tradedPrice", 0))),
            exchange_trade_id=str(data.get("exchangeTradeNo", "")),
            raw=data,
        )

    @property
    def notional(self) -> Decimal:
        """Notional value of the trade (price × quantity).

        Returns:
            Total trade value as a Decimal.
        """
        return self.price * self.quantity


@dataclass
class Fill:
    """A fill (partial or complete) on an order.

    Tracks individual fill events as an order is executed.
    Multiple fills can occur for a single order.

    Attributes:
        fill_id: Unique fill identifier.
        trade_id: Associated trade ID.
        quantity: Number of units filled in this fill.
        price: Execution price for this fill.
        timestamp: When the fill occurred.
    """

    fill_id: str = ""
    trade_id: str = ""
    quantity: int = 0
    price: Decimal = Decimal("0")
    timestamp: Optional[datetime] = None


@dataclass
class Order:
    """Order aggregate root — manages the full order lifecycle.

    This is the primary execution domain object. It encapsulates
    all order parameters, tracks fill status, manages bracket
    order legs, and provides lifecycle queries.

    Attributes:
        order_id: Broker-assigned unique order identifier.
        correlation_id: User-defined tag for order tracking.
        parent_order_id: Parent order ID for bracket/super orders.

        security_id: Broker security ID of the instrument.
        trading_symbol: Human-readable symbol.
        exchange_segment: Exchange segment string.

        side: BUY or SELL.
        order_type: LIMIT, MARKET, STOP_LOSS, STOP_LOSS_MARKET.
        product_type: CNC, INTRADAY, MARGIN, MTF.
        validity: DAY or IOC.
        quantity: Total ordered quantity.
        price: Limit price.
        trigger_price: Trigger price for SL orders.
        disclosed_quantity: Quantity disclosed in the order book.
        after_market_order: Whether this is an AMO.
        amo_time: AMO timing (OPEN or MARGIN_OPEN).
        tag: User-defined correlation ID.

        target_price: Target price for bracket orders.
        stop_loss_price: SL price for bracket orders.
        trailing_jump: Trailing stop jump size.

        status: Current order status.
        filled_quantity: Quantity filled so far.
        pending_quantity: Quantity still pending.
        average_price: Weighted average fill price.
        rejection_reason: Reason if rejected.

        legs: Order legs for super/bracket orders.
        created_at: When the order was created.
        updated_at: When the order was last updated.
        raw: Raw broker response data.
    """

    order_id: str = ""
    correlation_id: str = ""
    parent_order_id: str = ""  # For super orders

    # Instrument
    security_id: str = ""
    trading_symbol: str = ""
    exchange_segment: str = ""

    # Order parameters
    side: Side = Side.BUY
    order_type: OrderType = OrderType.LIMIT
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal = Decimal("0")
    disclosed_quantity: int = 0
    after_market_order: bool = False
    amo_time: AMOTime = AMOTime.OPEN
    tag: str = ""

    # Bracket order fields
    target_price: Optional[Decimal] = None
    stop_loss_price: Optional[Decimal] = None
    trailing_jump: Optional[Decimal] = None

    # Status
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    pending_quantity: int = 0
    average_price: Decimal = Decimal("0")
    rejection_reason: str = ""

    # Legs (for super orders)
    legs: list[OrderLeg] = field(default_factory=list)

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Raw provider data
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dhan(cls, data: dict[str, Any]) -> Order:
        """Construct an Order from a Dhan order list response.

        Maps all Dhan-specific field names and enum values to the
        canonical Order model.

        Args:
            data: Raw dictionary from Dhan get_order_list or
                get_order_by_id API response.

        Returns:
            Fully populated Order instance.
        """
        status_map = {
            "PENDING": OrderStatus.PENDING,
            "PLACED": OrderStatus.PLACED,
            "ACCEPTED": OrderStatus.ACCEPTED,
            "OPEN": OrderStatus.OPEN,
            "PART_TRADED": OrderStatus.PART_TRADED,
            "TRADED": OrderStatus.TRADED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED,
            "TRIGGER_PENDING": OrderStatus.TRIGGER_PENDING,
        }

        side_str = data.get("transactionType", "BUY")
        order_type_str = data.get("orderType", "LIMIT")
        product_str = data.get("productType", "INTRADAY")

        return cls(
            order_id=str(data.get("orderId", "")),
            correlation_id=str(data.get("correlationID", "")),
            security_id=str(data.get("securityId", "")),
            trading_symbol=data.get("tradingSymbol", ""),
            exchange_segment=data.get("exchangeSegment", ""),
            side=Side(side_str),
            order_type=OrderType(order_type_str),
            product_type=ProductType(product_str),
            validity=Validity(data.get("validity", "DAY")),
            quantity=int(data.get("quantity", 0)),
            price=Decimal(str(data.get("price", 0))),
            trigger_price=Decimal(str(data.get("triggerPrice", 0))),
            disclosed_quantity=int(data.get("disclosedQty", 0)),
            after_market_order=bool(data.get("afterMarketOrder")),
            tag=data.get("correlationID", ""),
            status=status_map.get(data.get("orderStatus", ""), OrderStatus.UNKNOWN),
            filled_quantity=int(data.get("filledQty", 0)),
            pending_quantity=int(data.get("pendingQty", 0)),
            average_price=Decimal(str(data.get("averagePrice", 0))),
            rejection_reason=data.get("rejectionReason", ""),
            raw=data,
        )

    @property
    def is_complete(self) -> bool:
        """Whether the order is in a terminal state.

        Terminal states include TRADED, FILLED, CANCELLED,
        REJECTED, and EXPIRED. No further modifications are
        possible.

        Returns:
            True if the order has reached a terminal state.
        """
        return self.status in (
            OrderStatus.TRADED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )

    @property
    def is_active(self) -> bool:
        """Whether the order is still active (can be modified/cancelled).

        Active states include PENDING, PLACED, ACCEPTED, OPEN,
        PART_TRADED, and TRIGGER_PENDING.

        Returns:
            True if the order can still be modified or cancelled.
        """
        return self.status in (
            OrderStatus.PENDING,
            OrderStatus.PLACED,
            OrderStatus.ACCEPTED,
            OrderStatus.OPEN,
            OrderStatus.PART_TRADED,
            OrderStatus.TRIGGER_PENDING,
        )

    @property
    def is_filled(self) -> bool:
        """Whether the order is fully filled.

        Returns:
            True if status is TRADED or FILLED.
        """
        return self.status in (OrderStatus.TRADED, OrderStatus.FILLED)

    @property
    def notional(self) -> Decimal:
        """Notional value of the order (price × quantity).

        Returns:
            Total order value as a Decimal.
        """
        return self.price * self.quantity

    def fill(self, quantity: int, price: Decimal) -> None:
        """Record a fill on this order.

        Updates filled_quantity, pending_quantity, average_price,
        and status. Called when a partial or complete execution
        is reported by the broker.

        Args:
            quantity: Number of units filled in this execution.
            price: Execution price per unit.
        """
        self.filled_quantity += quantity
        self.pending_quantity = self.quantity - self.filled_quantity
        if self.filled_quantity > 0:
            total_cost = self.average_price * (self.filled_quantity - quantity)
            total_cost += price * quantity
            self.average_price = total_cost / self.filled_quantity
        if self.filled_quantity >= self.quantity:
            self.status = OrderStatus.TRADED
        else:
            self.status = OrderStatus.PART_TRADED
        self.updated_at = datetime.now(timezone.utc)

    def summary(self) -> dict[str, Any]:
        """Get a human-readable order summary.

        Returns a flat dictionary with key order fields suitable
        for logging, display, or serialization.

        Returns:
            Dict with order_id, symbol, side, type, product,
            quantity, price, status, filled, avg_price, and tag.
        """
        return {
            "order_id": self.order_id,
            "symbol": self.trading_symbol or self.security_id,
            "side": self.side.value,
            "type": self.order_type.value,
            "product": self.product_type.value,
            "quantity": self.quantity,
            "price": float(self.price),
            "trigger_price": float(self.trigger_price),
            "status": self.status.value,
            "filled": self.filled_quantity,
            "avg_price": float(self.average_price),
            "tag": self.tag,
        }


@dataclass
class SuperOrder(Order):
    """Super (bracket) order with target, stop-loss, and trailing.

    Extends Order with target_price, stop_loss_price, trailing_jump,
    and a list of child OrderLegs.
    """

    target_price: Decimal = Decimal("0")
    stop_loss_price: Decimal = Decimal("0")
    trailing_jump: Decimal = Decimal("0")
    legs: list[OrderLeg] = field(default_factory=list)

    @classmethod
    def from_dhan_super(cls, data: dict[str, Any]) -> SuperOrder:
        """Construct from Dhan super order response."""
        base = Order.from_dhan(data)
        legs = []
        legs_raw = data.get("legs", [])
        if isinstance(legs_raw, list):
            legs = [OrderLeg.from_dict(leg) for leg in legs_raw]

        return cls(
            order_id=base.order_id,
            correlation_id=base.correlation_id,
            parent_order_id=base.parent_order_id,
            security_id=base.security_id,
            trading_symbol=base.trading_symbol,
            exchange_segment=base.exchange_segment,
            side=base.side,
            order_type=base.order_type,
            product_type=base.product_type,
            validity=base.validity,
            quantity=base.quantity,
            price=base.price,
            trigger_price=base.trigger_price,
            disclosed_quantity=base.disclosed_quantity,
            tag=base.tag,
            status=base.status,
            filled_quantity=base.filled_quantity,
            pending_quantity=base.pending_quantity,
            average_price=base.average_price,
            rejection_reason=base.rejection_reason,
            target_price=Decimal(str(data.get("targetPrice", 0))),
            stop_loss_price=Decimal(str(data.get("stopLossPrice", 0))),
            trailing_jump=Decimal(str(data.get("trailingJump", 0))),
            legs=legs,
            raw=data,
        )

    def summary(self) -> dict[str, Any]:
        base = super().summary()
        base.update(
            {
                "target_price": float(self.target_price),
                "stop_loss_price": float(self.stop_loss_price),
                "trailing_jump": float(self.trailing_jump),
                "legs_count": len(self.legs),
            }
        )
        return base


@dataclass
class ForeverOrder(Order):
    """Forever (GTC) trigger order with optional OCO support.

    Extends Order with order_flag, price1, trigger_price1, and quantity1
    for OCO-style second legs.
    """

    order_flag: str = "SINGLE"
    price1: Decimal = Decimal("0")
    trigger_price1: Decimal = Decimal("0")
    quantity1: int = 0

    @classmethod
    def from_dhan_forever(cls, data: dict[str, Any]) -> ForeverOrder:
        """Construct from Dhan forever order response."""
        base = Order.from_dhan(data)
        return cls(
            order_id=base.order_id,
            correlation_id=base.correlation_id,
            parent_order_id=base.parent_order_id,
            security_id=base.security_id,
            trading_symbol=base.trading_symbol,
            exchange_segment=base.exchange_segment,
            side=base.side,
            order_type=base.order_type,
            product_type=base.product_type,
            validity=base.validity,
            quantity=base.quantity,
            price=base.price,
            trigger_price=base.trigger_price,
            disclosed_quantity=base.disclosed_quantity,
            tag=base.tag,
            status=base.status,
            filled_quantity=base.filled_quantity,
            pending_quantity=base.pending_quantity,
            average_price=base.average_price,
            rejection_reason=base.rejection_reason,
            order_flag=data.get("orderFlag", "SINGLE"),
            price1=Decimal(str(data.get("price1", 0))),
            trigger_price1=Decimal(str(data.get("triggerPrice1", 0))),
            quantity1=int(data.get("quantity1", 0)),
            raw=data,
        )

    def summary(self) -> dict[str, Any]:
        base = super().summary()
        base.update(
            {
                "order_flag": self.order_flag,
                "price1": float(self.price1),
                "trigger_price1": float(self.trigger_price1),
                "quantity1": self.quantity1,
            }
        )
        return base
