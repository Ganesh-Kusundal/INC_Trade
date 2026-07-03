"""Capability-based port interfaces.

These protocols allow brokers to declare and expose specific capabilities
without requiring all brokers to implement every method. Brokers only
implement the capabilities they genuinely support.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from brokers.domain.entities import Order, OrderResponse
from brokers.domain.enums import OrderType, ProductType


@runtime_checkable
class MarginProvider(Protocol):
    """Broker supports margin calculation previews."""

    def calculate_margin(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        product_type: ProductType = ProductType.INTRADAY,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
    ) -> OrderResponse: ...


@runtime_checkable
class SuperOrderProvider(Protocol):
    """Broker supports super orders (bracket-like orders)."""

    def place_super_order(self, request: dict) -> OrderResponse: ...
    def get_super_order(self, order_id: str) -> Order | None: ...


@runtime_checkable
class ForeverOrderProvider(Protocol):
    """Broker supports forever/GTT orders."""

    def place_forever_order(self, request: dict) -> Order: ...
    def modify_forever_order(self, order_id: str, changes: dict) -> Order: ...
    def cancel_forever_order(self, order_id: str) -> bool: ...
    def get_forever_orders(self) -> list[Order]: ...


@runtime_checkable
class ConditionalTriggerProvider(Protocol):
    """Broker supports conditional alerts/triggers."""

    def place_alert(self, request: dict) -> str: ...
    def get_alert(self, alert_id: str) -> dict: ...
    def list_alerts(self) -> list[dict]: ...
    def delete_alert(self, alert_id: str) -> bool: ...


@runtime_checkable
class EDISTransferProvider(Protocol):
    """Broker supports EDIS (electronic delivery instruction) transfers."""

    def submit_edis(self, symbol: str, quantity: int, **kwargs) -> dict: ...
    def check_edis_status(self, isin: str) -> dict: ...


@runtime_checkable
class IPManagementProvider(Protocol):
    """Broker supports static IP management."""

    def get_static_ip(self) -> dict[str, str]: ...
    def set_static_ip(
        self, primary: str, secondary: str | None = None
    ) -> dict[str, str]: ...


@runtime_checkable
class LedgerProvider(Protocol):
    """Broker supports ledger history retrieval."""

    def get_ledger(self, from_date: str, to_date: str) -> list[dict]: ...


@runtime_checkable
class UserProfileProvider(Protocol):
    """Broker supports user profile data."""

    def get_profile(self) -> dict: ...


@runtime_checkable
class ReconciliationProvider(Protocol):
    """Broker supports order/portfolio reconciliation."""

    def reconcile(self) -> dict: ...
    def auto_repair(self, enabled: bool) -> None: ...
