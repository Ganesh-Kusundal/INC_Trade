"""Order lifecycle state machine — canonical transition table.

Defines which OrderStatus transitions are legal. Any transition not
in the table is considered invalid and should raise OrderStateError.
"""

from __future__ import annotations

from brokers_core.domain.enums import OrderStatus
from brokers_core.domain.exceptions import TradeXV2Error


class OrderStateError(TradeXV2Error):
    """Raised when an illegal order status transition is attempted."""


ORDER_STATUS_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset(
        {
            OrderStatus.OPEN,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        }
    ),
    OrderStatus.OPEN: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.PARTIALLY_CANCELLED,
            OrderStatus.EXPIRED,
            OrderStatus.REJECTED,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.PARTIALLY_CANCELLED,
        }
    ),
    OrderStatus.PARTIALLY_CANCELLED: frozenset(
        {
            OrderStatus.CANCELLED,
        }
    ),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
}


def is_valid_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
    allowed = ORDER_STATUS_TRANSITIONS.get(from_status, frozenset())
    return to_status in allowed


def validate_transition(from_status: OrderStatus, to_status: OrderStatus) -> None:
    if not is_valid_transition(from_status, to_status):
        raise OrderStateError(
            f"Illegal transition: {from_status.value} -> {to_status.value}"
        )
