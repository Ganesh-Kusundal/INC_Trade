"""Dhan extended capabilities facade — aggregates all Dhan-specific features.

Provides a single entry point for all Dhan extended capabilities,
accessible via ``adapter.extended`` or ``gateway.extended``.

Usage::

    from brokers.dhan.extended.facade import DhanExtended

    ext = DhanExtended(client=dhan_client)
    ext.super_orders.place(SuperOrderRequest(...))
    ext.forever_orders.place(ForeverOrderRequest(...))
    ext.margin.calculate(security_id="1333", ...)
"""

from __future__ import annotations

from brokers.dhan.client import DhanHttpClient

from .alerts import DhanAlerts
from .conditional_triggers import DhanConditionalTriggers
from .convert_position import DhanConvertPosition
from .edis import DhanEdis
from .exit_all import DhanExitAll
from .expired_options import DhanExpiredOptions
from .forever_orders import DhanForeverOrders
from .ip_management import DhanIpManagement
from .kill_switch import DhanKillSwitch
from .ledger import DhanLedger
from .margin import DhanMargin
from .order_lookup import DhanOrderLookup
from .slice_order import DhanSliceOrder
from .super_orders import DhanSuperOrders
from .user_profile import DhanUserProfile


class DhanExtended:
    """Facade aggregating all Dhan-specific extended capabilities.

    Each capability is exposed as a property that lazily creates the
    underlying adapter on first access.

    Usage::

        ext = DhanExtended(client=dhan_client)
        result = ext.super_orders.place(SuperOrderRequest(...))
        entries = ext.ledger.get_entries(from_date="2026-01-01")
    """

    def __init__(self, *, client: DhanHttpClient) -> None:
        self._client = client
        # Lazy-initialized capability adapters
        self._super_orders: DhanSuperOrders | None = None
        self._forever_orders: DhanForeverOrders | None = None
        self._conditional_triggers: DhanConditionalTriggers | None = None
        self._ledger: DhanLedger | None = None
        self._user_profile: DhanUserProfile | None = None
        self._ip_management: DhanIpManagement | None = None
        self._edis: DhanEdis | None = None
        self._exit_all: DhanExitAll | None = None
        self._margin: DhanMargin | None = None
        self._alerts: DhanAlerts | None = None
        self._convert_position: DhanConvertPosition | None = None
        self._kill_switch: DhanKillSwitch | None = None
        self._expired_options: DhanExpiredOptions | None = None
        self._slice_order: DhanSliceOrder | None = None
        self._order_lookup: DhanOrderLookup | None = None

    @property
    def super_orders(self) -> DhanSuperOrders:
        if self._super_orders is None:
            self._super_orders = DhanSuperOrders(client=self._client)
        return self._super_orders

    @property
    def forever_orders(self) -> DhanForeverOrders:
        if self._forever_orders is None:
            self._forever_orders = DhanForeverOrders(client=self._client)
        return self._forever_orders

    @property
    def conditional_triggers(self) -> DhanConditionalTriggers:
        if self._conditional_triggers is None:
            self._conditional_triggers = DhanConditionalTriggers(client=self._client)
        return self._conditional_triggers

    @property
    def ledger(self) -> DhanLedger:
        if self._ledger is None:
            self._ledger = DhanLedger(client=self._client)
        return self._ledger

    @property
    def user_profile(self) -> DhanUserProfile:
        if self._user_profile is None:
            self._user_profile = DhanUserProfile(client=self._client)
        return self._user_profile

    @property
    def ip_management(self) -> DhanIpManagement:
        if self._ip_management is None:
            self._ip_management = DhanIpManagement(client=self._client)
        return self._ip_management

    @property
    def edis(self) -> DhanEdis:
        if self._edis is None:
            self._edis = DhanEdis(client=self._client)
        return self._edis

    @property
    def exit_all(self) -> DhanExitAll:
        if self._exit_all is None:
            self._exit_all = DhanExitAll(client=self._client)
        return self._exit_all

    @property
    def margin(self) -> DhanMargin:
        if self._margin is None:
            self._margin = DhanMargin(client=self._client)
        return self._margin

    @property
    def alerts(self) -> DhanAlerts:
        if self._alerts is None:
            self._alerts = DhanAlerts(client=self._client)
        return self._alerts

    @property
    def convert_position(self) -> DhanConvertPosition:
        if self._convert_position is None:
            self._convert_position = DhanConvertPosition(client=self._client)
        return self._convert_position

    @property
    def kill_switch(self) -> DhanKillSwitch:
        if self._kill_switch is None:
            self._kill_switch = DhanKillSwitch(client=self._client)
        return self._kill_switch

    @property
    def expired_options(self) -> DhanExpiredOptions:
        if self._expired_options is None:
            self._expired_options = DhanExpiredOptions(client=self._client)
        return self._expired_options

    @property
    def slice_order(self) -> DhanSliceOrder:
        if self._slice_order is None:
            self._slice_order = DhanSliceOrder(client=self._client)
        return self._slice_order

    @property
    def order_lookup(self) -> DhanOrderLookup:
        if self._order_lookup is None:
            self._order_lookup = DhanOrderLookup(client=self._client)
        return self._order_lookup


__all__ = ["DhanExtended"]
