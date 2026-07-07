"""Canonical event-type catalogue for the in-process event bus.

Provides :class:`DomainEvent`, :class:`EventType` (str enum), and
:class:`EventPayload` contract definitions.  The event *shape* lives here
in domain; the bus infrastructure lives in ``infrastructure.event_bus``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

EVENT_ID_HEX_LENGTH = 16


@runtime_checkable
class EventBusProtocol(Protocol):
    """Domain protocol for the event bus.

    Any in-process event bus must implement ``publish()``.
    The domain layer depends on this protocol, not on the
    infrastructure implementation.
    """

    def publish(self, event: DomainEvent) -> None: ...


@dataclass(frozen=True)
class DomainEvent:
    """An immutable domain event — the core value object for the event bus.

    This is a pure domain concept. The event bus infrastructure
    (publish/subscribe/dispatch) lives in ``infrastructure.event_bus``;
    the event *shape* lives here in domain.
    """

    event_type: str
    timestamp: datetime
    payload: dict[str, Any]
    symbol: str | None = None
    source: str | None = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:EVENT_ID_HEX_LENGTH])
    correlation_id: str | None = None
    sequence_number: int = 0

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                f"DomainEvent requires timezone-aware timestamps. "
                f"Got naive datetime: {self.timestamp}. "
                f"Use DomainEvent.now() factory or provide tzinfo explicitly."
            )

    @classmethod
    def now(
        cls,
        event_type: str,
        payload: dict[str, Any],
        symbol: str | None = None,
        source: str | None = None,
        correlation_id: str | None = None,
        sequence_number: int = 0,
    ) -> DomainEvent:
        """Factory using UTC now. Validates payload against the contract."""
        validated = make_payload(event_type, payload, validate=True)
        return cls(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            payload=dict(validated),
            symbol=symbol,
            source=source,
            correlation_id=correlation_id,
            sequence_number=sequence_number,
        )


class EventType(str, Enum):
    """Canonical event types published on the :class:`EventBus`.

    Inheriting from :class:`str` means existing ``==`` comparisons
    with bare strings continue to work:

        if event.event_type == EventType.TICK:   # works
        if event.event_type == "TICK":          # also works

    The order is intentional — new types should be appended, never
    inserted, to keep the wire-format stable across deployments.
    """

    # ── Market data ────────────────────────────────────────────────────
    TICK = "TICK"
    DEPTH = "DEPTH"
    INDEX_QUOTE = "INDEX_QUOTE"
    OPTION_CHAIN = "OPTION_CHAIN"

    # ── Orders / OMS ───────────────────────────────────────────────────
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_UPDATED = "ORDER_UPDATED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    TRADE = "TRADE"
    TRADE_APPLIED = "TRADE_APPLIED"

    # ── Risk / position ────────────────────────────────────────────────
    POSITION_CHANGED = "POSITION_CHANGED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    RISK_BREACH = "RISK_BREACH"
    RISK_VIOLATED = "RISK_VIOLATED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    KILL_SWITCH_FLIPPED = "KILL_SWITCH_FLIPPED"
    KILL_SWITCH_TOGGLED = "KILL_SWITCH_TOGGLED"
    DAILY_PNL_RESET = "DAILY_PNL_RESET"
    DRAWDOWN_LIMIT_HIT = "DRAWDOWN_LIMIT_HIT"

    # ── Reconciliation ─────────────────────────────────────────────────
    RECONCILIATION_DRIFT = "RECONCILIATION_DRIFT"
    RECONCILIATION_OK = "RECONCILIATION_OK"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"

    # ── Lifecycle / system ─────────────────────────────────────────────
    SERVICE_STARTED = "SERVICE_STARTED"
    SERVICE_STOPPED = "SERVICE_STOPPED"
    SERVICE_FAILED = "SERVICE_FAILED"
    SYSTEM_STARTED = "SYSTEM_STARTED"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    HEALTH_CHECK_PASSED = "HEALTH_CHECK_PASSED"
    HEALTH_CHECK_FAILED = "HEALTH_CHECK_FAILED"

    # ── Broker connectivity ───────────────────────────────────────────
    BROKER_CONNECTED = "BROKER_CONNECTED"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    CIRCUIT_BREAKER_OPENED = "CIRCUIT_BREAKER_OPENED"
    CIRCUIT_BREAKER_CLOSED = "CIRCUIT_BREAKER_CLOSED"

    # ── Scanner / Strategy ────────────────────────────────────────────
    SCAN_STARTED = "SCAN_STARTED"
    CANDIDATE_GENERATED = "CANDIDATE_GENERATED"
    SCAN_COMPLETED = "SCAN_COMPLETED"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    SIGNAL_EXECUTED = "SIGNAL_EXECUTED"
    SCANNER_STATE_CHANGED = "SCANNER_STATE_CHANGED"
    STRATEGY_ACTIVATED = "STRATEGY_ACTIVATED"
    STRATEGY_PAUSED = "STRATEGY_PAUSED"
    STRATEGY_DISABLED = "STRATEGY_DISABLED"

    # ── Portfolio / Metrics ───────────────────────────────────────────
    PORTFOLIO_UPDATED = "PORTFOLIO_UPDATED"
    METRICS_UPDATED = "METRICS_UPDATED"
    POSITION_UPDATED = "POSITION_UPDATED"


@dataclass(frozen=True)
class EventPayload:
    """Payload contract for one :class:`EventType`.

    ``required_keys`` are the keys that MUST be present in
    ``DomainEvent.payload``. ``optional_keys`` are recognised but
    not enforced.
    """

    required_keys: tuple[str, ...] = ()
    optional_keys: tuple[str, ...] = ()
    notes: str = ""
    version: int = 1


# Catalogue — append-only. The dict key is the canonical EventType.
EVENT_PAYLOADS: dict[EventType, EventPayload] = {
    EventType.TICK: EventPayload(
        required_keys=(),
        optional_keys=("ltp", "open", "high", "low", "close", "volume"),
        notes="TICK carries the latest quote snapshot for one symbol.",
    ),
    EventType.DEPTH: EventPayload(
        required_keys=("bids", "asks"),
        optional_keys=("ltp", "timestamp"),
        notes="DEPTH carries the order-book snapshot.",
    ),
    EventType.ORDER_PLACED: EventPayload(
        required_keys=("order",),
        notes="ORDER_PLACED is published after a successful place_order().",
    ),
    EventType.ORDER_SUBMITTED: EventPayload(
        required_keys=("order",),
        notes="ORDER_SUBMITTED is published when an order is submitted to the broker.",
    ),
    EventType.ORDER_UPDATED: EventPayload(
        required_keys=("order",),
        notes="ORDER_UPDATED is published on every order status transition.",
    ),
    EventType.ORDER_CANCELLED: EventPayload(
        required_keys=("order_id",),
        optional_keys=("order",),
    ),
    EventType.ORDER_REJECTED: EventPayload(
        required_keys=("order_id", "reason"),
        optional_keys=("error_code",),
    ),
    EventType.TRADE: EventPayload(
        required_keys=("trade",),
        notes="TRADE is published when a fill is received.",
    ),
    EventType.TRADE_APPLIED: EventPayload(
        required_keys=("trade",),
        notes="TRADE_APPLIED is the OMS-private downstream of TRADE.",
    ),
    EventType.POSITION_CHANGED: EventPayload(
        required_keys=("symbol", "quantity"),
        optional_keys=("avg_price", "realized_pnl"),
    ),
    EventType.POSITION_OPENED: EventPayload(
        required_keys=("symbol", "quantity", "avg_price"),
    ),
    EventType.POSITION_CLOSED: EventPayload(
        required_keys=("symbol", "realized_pnl"),
    ),
    EventType.RISK_BREACH: EventPayload(
        required_keys=("rule", "value", "limit"),
        optional_keys=("symbol",),
    ),
    EventType.RISK_VIOLATED: EventPayload(
        required_keys=("rule", "value", "limit"),
        optional_keys=("symbol",),
    ),
    EventType.RISK_APPROVED: EventPayload(
        required_keys=("order_id",),
    ),
    EventType.RISK_REJECTED: EventPayload(
        required_keys=("order_id", "rule", "value", "limit"),
    ),
    EventType.KILL_SWITCH_FLIPPED: EventPayload(
        required_keys=("active",),
        optional_keys=("actor", "reason"),
    ),
    EventType.KILL_SWITCH_TOGGLED: EventPayload(
        required_keys=("active",),
        optional_keys=("actor", "reason"),
    ),
    EventType.DAILY_PNL_RESET: EventPayload(
        optional_keys=("reset_at",),
    ),
    EventType.DRAWDOWN_LIMIT_HIT: EventPayload(
        required_keys=("drawdown", "limit"),
    ),
    EventType.RECONCILIATION_DRIFT: EventPayload(
        required_keys=("symbol", "internal", "broker"),
        optional_keys=("side", "quantity_diff"),
    ),
    EventType.RECONCILIATION_OK: EventPayload(
        optional_keys=("checked_at", "symbols"),
    ),
    EventType.RECONCILIATION_COMPLETED: EventPayload(
        optional_keys=("checked_at", "symbols", "drift_count"),
    ),
    EventType.SERVICE_STARTED: EventPayload(
        required_keys=("service_name",),
        optional_keys=("detail",),
    ),
    EventType.SERVICE_STOPPED: EventPayload(
        required_keys=("service_name",),
        optional_keys=("detail",),
    ),
    EventType.SERVICE_FAILED: EventPayload(
        required_keys=("service_name", "error"),
        optional_keys=("traceback",),
    ),
    EventType.SYSTEM_STARTED: EventPayload(
        required_keys=("service_name",),
        optional_keys=("version",),
    ),
    EventType.SYSTEM_SHUTDOWN: EventPayload(
        required_keys=("service_name",),
        optional_keys=("reason",),
    ),
    EventType.HEALTH_CHECK_PASSED: EventPayload(
        optional_keys=("component",),
    ),
    EventType.HEALTH_CHECK_FAILED: EventPayload(
        required_keys=("component", "error"),
    ),
    EventType.BROKER_CONNECTED: EventPayload(
        required_keys=("broker_name",),
        optional_keys=("environment",),
    ),
    EventType.BROKER_DISCONNECTED: EventPayload(
        required_keys=("broker_name", "reason"),
    ),
    EventType.TOKEN_REFRESHED: EventPayload(
        required_keys=("broker_name",),
        optional_keys=("expires_at",),
    ),
    EventType.TOKEN_EXPIRED: EventPayload(
        required_keys=("broker_name",),
    ),
    EventType.CIRCUIT_BREAKER_OPENED: EventPayload(
        required_keys=("reason",),
        optional_keys=("duration",),
    ),
    EventType.CIRCUIT_BREAKER_CLOSED: EventPayload(
        optional_keys=("down_time",),
    ),
    EventType.SCAN_STARTED: EventPayload(
        required_keys=("profile",),
        optional_keys=("universe",),
    ),
    EventType.CANDIDATE_GENERATED: EventPayload(
        required_keys=("symbol", "score"),
        optional_keys=("reason",),
    ),
    EventType.SCAN_COMPLETED: EventPayload(
        required_keys=("candidate_count",),
        optional_keys=("duration", "universe"),
    ),
    EventType.SIGNAL_GENERATED: EventPayload(
        required_keys=("signal",),
    ),
    EventType.SIGNAL_EXECUTED: EventPayload(
        required_keys=("signal", "order_id"),
    ),
    EventType.SCANNER_STATE_CHANGED: EventPayload(
        required_keys=("scanner_name", "state"),
        optional_keys=("reason",),
    ),
    EventType.STRATEGY_ACTIVATED: EventPayload(
        required_keys=("strategy_name",),
        optional_keys=("activated_by",),
    ),
    EventType.STRATEGY_PAUSED: EventPayload(
        required_keys=("strategy_name",),
        optional_keys=("reason",),
    ),
    EventType.STRATEGY_DISABLED: EventPayload(
        required_keys=("strategy_name", "reason"),
    ),
    EventType.PORTFOLIO_UPDATED: EventPayload(
        required_keys=("total_pnl", "capital", "positions_count"),
        optional_keys=("drawdown", "sharpe"),
    ),
    EventType.METRICS_UPDATED: EventPayload(
        required_keys=("metric_name", "value"),
        optional_keys=("symbol", "strategy"),
    ),
    EventType.POSITION_UPDATED: EventPayload(
        required_keys=("symbol", "quantity"),
        optional_keys=("avg_price",),
    ),
    EventType.INDEX_QUOTE: EventPayload(
        required_keys=("index",),
        optional_keys=("ltp", "change", "change_pct"),
    ),
    EventType.OPTION_CHAIN: EventPayload(
        required_keys=("underlying", "expiry"),
        optional_keys=("calls", "puts", "timestamp"),
    ),
}


_CANONICAL: frozenset[str] = frozenset(t.value for t in EventType)


def canonical_event_types() -> frozenset[str]:
    """Return every event type known to the bus, as strings.

    Use this in tests that want to assert "no unknown event types
    are being published".
    """
    return _CANONICAL


def make_payload(
    event_type: EventType | str,
    payload: dict[str, Any],
    validate: bool = True,
) -> dict[str, Any]:
    """Validate ``payload`` against the contract for ``event_type``.

    If ``validate=True`` (default), :class:`KeyError` is raised if any
    required key is missing.  If ``validate=False``, this is a pass-through.
    """
    if not validate:
        return payload
    # Normalise: EVENT_PAYLOADS keys are EventType enums, but callers may pass str
    if isinstance(event_type, str):
        try:
            lookup = EventType(event_type)
        except ValueError:
            return payload  # Unknown event type — skip validation
    else:
        lookup = event_type
    contract = EVENT_PAYLOADS.get(lookup)
    if contract is None:
        return payload
    missing = [k for k in contract.required_keys if k not in payload]
    if missing:
        raise KeyError(
            f"{lookup.value} payload missing required keys: {missing}; "
            f"contract: {contract.notes}"
        )
    return payload


__all__ = [
    "EVENT_PAYLOADS",
    "DomainEvent",
    "EventPayload",
    "EventType",
    "canonical_event_types",
    "make_payload",
]
