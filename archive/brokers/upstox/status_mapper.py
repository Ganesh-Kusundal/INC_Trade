"""Upstox order status mapper — translates Upstox-specific status strings to canonical.

Extends :data:`domain.status_mapper.COMMON_STATUS_MAP` with
Upstox-specific status strings that have no Dhan equivalent.

Registration is lazy — call :func:`register_mappings` explicitly
during broker initialization (see :class:`~brokers.upstox.factory.UpstoxBrokerFactory`)
rather than relying on import-time side effects.
"""

from __future__ import annotations

from domain import OrderStatus
from domain.status_mapper import COMMON_STATUS_MAP

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

_registered = False


def register_mappings() -> None:
    """Register Upstox status mappings with the global StatusMapperRegistry.

    Safe to call multiple times — registration happens at most once.
    """
    global _registered
    if _registered:
        return
    from brokers.common.identity import BrokerId
    from domain.status_mapper import StatusMapperRegistry

    StatusMapperRegistry.register(BrokerId.UPSTOX, UPSTOX_STATUS_MAP)
    _registered = True
