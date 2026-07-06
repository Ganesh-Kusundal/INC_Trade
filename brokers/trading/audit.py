"""Order audit trail — immutable value objects for state-transition history.

Architecture:
    The OMS persists every order state transition in an ``OrderStateHistory``
    value object that is stored alongside the corresponding ``Order`` in the
    ``OrderRepository``. The history is a pure domain construct: no I/O, no
    broker-specific knowledge, no thread-safety concerns of its own
    (concurrency is the repository's responsibility).

    Value objects live in the trading bounded context because they are
    produced and consumed by the trading layer (the OMS). They depend only
    on ``brokers.domain`` and the Python standard library.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from brokers.domain.enums import OrderStatus


@dataclass(frozen=True)
class OrderStateChange:
    """Single transition record — one row in an order's audit history.

    Attributes:
        order_id: Broker-assigned order identifier.
        correlation_id: Client-generated idempotency key (may be empty).
        from_status: Status the order transitioned from.
        to_status: Status the order transitioned to.
        reason: Free-form reason code — "place", "cancel", "modify", "fill",
            "reject", or "system".
        timestamp: When the transition was recorded.
        metadata: Extensible, read-only key/value bag for transition-specific
            context (e.g. ``{"fill_price": "2500.50", "fill_qty": "10"}``).
    """

    order_id: str
    correlation_id: str
    from_status: OrderStatus
    to_status: OrderStatus
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderStateHistory:
    """Immutable history for a single order.

    ``OrderStateHistory`` is append-only: ``append`` returns a *new* instance
    with the additional change at the end. The original instance is never
    mutated, which keeps the audit trail tamper-evident and safe to share
    across threads without external locking.

    Attributes:
        order_id: Order this history belongs to.
        changes: Tuple of recorded transitions, in chronological order.
    """

    order_id: str
    changes: tuple[OrderStateChange, ...] = ()

    def append(self, change: OrderStateChange) -> OrderStateHistory:
        """Return a new history with ``change`` appended.

        The receiver is not modified. The returned instance replaces the
        stored history in the repository.
        """
        if change.order_id != self.order_id:
            raise ValueError(
                f"Cannot append change for order_id={change.order_id!r} "
                f"to history for order_id={self.order_id!r}"
            )
        return OrderStateHistory(
            order_id=self.order_id,
            changes=(*self.changes, change),
        )

    def last_change(self) -> OrderStateChange | None:
        """Return the most recent change, or ``None`` if history is empty."""
        if not self.changes:
            return None
        return self.changes[-1]

    def transitions_from(self, status: OrderStatus) -> tuple[OrderStateChange, ...]:
        """Return all transitions that originated from ``status``."""
        return tuple(c for c in self.changes if c.from_status is status)
