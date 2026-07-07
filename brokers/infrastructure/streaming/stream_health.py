"""Stream health models — three orthogonal state dimensions for WebSocket sessions.

Every active stream session tracks:
- **TransportState**: Is the underlying WebSocket connection open?
- **SubscriptionState**: Are all requested instruments subscribed?
- **FreshnessState**: Are we receiving data within the freshness SLA?

These states combine into a ``StreamHealth`` snapshot that consumers
can inspect to detect degraded streams and trigger failover.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ── State enums ────────────────────────────────────────────────────────────


class TransportState(str, Enum):
    """Underlying WebSocket connection state."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    RECONNECTING = "RECONNECTING"


class SubscriptionState(str, Enum):
    """Whether all requested subscriptions are active on the server."""

    SYNCED = "SYNCED"       # All requested instruments are subscribed
    PARTIAL = "PARTIAL"     # Some instruments failed or pending
    NONE = "NONE"           # No active subscriptions


class FreshnessState(str, Enum):
    """Data freshness relative to the configured SLA."""

    ACTIVE = "ACTIVE"       # Received data within freshness_sla_s
    STALE = "STALE"         # No data received within freshness_sla_s
    UNKNOWN = "UNKNOWN"     # Cannot determine (e.g., no subscribers yet)


# ── Health snapshot ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StreamHealth:
    """Immutable snapshot of a stream session's health."""

    transport: TransportState = TransportState.CLOSED
    subscription: SubscriptionState = SubscriptionState.NONE
    freshness: FreshnessState = FreshnessState.UNKNOWN
    last_tick_at: datetime | None = None
    reconnect_attempts: int = 0
    subscribed_count: int = 0
    requested_count: int = 0
    detail: str = ""

    @property
    def is_healthy(self) -> bool:
        """True if all three dimensions are in their best state."""
        return (
            self.transport == TransportState.OPEN
            and self.subscription == SubscriptionState.SYNCED
            and self.freshness == FreshnessState.ACTIVE
        )

    @property
    def is_degraded(self) -> bool:
        """True if connected but not fully healthy."""
        return (
            self.transport == TransportState.OPEN
            and not self.is_healthy
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a flat dict for logging/metrics."""
        return {
            "transport": self.transport.value,
            "subscription": self.subscription.value,
            "freshness": self.freshness.value,
            "is_healthy": self.is_healthy,
            "reconnect_attempts": self.reconnect_attempts,
            "subscribed_count": self.subscribed_count,
            "requested_count": self.requested_count,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "detail": self.detail,
        }


# ── Health change event ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StreamHealthChangeEvent:
    """Emitted when stream health transitions between states."""

    previous: StreamHealth
    current: StreamHealth
    broker_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_recovery(self) -> bool:
        """True if this transition represents a recovery (became healthy)."""
        return not self.previous.is_healthy and self.current.is_healthy

    @property
    def is_degradation(self) -> bool:
        """True if this transition represents a degradation."""
        return self.previous.is_healthy and not self.current.is_healthy


# ── Tick and order event types ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MarketTickEvent:
    """A normalized market data tick from any broker."""

    symbol: str
    ltp: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    change: float = 0.0
    depth_bids: tuple[tuple[float, int], ...] = ()
    depth_asks: tuple[tuple[float, int], ...] = ()
    broker_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_depth(self) -> bool:
        """True if this tick includes order book depth data."""
        return len(self.depth_bids) > 0 or len(self.depth_asks) > 0


@dataclass(frozen=True, slots=True)
class OrderUpdateEvent:
    """A normalized order/trade update from any broker."""

    order_id: str
    symbol: str = ""
    status: str = ""
    side: str = ""
    quantity: int = 0
    filled_quantity: int = 0
    price: float = 0.0
    average_price: float = 0.0
    broker_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = [
    "TransportState",
    "SubscriptionState",
    "FreshnessState",
    "StreamHealth",
    "StreamHealthChangeEvent",
    "MarketTickEvent",
    "OrderUpdateEvent",
]
