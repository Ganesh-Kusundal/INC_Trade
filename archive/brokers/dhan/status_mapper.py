"""Dhan order status mapper — translates Dhan-specific status strings to canonical.

Extends :data:`domain.status_mapper.COMMON_STATUS_MAP` with
Dhan-specific status strings that have no Upstox equivalent.

Registration is lazy — call :func:`register_mappings` explicitly
during broker initialization (see :class:`~brokers.dhan.factory.BrokerFactory`)
rather than relying on import-time side effects.
"""

from __future__ import annotations

from domain import OrderStatus
from domain.status_mapper import COMMON_STATUS_MAP

DHAN_STATUS_MAP: dict[str, OrderStatus] = {
    **COMMON_STATUS_MAP,
    # Dhan-specific additions (TRANSIT, TRIGGER_PENDING, PENDING,
    # OPEN_PENDING, PUT_ORDER_REQ_RECEIVED are already in COMMON_STATUS_MAP)
    "PLACED": OrderStatus.OPEN,
    "TRIGGERED": OrderStatus.OPEN,
    "PARTIALLY_CANCELLED": OrderStatus.PARTIALLY_CANCELLED,
}

_registered = False


def register_mappings() -> None:
    """Register Dhan status mappings with the global StatusMapperRegistry.

    Safe to call multiple times — registration happens at most once.
    """
    global _registered
    if _registered:
        return
    from brokers.common.identity import BrokerId
    from domain.status_mapper import StatusMapperRegistry

    StatusMapperRegistry.register(BrokerId.DHAN, DHAN_STATUS_MAP)
    _registered = True
