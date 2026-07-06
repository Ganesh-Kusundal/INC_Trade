"""Order guard — enforces live-order kill switch at the service layer."""

from __future__ import annotations

from inc_trade.domain.entities import OrderResponse
from inc_trade.ports.order_guard import OrderGuardPort


class AllowLiveOrdersGuard:
    """Blocks order mutations when ``allow_live_orders`` is False."""

    def __init__(self, allow_live_orders: bool = True) -> None:
        self._allow_live_orders = allow_live_orders

    @property
    def allow_live_orders(self) -> bool:
        return self._allow_live_orders

    @allow_live_orders.setter
    def allow_live_orders(self, value: bool) -> None:
        self._allow_live_orders = value

    def check_live_order_allowed(self) -> OrderResponse | None:
        if self._allow_live_orders:
            return None
        return OrderResponse.live_orders_disabled()


def order_guard_from_flag(allow_live_orders: bool) -> OrderGuardPort:
    """Factory for the standard allow-live-orders guard."""
    return AllowLiveOrdersGuard(allow_live_orders=allow_live_orders)
