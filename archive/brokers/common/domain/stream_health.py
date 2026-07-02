"""Stream health models — orthogonal health dimensions for WebSocket sessions.

The architecture treats transport health, subscription integrity, and data
freshness as three independent concerns.  A stream can be connected but stale,
or subscribed but on a broken transport.  Each dimension must be modeled
separately so failures are diagnosable without log archaeology.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal

# ---------------------------------------------------------------------------
# Transport layer
# ---------------------------------------------------------------------------


class TransportState(str, Enum):
    """Raw TCP/WebSocket connection state."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    AUTHENTICATING = "AUTHENTICATING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"

    def is_usable(self) -> bool:
        return self == TransportState.CONNECTED


# ---------------------------------------------------------------------------
# Subscription layer
# ---------------------------------------------------------------------------


class SubscriptionState(str, Enum):
    """State of the instrument subscription layer on top of the transport."""

    IDLE = "IDLE"  # connected, nothing subscribed yet
    SUBSCRIBING = "SUBSCRIBING"  # subscription in flight
    ACKNOWLEDGED = "ACKNOWLEDGED"  # broker confirmed all subscriptions
    PARTIAL = "PARTIAL"  # some subscriptions rejected
    DEGRADED = "DEGRADED"  # material fraction of subs missing

    def is_usable(self) -> bool:
        return self in {SubscriptionState.ACKNOWLEDGED, SubscriptionState.PARTIAL}


# ---------------------------------------------------------------------------
# Data freshness layer
# ---------------------------------------------------------------------------


class FreshnessState(str, Enum):
    """Whether valid data has been received recently."""

    UNKNOWN = "UNKNOWN"  # no data received yet (just connected)
    FRESH = "FRESH"  # within SLA window
    STALE = "STALE"  # last valid tick beyond SLA threshold
    NO_DATA = "NO_DATA"  # never received any valid tick since connect

    def within_sla(self) -> bool:
        return self == FreshnessState.FRESH


# ---------------------------------------------------------------------------
# Composite stream health
# ---------------------------------------------------------------------------


@dataclass(frozen=False)
class StreamHealth:
    """Composite health view for a single stream session.

    healthy() is True only when all three dimensions are healthy.
    Each dimension is independently diagnosable.
    """

    transport: TransportState = TransportState.DISCONNECTED
    subscription: SubscriptionState = SubscriptionState.IDLE
    freshness: FreshnessState = FreshnessState.UNKNOWN
    last_message_at: datetime | None = None
    last_valid_tick_at: datetime | None = None
    stale_seconds_threshold: float = 30.0

    def healthy(self) -> bool:
        """Return True only when transport connected, subs acknowledged, and data fresh."""
        return (
            self.transport.is_usable()
            and self.subscription.is_usable()
            and self.freshness.within_sla()
        )

    def failure_reasons(self) -> list[str]:
        """Return a list of human-readable failure reasons."""
        reasons: list[str] = []
        if not self.transport.is_usable():
            reasons.append(f"transport:{self.transport.value}")
        if not self.subscription.is_usable():
            reasons.append(f"subscription:{self.subscription.value}")
        if not self.freshness.within_sla():
            reasons.append(f"freshness:{self.freshness.value}")
        return reasons


# ---------------------------------------------------------------------------
# Stream session model
# ---------------------------------------------------------------------------


@dataclass
class StreamSession:
    """Tracks the full lifecycle state of a single broker stream session.

    This is the authoritative record owned by ``StreamOrchestrator``.
    Gateways produce and update ``StreamSession`` instances; consumers
    observe them through health snapshots.
    """

    session_id: str
    broker_id: str
    stream_kind: Literal["market", "order", "portfolio"]
    instruments: frozenset[str]  # InstrumentRef strings ("SYMBOL:EXCHANGE")
    modes: frozenset[str]  # e.g. {"LTP", "FULL"} for market; empty for order
    health: StreamHealth = field(default_factory=StreamHealth)
    reconnect_generation: int = 0
    created_at: datetime | None = None
    last_state_change_at: datetime | None = None

    def is_healthy(self) -> bool:
        return self.health.healthy()

    def failure_reasons(self) -> list[str]:
        return self.health.failure_reasons()

    def increment_reconnect(self) -> None:
        self.reconnect_generation += 1

    def update_transport(self, state: TransportState, at: datetime | None = None) -> None:
        self.health.transport = state
        if at is not None:
            self.last_state_change_at = at

    def update_subscription(self, state: SubscriptionState) -> None:
        self.health.subscription = state

    def update_freshness(self, state: FreshnessState, at: datetime | None = None) -> None:
        self.health.freshness = state
        if state == FreshnessState.FRESH and at is not None:
            self.health.last_valid_tick_at = at

    def record_message(self, at: datetime) -> None:
        self.health.last_message_at = at


@dataclass(frozen=True)
class StreamStateSummary:
    """Snapshot of all stream sessions for a broker — owned by BrokerRegistry."""

    broker_id: str
    active_sessions: int
    healthy_sessions: int
    stale_sessions: int
    degraded_sessions: int

    def all_healthy(self) -> bool:
        return self.active_sessions > 0 and self.healthy_sessions == self.active_sessions
