"""Dhan order status mapper — translates Dhan-specific status strings to canonical.

Extends :data:`domain.status_mapper.COMMON_STATUS_MAP` with
Dhan-specific status strings that have no Upstox equivalent.
"""

from __future__ import annotations

from domain import OrderStatus
from domain.status_mapper import COMMON_STATUS_MAP, StatusMapperRegistry

DHAN_STATUS_MAP: dict[str, OrderStatus] = {
    **COMMON_STATUS_MAP,
    # Dhan-specific additions (TRANSIT, TRIGGER_PENDING, PENDING,
    # OPEN_PENDING, PUT_ORDER_REQ_RECEIVED are already in COMMON_STATUS_MAP)
    "PLACED": OrderStatus.OPEN,
    "TRIGGERED": OrderStatus.OPEN,
    "PARTIALLY_CANCELLED": OrderStatus.PARTIALLY_CANCELLED,
}

# Register Dhan mappings at module load
StatusMapperRegistry.register("dhan", DHAN_STATUS_MAP)
