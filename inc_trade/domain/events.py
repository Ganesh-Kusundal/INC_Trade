"""Domain events — immutable value objects for the event bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from inc_trade.domain.enums import OrderStatus


@dataclass(frozen=True)
class DomainEvent:
    """Immutable domain event published on the in-process event bus."""

    event_type: str
    payload: dict[str, Any]
    symbol: str | None = None
    source: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def now(
        cls,
        event_type: str,
        payload: dict[str, Any],
        *,
        symbol: str | None = None,
        source: str | None = None,
    ) -> DomainEvent:
        return cls(
            event_type=event_type,
            payload=payload,
            symbol=symbol,
            source=source,
            timestamp=datetime.now(timezone.utc),
        )


# ── Event Type Constants ─────────────────────────────────────────────────────

EVENT_QUOTE_TICK = "quote.tick"
EVENT_DEPTH_UPDATE = "depth.update"
EVENT_ORDER_PLACED = "order.placed"
EVENT_ORDER_FILLED = "order.filled"
EVENT_ORDER_REJECTED = "order.rejected"
EVENT_ORDER_MODIFIED = "order.modified"
EVENT_ORDER_CANCELLED = "order.cancelled"
EVENT_ORDER_STATE_CHANGE = "order.state_change"
EVENT_CONNECTION = "connection"
EVENT_CONNECTION_CHANGED = EVENT_CONNECTION


# ── Market Data Events ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class QuoteTickEvent:
    """Published when a streaming tick arrives for an instrument.

    Attributes:
        composite_key: Canonical composite key ``{exchange}:{symbol}``.
        symbol: Trading symbol.
        exchange: Exchange code.
        ltp: Last traded price.
        bid: Best bid price.
        ask: Best ask price.
        volume: Traded volume for this tick.
        oi: Open interest (0 if not available).
        source: Broker identifier that generated this event.
        event_type: Constant ``EVENT_QUOTE_TICK``.
        timestamp: When the tick was received.
    """

    composite_key: str = ""
    symbol: str = ""
    exchange: str = ""
    ltp: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    volume: int = 0
    oi: int = 0
    source: str = ""
    event_type: str = EVENT_QUOTE_TICK
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class DepthUpdateEvent:
    """Published when depth data arrives for an instrument."""

    composite_key: str = ""
    symbol: str = ""
    exchange: str = ""
    bids: tuple[tuple[Decimal, int], ...] = ()
    asks: tuple[tuple[Decimal, int], ...] = ()
    source: str = ""
    event_type: str = EVENT_DEPTH_UPDATE
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Order Events ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OrderPlacedEvent:
    """Published when an order is successfully placed."""

    account_id: str = ""
    order_id: str = ""
    correlation_id: str = ""
    symbol: str = ""
    exchange: str = ""
    side: str = ""
    quantity: int = 0
    order_type: str = ""
    price: Decimal = Decimal("0")
    trigger_price: str = ""
    event_type: str = EVENT_ORDER_PLACED
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class OrderFilledEvent:
    """Published when an order is partially or fully filled."""

    account_id: str = ""
    order_id: str = ""
    correlation_id: str = ""
    symbol: str = ""
    fill_price: str = ""
    fill_quantity: int = 0
    remaining_quantity: int = 0
    is_complete: bool = False
    event_type: str = EVENT_ORDER_FILLED
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class OrderRejectedEvent:
    """Published when an order is rejected by the broker."""

    account_id: str = ""
    order_id: str = ""
    correlation_id: str = ""
    symbol: str = ""
    reason: str = ""
    is_retryable: bool = False
    event_type: str = EVENT_ORDER_REJECTED
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class OrderModifiedEvent:
    """Published when an order is successfully modified."""

    account_id: str = ""
    order_id: str = ""
    correlation_id: str = ""
    symbol: str = ""
    old_quantity: int = 0
    new_quantity: int = 0
    event_type: str = EVENT_ORDER_MODIFIED
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class OrderCancelledEvent:
    """Published when an order is cancelled."""

    account_id: str = ""
    order_id: str = ""
    correlation_id: str = ""
    symbol: str = ""
    cancelled_quantity: int = 0
    event_type: str = EVENT_ORDER_CANCELLED
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class OrderStateChangeEvent:
    """Published on every order state transition recorded by the OMS."""

    order_id: str = ""
    account_id: str = ""
    correlation_id: str = ""
    from_status: str = ""
    to_status: str = ""
    reason: str = ""
    event_type: str = EVENT_ORDER_STATE_CHANGE
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ConnectionEvent:
    """Published when a WebSocket or streaming connection changes state."""

    connection_type: str = ""
    state: str = ""  # "connected", "disconnected", "reconnecting", "error"
    broker_id: str = ""
    message: str = ""
    event_type: str = EVENT_CONNECTION
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
