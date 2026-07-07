"""Subscription plan — SSOT for which instruments a stream should carry.

The ``SubscriptionPlan`` is an immutable snapshot of the set of instruments
and the data mode that a stream should be subscribed to.  The orchestrator
uses the plan as the source of truth for reconnect replay: when a connection
drops and reconnects, the entire plan is re-sent to the server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StreamMode(str, Enum):
    """Data mode for market data subscriptions."""

    LTP = "ltp"
    QUOTE = "quote"
    FULL = "full"
    DEPTH = "depth"


@dataclass(frozen=True, slots=True)
class InstrumentKey:
    """Uniquely identifies an instrument for streaming purposes."""

    symbol: str
    exchange: str
    # Broker-specific ID (Dhan numeric, Upstox instrument_key strings).
    # security_id is part of identity to prevent silent dedup across brokers.
    security_id: str = ""

    def __hash__(self) -> int:
        # Include security_id so distinct broker IDs (Dhan numeric vs
        # Upstox instrument_key strings) are not silently deduped in
        # plan/diff operations across brokers.
        return hash((self.symbol, self.exchange, self.security_id))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InstrumentKey):
            return NotImplemented
        return (
            self.symbol == other.symbol
            and self.exchange == other.exchange
            and self.security_id == other.security_id
        )


@dataclass(frozen=True, slots=True)
class SubscriptionPlan:
    """Immutable snapshot of the desired subscription state.

    This is the source of truth for what the stream should be subscribed
    to.  On reconnect, the entire plan is replayed to the server.
    """

    instruments: frozenset[InstrumentKey] = field(default_factory=frozenset)
    mode: StreamMode = StreamMode.QUOTE

    def __len__(self) -> int:
        return len(self.instruments)

    def __bool__(self) -> bool:
        return len(self.instruments) > 0

    def with_added(self, *keys: InstrumentKey) -> SubscriptionPlan:
        """Return a new plan with the given instruments added."""
        return SubscriptionPlan(
            instruments=self.instruments | frozenset(keys),
            mode=self.mode,
        )

    def with_removed(self, *keys: InstrumentKey) -> SubscriptionPlan:
        """Return a new plan with the given instruments removed."""
        return SubscriptionPlan(
            instruments=self.instruments - frozenset(keys),
            mode=self.mode,
        )

    def with_mode(self, mode: StreamMode) -> SubscriptionPlan:
        """Return a new plan with a different mode."""
        return SubscriptionPlan(instruments=self.instruments, mode=mode)

    def diff(self, other: SubscriptionPlan) -> SubscriptionDiff:
        """Compute what changed between this plan and another."""
        added = self.instruments - other.instruments
        removed = other.instruments - self.instruments
        return SubscriptionDiff(added=frozenset(added), removed=frozenset(removed))


@dataclass(frozen=True, slots=True)
class SubscriptionDiff:
    """Describes the difference between two subscription plans."""

    added: frozenset[InstrumentKey] = field(default_factory=frozenset)
    removed: frozenset[InstrumentKey] = field(default_factory=frozenset)

    @property
    def has_changes(self) -> bool:
        return len(self.added) > 0 or len(self.removed) > 0


__all__ = [
    "StreamMode",
    "InstrumentKey",
    "SubscriptionPlan",
    "SubscriptionDiff",
]
