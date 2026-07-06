"""Domain events — immutable value objects for the event bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = ""

    @property
    def event_type(self) -> str:
        return type(self).__name__


# ── Event Type Constants (legacy string dispatch) ────────────────────────────

EVENT_QUOTE_TICK = "quote.tick"
EVENT_QUOTE_UPDATED = "QuoteUpdatedEvent"
EVENT_DEPTH_UPDATE = "depth.update"
EVENT_ORDER_PLACED = "order.placed"
EVENT_ORDER_FILLED = "order.filled"
EVENT_ORDER_REJECTED = "order.rejected"
EVENT_ORDER_MODIFIED = "order.modified"
EVENT_ORDER_CANCELLED = "order.cancelled"
EVENT_ORDER_STATE_CHANGE = "order.state_change"
EVENT_CONNECTION = "connection"
EVENT_CONNECTION_CHANGED = EVENT_CONNECTION


# ── Market Data Events (V3) ──────────────────────────────────────────────────


@dataclass(frozen=True)
class QuoteUpdatedEvent(DomainEvent):
    """Published when a new quote tick arrives for an instrument."""

    instrument_key: str = ""
    ltp: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    volume: int = 0
    oi: int = 0
    timestamp_exchange: datetime | None = None


@dataclass(frozen=True)
class QuoteTickEvent(QuoteUpdatedEvent):
    """Backward-compatible alias for streaming quote ticks."""

    composite_key: str = ""
    symbol: str = ""
    exchange: str = ""
    event_type_legacy: str = EVENT_QUOTE_TICK

    @property
    def event_type(self) -> str:
        return self.event_type_legacy


@dataclass(frozen=True)
class DepthUpdateEvent(DomainEvent):
    """Published when depth data arrives for an instrument."""

    composite_key: str = ""
    symbol: str = ""
    exchange: str = ""
    bids: tuple[tuple[Decimal, int], ...] = ()
    asks: tuple[tuple[Decimal, int], ...] = ()


# ── Order Events (V3) ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OrderPlacedEvent(DomainEvent):
    """Published when an order is placed successfully."""

    instrument_key: str = ""
    order_id: str = ""
    side: str = ""
    quantity: int = 0
    price: Decimal = Decimal("0")
    order_type: str = ""
    account_id: str = ""
    correlation_id: str = ""
    symbol: str = ""
    exchange: str = ""
    trigger_price: str = ""


@dataclass(frozen=True)
class OrderFilledEvent(DomainEvent):
    """Published when an order receives fills."""

    instrument_key: str = ""
    order_id: str = ""
    filled_quantity: int = 0
    remaining_quantity: int = 0
    average_price: Decimal = Decimal("0")
    account_id: str = ""
    correlation_id: str = ""
    symbol: str = ""
    fill_price: str = ""
    fill_quantity: int = 0
    is_complete: bool = False


@dataclass(frozen=True)
class OrderRejectedEvent(DomainEvent):
    """Published when an order is rejected."""

    instrument_key: str = ""
    order_id: str = ""
    reason: str = ""
    account_id: str = ""
    correlation_id: str = ""
    symbol: str = ""
    is_retryable: bool = False


@dataclass(frozen=True)
class OrderModifiedEvent(DomainEvent):
    """Published when an order is successfully modified."""

    account_id: str = ""
    order_id: str = ""
    correlation_id: str = ""
    symbol: str = ""
    old_quantity: int = 0
    new_quantity: int = 0


@dataclass(frozen=True)
class OrderCancelledEvent(DomainEvent):
    """Published when an order is cancelled."""

    account_id: str = ""
    order_id: str = ""
    correlation_id: str = ""
    symbol: str = ""
    cancelled_quantity: int = 0


@dataclass(frozen=True)
class OrderStateChangeEvent(DomainEvent):
    """Published on every order state transition recorded by the OMS."""

    order_id: str = ""
    account_id: str = ""
    correlation_id: str = ""
    from_status: str = ""
    to_status: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ConnectionEvent(DomainEvent):
    """Published when a WebSocket or streaming connection changes state."""

    connection_type: str = ""
    state: str = ""
    broker_id: str = ""
    message: str = ""


def resolve_event_type(event: DomainEvent | Any) -> str:
    """Resolve dispatch key for event bus handlers."""
    legacy = getattr(event, "event_type_legacy", None)
    if legacy:
        return str(legacy)
    event_type = getattr(event, "event_type", None)
    if isinstance(event_type, str):
        return event_type
    return type(event).__name__
