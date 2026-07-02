"""Shared infrastructure models — routing, health, and registry snapshots.

These are the data types used between the registry, router, quota scheduler,
and coordinator layers.  They are distinct from the domain models in ``domain/``
(which are broker-neutral business concepts) and from the gateway DTOs (which are
broker-wire representations).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

# ---------------------------------------------------------------------------
# Operation kinds
# ---------------------------------------------------------------------------


class OperationKind(str, Enum):
    """Classifies a broker operation for routing and quota purposes.

    Routing policy is defined per operation kind so that, for example, the
    market-data source and the execution account can be different brokers.
    """

    PLACE_ORDER = "place_order"
    CANCEL_ORDER = "cancel_order"
    MODIFY_ORDER = "modify_order"
    GET_POSITIONS = "get_positions"
    GET_MARGINS = "get_margins"
    GET_ORDERS = "get_orders"
    GET_TRADES = "get_trades"
    GET_QUOTE = "get_quote"
    GET_DEPTH = "get_depth"
    GET_HISTORICAL_BARS = "get_historical_bars"
    OPEN_MARKET_STREAM = "open_market_stream"
    OPEN_ORDER_STREAM = "open_order_stream"
    FETCH_OPTION_CHAIN = "fetch_option_chain"
    FETCH_NEWS = "fetch_news"
    FETCH_FUNDAMENTALS = "fetch_fundamentals"
    FETCH_MARKET_INTELLIGENCE = "fetch_market_intelligence"
    PLACE_SUPER_ORDER = "place_super_order"
    PLACE_FOREVER_ORDER = "place_forever_order"
    PLACE_SLICE_ORDER = "place_slice_order"

    def is_execution(self) -> bool:
        return self in {
            OperationKind.PLACE_ORDER,
            OperationKind.CANCEL_ORDER,
            OperationKind.MODIFY_ORDER,
            OperationKind.PLACE_SUPER_ORDER,
            OperationKind.PLACE_FOREVER_ORDER,
            OperationKind.PLACE_SLICE_ORDER,
        }

    def is_market_data(self) -> bool:
        return self in {
            OperationKind.GET_QUOTE,
            OperationKind.GET_DEPTH,
            OperationKind.GET_HISTORICAL_BARS,
            OperationKind.OPEN_MARKET_STREAM,
            OperationKind.FETCH_OPTION_CHAIN,
        }

    def is_enrichment(self) -> bool:
        return self in {
            OperationKind.FETCH_NEWS,
            OperationKind.FETCH_FUNDAMENTALS,
            OperationKind.FETCH_MARKET_INTELLIGENCE,
        }


# ---------------------------------------------------------------------------
# Routing request & decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingRequest:
    """Input to BrokerRouter.route().

    operation       — the kind of operation being requested.
    instrument      — optional instrument identifier (symbol:exchange string)
                      for market-data and historical operations.
    required_features — feature names that the selected broker must support;
                        checked against BrokerCapabilities.supports().
    trace_id        — correlation ID from the calling context.
    user_mode       — ``"auto"`` lets policy decide; any other value is a
                      hint (treated as advisory, not mandatory).
    """

    operation: OperationKind
    trace_id: str
    instrument: str | None = None
    required_features: frozenset[str] = field(default_factory=frozenset)
    user_mode: str = "auto"


@dataclass(frozen=True)
class RouteDecision:
    """Auditable result of BrokerRouter.route().

    Every routing decision is logged as a structured event with all fields
    present so the decision can be replayed and explained after the fact.

    primary_broker  — the broker selected for this operation.
    fallback_brokers — ordered fallback chain if primary fails.
    parallel_brokers — brokers to use in parallel (historical federation only).
    policy_version  — identifier of the policy snapshot that produced this decision.
    reason_codes    — machine-readable list of reasons (e.g. ``["capability_match",
                      "best_quota_headroom"]``).
    rejected        — mapping of broker_id → rejection reason for audit.
    trace_id        — echoed from RoutingRequest for correlation.
    decided_at      — UTC timestamp of the decision.
    """

    operation: OperationKind
    primary_broker: str
    trace_id: str
    policy_version: str
    fallback_brokers: tuple[str, ...] = field(default_factory=tuple)
    parallel_brokers: tuple[str, ...] = field(default_factory=tuple)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    rejected: dict[str, str] = field(default_factory=dict)
    decided_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def has_fallback(self) -> bool:
        return len(self.fallback_brokers) > 0

    def to_audit_dict(self) -> dict:
        """Return a structured dict suitable for logging."""
        return {
            "event": "routing.decision",
            "trace_id": self.trace_id,
            "operation": self.operation.value,
            "primary_broker": self.primary_broker,
            "fallback_brokers": list(self.fallback_brokers),
            "parallel_brokers": list(self.parallel_brokers),
            "policy_version": self.policy_version,
            "reason_codes": list(self.reason_codes),
            "rejected": self.rejected,
            "decided_at": self.decided_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Health snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrokerHealthSnapshot:
    """Point-in-time health view used by the router for selection decisions."""

    broker_id: str
    alive: bool
    auth_valid: bool = True
    error_rate: float = 0.0  # 0.0-1.0
    latency_p50_ms: float = 0.0
    reason: str = ""
    observed_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def is_usable(self) -> bool:
        """Return True when the broker can be selected for routing."""
        return self.alive and self.auth_valid


# ---------------------------------------------------------------------------
# Registry snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistrySnapshot:
    """Point-in-time view of all registered brokers — used for audit and observability."""

    broker_ids: tuple[str, ...]
    health: dict[str, BrokerHealthSnapshot]
    taken_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
