"""Dhan order status mapping — single source of truth.

Three consumers share this mapping:
- Streaming decoder (wire string → canonical string)
- Order feed (wire string → canonical string)
- Mapper (wire string → OrderStatus enum)

Keep the dict here; consumers import what they need.
"""

from __future__ import annotations

from brokers.domain.enums import OrderStatus

# Wire-format status strings → canonical flat strings
DHAN_STATUS_TO_STRING: dict[str, str] = {
    "TRANSIT": "OPEN",
    "PENDING": "OPEN",
    "PENDING_ORDER": "OPEN",
    "VALIDATED": "OPEN",
    "AMO_RECEIVED": "OPEN",
    "OPEN": "OPEN",
    "TRADED": "FILLED",
    "FILLED": "FILLED",
    "PART_TRADED": "PARTIALLY_FILLED",
    "PART_FILLED": "PARTIALLY_FILLED",
    "EXPIRED": "EXPIRED",
    "REJECTED": "REJECTED",
    "CANCELLED": "CANCELLED",
    "CANCELED": "CANCELLED",
    "MODIFIED": "OPEN",
}

# Wire-format status strings → OrderStatus enum
DHAN_STATUS_TO_ENUM: dict[str, OrderStatus] = {
    "TRANSIT": OrderStatus.OPEN,
    "PENDING": OrderStatus.OPEN,
    "PENDING_ORDER": OrderStatus.OPEN,
    "VALIDATED": OrderStatus.OPEN,
    "AMO_RECEIVED": OrderStatus.OPEN,
    "OPEN": OrderStatus.OPEN,
    "TRADED": OrderStatus.FILLED,
    "FILLED": OrderStatus.FILLED,
    "PART_TRADED": OrderStatus.PARTIALLY_FILLED,
    "PART_FILLED": OrderStatus.PARTIALLY_FILLED,
    "EXPIRED": OrderStatus.EXPIRED,
    "REJECTED": OrderStatus.REJECTED,
    "CANCELLED": OrderStatus.CANCELLED,
    "CANCELED": OrderStatus.CANCELLED,
    "MODIFIED": OrderStatus.OPEN,
}

_DEFAULT_STRING = "UNKNOWN"
_DEFAULT_ENUM = OrderStatus.UNKNOWN


def normalize_status(raw: str) -> str:
    """Map a Dhan wire-status string to a canonical flat string."""
    return DHAN_STATUS_TO_STRING.get(raw.upper(), _DEFAULT_STRING)


def to_order_status(raw: str) -> OrderStatus:
    """Map a Dhan wire-status string to an OrderStatus enum value."""
    return DHAN_STATUS_TO_ENUM.get(raw.upper(), _DEFAULT_ENUM)


__all__ = [
    "DHAN_STATUS_TO_STRING",
    "DHAN_STATUS_TO_ENUM",
    "normalize_status",
    "to_order_status",
]
