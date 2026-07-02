"""Canonical event-type catalogue for the in-process event bus.

Why this module exists
----------------------
The :class:`EventBus` accepts arbitrary string ``event_type`` values.
This was a deliberate design choice early on — strings are flexible
and require no schema migration when adding new event types — but it
has a real cost:

- A typo (``"TICk"`` vs ``"TICK"``) silently creates a separate
  event type that no subscriber will ever see. There is no test
  that catches this.
- The set of canonical event types is implicit; a new contributor
  reads the code to discover what is in use.
- Refactoring an event type requires grep across the entire
  codebase with no compiler help.

This module centralises the contract:

- :class:`EventType` is a :class:`str`-backed enum so existing
  code that compares ``event.event_type == "TICK"`` keeps working.
- :class:`EventPayload` declares the canonical payload keys for
  each event type. Validation is optional — see
  :func:`make_payload` — but the contract is documented.
- :func:`canonical_event_types` returns the full set so tests
  and lint rules can verify no unknown event types are introduced.
- **P5 Stability Engineering**: Typed event classes provide
  compile-time safety for critical OMS events, eliminating raw
  dict access patterns that cause runtime errors.

Migration
---------
New code SHOULD use :class:`EventType` directly. Existing code MAY
continue to pass strings; the bus does not enforce the enum and the
constants on the enum are the same as the legacy strings. A future
audit pass can tighten this — for now the goal is to provide a
single, grep-able source of truth, not to break callers.

P5: Typed Event Classes
-----------------------
Critical OMS events now have typed dataclasses that wrap DomainEvent
with type-safe accessors. These eliminate raw dict payload access:

    # OLD (unsafe):
    order = event.payload.get("order")  # No type safety!

    # NEW (safe):
    typed_event = OrderUpdatedEvent.from_domain_event(event)
    order = typed_event.order  # Type: Order, compile-time checked
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.entities.order import Order
    from domain.entities.trade import Trade

EVENT_ID_HEX_LENGTH = 16


@dataclass(frozen=True)
class DomainEvent:
    """An immutable domain event — the core value object for the event bus.

    This is a pure domain concept. The event bus infrastructure
    (publish/subscribe/dispatch) lives in ``infrastructure.event_bus``;
    the event *shape* lives here in domain.
    """

    event_type: str
    timestamp: datetime
    payload: dict
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
        payload: dict,
        symbol: str | None = None,
        source: str | None = None,
        correlation_id: str | None = None,
        sequence_number: int = 0,
    ) -> DomainEvent:
        """Factory using UTC now.

        If *correlation_id* is not provided, the current thread's active
        correlation ID is used for automatic end-to-end tracing.
        """
        if correlation_id is None:
            try:
                from domain.correlation import get_current_correlation_id
                cid = get_current_correlation_id()
                if cid is not None:
                    correlation_id = cid
            except ImportError:
                pass
        return cls(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            payload=dict(payload),
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
    # TRADE_APPLIED is the OMS-private downstream of TRADE — published
    # only after the OMS has accepted the trade (idempotency check
    # passed). External consumers should subscribe to TRADE; the
    # position manager subscribes to TRADE_APPLIED to avoid double-
    # counting on duplicate websocket fills.
    TRADE_APPLIED = "TRADE_APPLIED"

    # ── Risk / position ────────────────────────────────────────────────
    POSITION_CHANGED = "POSITION_CHANGED"
    RISK_BREACH = "RISK_BREACH"
    KILL_SWITCH_FLIPPED = "KILL_SWITCH_FLIPPED"

    # ── Reconciliation ─────────────────────────────────────────────────
    RECONCILIATION_DRIFT = "RECONCILIATION_DRIFT"
    RECONCILIATION_OK = "RECONCILIATION_OK"

    # ── Lifecycle / system ─────────────────────────────────────────────
    SERVICE_STARTED = "SERVICE_STARTED"
    SERVICE_STOPPED = "SERVICE_STOPPED"
    SERVICE_FAILED = "SERVICE_FAILED"

    # ── Legacy (still published by existing callers) ──────────────────
    POSITION_UPDATED = "POSITION_UPDATED"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"

    # ── Additional Risk Events ───────────────────────────────────────
    RISK_VIOLATED = "RISK_VIOLATED"
    KILL_SWITCH_TOGGLED = "KILL_SWITCH_TOGGLED"
    DAILY_PNL_RESET = "DAILY_PNL_RESET"
    DRAWDOWN_LIMIT_HIT = "DRAWDOWN_LIMIT_HIT"

    # ── Broker Connectivity Events ───────────────────────────────────
    BROKER_CONNECTED = "BROKER_CONNECTED"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    CIRCUIT_BREAKER_OPENED = "CIRCUIT_BREAKER_OPENED"
    CIRCUIT_BREAKER_CLOSED = "CIRCUIT_BREAKER_CLOSED"

    # ── Scanner Events ───────────────────────────────────────────────
    SCAN_STARTED = "SCAN_STARTED"
    CANDIDATE_GENERATED = "CANDIDATE_GENERATED"
    SCAN_COMPLETED = "SCAN_COMPLETED"

    # ── Strategy Events ──────────────────────────────────────────────
    SIGNAL_EXECUTED = "SIGNAL_EXECUTED"

    # ── Position Lifecycle Events ────────────────────────────────────
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"

    # ── Health / System Events ───────────────────────────────────────
    SYSTEM_STARTED = "SYSTEM_STARTED"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    HEALTH_CHECK_PASSED = "HEALTH_CHECK_PASSED"
    HEALTH_CHECK_FAILED = "HEALTH_CHECK_FAILED"

    # ── Risk Decision Events (P1-Phase 1) ────────────────────────────
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"

    # ── Portfolio & Metrics Events (P1-Phase 1) ─────────────────────
    PORTFOLIO_UPDATED = "PORTFOLIO_UPDATED"
    METRICS_UPDATED = "METRICS_UPDATED"

    # ── Scanner/Strategy Lifecycle Events (P1-Phase 1) ──────────────
    SCANNER_STATE_CHANGED = "SCANNER_STATE_CHANGED"
    STRATEGY_ACTIVATED = "STRATEGY_ACTIVATED"
    STRATEGY_PAUSED = "STRATEGY_PAUSED"
    STRATEGY_DISABLED = "STRATEGY_DISABLED"


@dataclass(frozen=True)
class EventPayload:
    """Payload contract for one :class:`EventType`.

    ``required_keys`` are the keys that MUST be present in
    ``DomainEvent.payload``. ``optional_keys`` are recognised but
    not enforced.

    The contract is *informative* today (validated by
    :func:`make_payload` if ``validate=True``). It exists so:

    - A subscriber reading ``event.payload["ltp"]`` knows ``ltp``
      is part of the contract and can rely on it.
    - A publisher adding a new key is forced to update this dataclass
      (because tests grep for changes).

    ``version`` tracks schema evolution. When a payload's required_keys
    or optional_keys change, increment the version. This enables:
    - Backward-compatible event replay (old events with v1 schema)
    - Schema migration detection
    - Consumer version negotiation
    """

    required_keys: tuple[str, ...] = ()
    optional_keys: tuple[str, ...] = ()
    notes: str = ""
    version: int = 1


# Catalogue — append-only. The dict key is the canonical EventType;
# the linter / test will catch mismatches.
EVENT_PAYLOADS: dict[EventType, EventPayload] = {
    EventType.TICK: EventPayload(
        required_keys=(),
        optional_keys=("ltp", "open", "high", "low", "close", "volume"),
        notes=(
            "TICK carries the latest quote snapshot for one symbol. "
            "Subscribers MUST tolerate missing optional keys — a partial "
            "tick is valid during warmup."
        ),
    ),
    EventType.DEPTH: EventPayload(
        required_keys=("bids", "asks"),
        optional_keys=("ltp", "timestamp"),
        notes=(
            "DEPTH carries the order-book snapshot. bids/asks are "
            "lists of [price, quantity, orders] triples."
        ),
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
        notes=(
            "TRADE_APPLIED is the OMS-private downstream of TRADE. "
            "Published only after the OMS has accepted the trade "
            "(idempotency check passed). External consumers should "
            "subscribe to TRADE."
        ),
    ),
    EventType.POSITION_CHANGED: EventPayload(
        required_keys=("symbol", "quantity"),
        optional_keys=("avg_price", "realized_pnl"),
    ),
    EventType.RISK_BREACH: EventPayload(
        required_keys=("rule", "value", "limit"),
        optional_keys=("symbol",),
    ),
    EventType.KILL_SWITCH_FLIPPED: EventPayload(
        required_keys=("active",),
        optional_keys=("actor", "reason"),
    ),
    EventType.RECONCILIATION_DRIFT: EventPayload(
        required_keys=("symbol", "internal", "broker"),
        optional_keys=("side", "quantity_diff"),
    ),
    EventType.RECONCILIATION_OK: EventPayload(
        optional_keys=("checked_at", "symbols"),
        notes="Heartbeat-style: published after each successful reconcile cycle.",
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
    EventType.INDEX_QUOTE: EventPayload(
        required_keys=("index",),
        optional_keys=("ltp", "change", "change_pct"),
    ),
    EventType.OPTION_CHAIN: EventPayload(
        required_keys=("underlying", "expiry"),
        optional_keys=("calls", "puts", "timestamp"),
    ),
    EventType.POSITION_UPDATED: EventPayload(
        required_keys=("symbol", "quantity"),
        optional_keys=("avg_price",),
    ),
    EventType.SIGNAL_GENERATED: EventPayload(
        required_keys=("signal",),
    ),
    EventType.RECONCILIATION_COMPLETED: EventPayload(
        optional_keys=("checked_at", "symbols", "drift_count"),
    ),
    EventType.RISK_VIOLATED: EventPayload(
        required_keys=("rule", "value", "limit"),
        optional_keys=("symbol",),
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
    EventType.SIGNAL_EXECUTED: EventPayload(
        required_keys=("signal", "order_id"),
    ),
    EventType.POSITION_OPENED: EventPayload(
        required_keys=("symbol", "quantity", "avg_price"),
    ),
    EventType.POSITION_CLOSED: EventPayload(
        required_keys=("symbol", "realized_pnl"),
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
    EventType.RISK_APPROVED: EventPayload(
        required_keys=("order_id",),
        notes="RISK_APPROVED is published when risk check passes for an order.",
    ),
    EventType.RISK_REJECTED: EventPayload(
        required_keys=("order_id", "rule", "value", "limit"),
        notes="RISK_REJECTED is published when risk check fails for an order.",
    ),
    EventType.PORTFOLIO_UPDATED: EventPayload(
        required_keys=("total_pnl", "capital", "positions_count"),
        optional_keys=("drawdown", "sharpe"),
        notes="PORTFOLIO_UPDATED is published when portfolio state changes.",
    ),
    EventType.METRICS_UPDATED: EventPayload(
        required_keys=("metric_name", "value"),
        optional_keys=("symbol", "strategy"),
        notes="METRICS_UPDATED is published when a metric value changes.",
    ),
    EventType.SCANNER_STATE_CHANGED: EventPayload(
        required_keys=("scanner_name", "state"),
        optional_keys=("reason",),
        notes="SCANNER_STATE_CHANGED is published when scanner state changes.",
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
}

_CANONICAL: frozenset[str] = frozenset(t.value for t in EventType)


def canonical_event_types() -> frozenset[str]:
    """Return every event type known to the bus, as strings.

    Use this in tests that want to assert "no unknown event types
    are being published". Tests can diff the live set returned by
    the bus against this canonical set to catch typos.
    """
    return _CANONICAL


def make_payload(
    event_type: EventType,
    payload: dict[str, Any],
    validate: bool = False,
) -> dict[str, Any]:
    """Optionally validate ``payload`` against the contract for ``event_type``.

    If ``validate=False`` (default), this is a pass-through. The
    default is intentionally permissive because runtime validation
    would block legacy events on the event log.

    If ``validate=True``, :class:`KeyError` is raised if any
    required key is missing.

    Returns the (possibly mutated) payload dict so the call site
    can chain into :meth:`DomainEvent.now`.
    """
    if not validate:
        return payload
    contract = EVENT_PAYLOADS.get(event_type)
    if contract is None:
        return payload
    missing = [k for k in contract.required_keys if k not in payload]
    if missing:
        raise KeyError(
            f"{event_type.value} payload missing required keys: {missing}; "
            f"contract: {contract.notes}"
        )
    return payload


__all__ = [
    "EVENT_PAYLOADS",
    "EventPayload",
    "EventType",
    "OrderUpdatedEvent",
    "TradeAppliedEvent",
    "TradeFilledEvent",
    "canonical_event_types",
    "make_payload",
]


# ── P5: Typed Event Classes (Stability Engineering) ─────────────────────
# These provide compile-time safety for critical OMS events,
# eliminating raw dict payload access that causes runtime errors.


@dataclass(frozen=True)
class TypedDomainEvent:
    """Base for typed event wrappers — delegates to the underlying DomainEvent."""

    underlying_event: Any  # DomainEvent (avoid circular import)

    @property
    def event_type(self) -> str:
        return self.underlying_event.event_type

    @property
    def event_id(self) -> str:
        return self.underlying_event.event_id

    @property
    def correlation_id(self) -> str | None:
        return self.underlying_event.correlation_id


@dataclass(frozen=True)
class OrderUpdatedEvent(TypedDomainEvent):
    """Typed wrapper for ORDER_UPDATED events.

    Usage:
        def on_order_update(self, event: DomainEvent) -> None:
            typed = OrderUpdatedEvent.from_domain_event(event)
            order = typed.order  # Type: Order, compile-time safe!
            self.upsert_order(order)
    """

    order: Order = None  # type: ignore[assignment]

    @classmethod
    def from_domain_event(cls, event: Any) -> OrderUpdatedEvent:
        from domain.entities.order import Order

        order = event.payload.get("order")
        if not isinstance(order, Order):
            raise ValueError(
                f"ORDER_UPDATED event must contain Order object in payload, "
                f"got {type(order).__name__}"
            )
        return cls(order=order, underlying_event=event)


@dataclass(frozen=True)
class TradeFilledEvent(TypedDomainEvent):
    """Typed wrapper for TRADE events (broker fill received).

    Usage:
        def on_trade(self, event: DomainEvent) -> None:
            typed = TradeFilledEvent.from_domain_event(event)
            trade = typed.trade  # Type: Trade, compile-time safe!
            self.record_trade(trade)
    """

    trade: Trade = None  # type: ignore[assignment]

    @classmethod
    def from_domain_event(cls, event: Any) -> TradeFilledEvent:
        from domain.entities.trade import Trade

        trade = event.payload.get("trade")
        if not isinstance(trade, Trade):
            raise ValueError(
                f"TRADE event must contain Trade object in payload, "
                f"got {type(trade).__name__}"
            )
        return cls(trade=trade, underlying_event=event)


@dataclass(frozen=True)
class TradeAppliedEvent(TypedDomainEvent):
    """Typed wrapper for TRADE_APPLIED events (OMS accepted trade).

    TRADE_APPLIED is the OMS-private downstream of TRADE, published only
    after idempotency check passes. This typed wrapper ensures
    PositionManager receives valid Trade objects.

    Usage:
        def on_trade_applied(self, event: DomainEvent) -> None:
            typed = TradeAppliedEvent.from_domain_event(event)
            trade = typed.trade  # Type: Trade, compile-time safe!
            self._apply_trade(trade)
    """

    trade: Trade = None  # type: ignore[assignment]

    @classmethod
    def from_domain_event(cls, event: Any) -> TradeAppliedEvent:
        from domain.entities.trade import Trade

        trade = event.payload.get("trade")
        if not isinstance(trade, Trade):
            raise ValueError(
                f"TRADE_APPLIED event must contain Trade object in payload, "
                f"got {type(trade).__name__}"
            )
        return cls(trade=trade, underlying_event=event)
