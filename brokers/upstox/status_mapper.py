"""Upstox order status mapper — translates Upstox-specific status strings to canonical.

Extends :data:`domain.status_mapper.COMMON_STATUS_MAP` with
Upstox-specific status strings that have no Dhan equivalent.
"""

from __future__ import annotations

from domain import OrderStatus
from domain.status_mapper import COMMON_STATUS_MAP, StatusMapperRegistry

UPSTOX_STATUS_MAP: dict[str, OrderStatus] = {
    **COMMON_STATUS_MAP,
    # Upstox-specific additions
    "OPEN_ORDER": OrderStatus.OPEN,
    "TRIGGER_ORDER": OrderStatus.OPEN,
    "CANCEL_PENDING": OrderStatus.OPEN,
    "REJECTED_BY_BROKER": OrderStatus.REJECTED,
    "REJECTED_BY_EXCHANGE": OrderStatus.REJECTED,
    "MODIFIED": OrderStatus.OPEN,
    "MODIFIED_PENDING": OrderStatus.OPEN,
    "PLACED": OrderStatus.OPEN,
    "COMPLETED": OrderStatus.FILLED,
}

# Register Upstox mappings at module load
StatusMapperRegistry.register("upstox", UPSTOX_STATUS_MAP)
