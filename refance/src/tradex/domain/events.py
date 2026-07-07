"""Domain events — typed events for all state changes in the SDK.

Events are the primary communication mechanism between components.
The DomainEvent base class lives here so the domain layer has zero
infrastructure dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradex.core.events import DomainEvent
from tradex.domain.enums import OrderStatus, Side


# --- Authentication Events ---


@dataclass(frozen=True)
class SessionConnected(DomainEvent):
    """Broker session established."""

    broker: str = ""
    account_id: str = ""


@dataclass(frozen=True)
class SessionDisconnected(DomainEvent):
    """Broker session disconnected."""

    broker: str = ""
    reason: str = ""


@dataclass(frozen=True)
class SessionExpired(DomainEvent):
    """Session token expired, re-authentication needed."""

    broker: str = ""


@dataclass(frozen=True)
class TokenRefreshed(DomainEvent):
    """Access token refreshed successfully."""

    broker: str = ""


@dataclass(frozen=True)
class TokenExpired(DomainEvent):
    """Token has expired and cannot be refreshed."""

    broker: str = ""


# --- Order Events ---


@dataclass(frozen=True)
class OrderPlaced(DomainEvent):
    """Order placed with broker."""

    order_id: str = ""
    correlation_id: str = ""
    security_id: str = ""
    side: Side = Side.BUY
    quantity: int = 0


@dataclass(frozen=True)
class OrderModified(DomainEvent):
    """Order modified."""

    order_id: str = ""
    correlation_id: str = ""


@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    """Order cancelled."""

    order_id: str = ""
    correlation_id: str = ""


@dataclass(frozen=True)
class OrderStatusChanged(DomainEvent):
    """Order status changed."""

    order_id: str = ""
    correlation_id: str = ""
    old_status: OrderStatus = OrderStatus.UNKNOWN
    new_status: OrderStatus = OrderStatus.UNKNOWN
    filled_quantity: int = 0
    pending_quantity: int = 0


@dataclass(frozen=True)
class OrderRejected(DomainEvent):
    """Order rejected by broker."""

    order_id: str = ""
    correlation_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class OrderFilled(DomainEvent):
    """Order fully filled."""

    order_id: str = ""
    correlation_id: str = ""
    filled_quantity: int = 0
    average_price: float = 0.0


@dataclass(frozen=True)
class TradeExecuted(DomainEvent):
    """Individual trade (fill) executed."""

    trade_id: str = ""
    order_id: str = ""
    security_id: str = ""
    side: Side = Side.BUY
    quantity: int = 0
    price: float = 0.0


# --- Market Data Events ---


@dataclass(frozen=True)
class QuoteReceived(DomainEvent):
    """Quote (tick) received from market feed."""

    security_id: str = ""
    exchange: str = ""
    last_price: float = 0.0
    volume: int = 0
    bid: float = 0.0
    ask: float = 0.0


@dataclass(frozen=True)
class DepthUpdated(DomainEvent):
    """Market depth updated."""

    security_id: str = ""
    exchange: str = ""
    depth_levels: int = 0


@dataclass(frozen=True)
class OptionChainUpdated(DomainEvent):
    """Option chain data received."""

    underlying_security_id: str = ""
    expiry: str = ""


# --- Portfolio Events ---


@dataclass(frozen=True)
class HoldingsUpdated(DomainEvent):
    """Portfolio holdings refreshed."""

    account_id: str = ""
    count: int = 0


@dataclass(frozen=True)
class PositionsUpdated(DomainEvent):
    """Portfolio positions refreshed."""

    account_id: str = ""
    open_count: int = 0


@dataclass(frozen=True)
class FundsUpdated(DomainEvent):
    """Fund limits refreshed."""

    account_id: str = ""


# --- Health Events ---


@dataclass(frozen=True)
class HealthChanged(DomainEvent):
    """Component health status changed."""

    component: str = ""
    old_status: str = ""
    new_status: str = ""
