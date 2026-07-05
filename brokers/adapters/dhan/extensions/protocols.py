"""Dhan-specific extension protocols — capabilities unique to Dhan.

These protocols define broker-specific features that are NOT part of the
common broker contract. They live in the adapter layer, not the ports layer,
ensuring common interfaces remain broker-agnostic.

Usage::

    from brokers.adapters.dhan.extensions.protocols import (
        SuperOrderProvider,
        SliceOrderProvider,
        AlertsProvider,
        EDISProvider,
        IPManagementProvider,
        ExitAllProvider,
    )

    registry: ExtensionRegistryPort = ...
    super_order = registry.resolve("dhan", SuperOrderProvider)
    if super_order is not None:
        result = super_order.place_super_order({...})
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from inc_trade.domain.entities import Order, OrderResponse
from inc_trade.domain.enums import OrderType, ProductType, Side, Validity


@runtime_checkable
class SuperOrderProvider(Protocol):
    """Dhan-native super orders (bracket-like orders with entry + target + SL).

    A single-API-call bracket: one entry leg plus target and stop-loss legs
    managed server-side. The failure mode is a single atomic reject, not leg
    desynchronization — unlike client-side emulation.
    """

    def place_super_order(self, request: dict[str, Any]) -> OrderResponse: ...
    def get_super_order(self, order_id: str) -> Order | None: ...


@runtime_checkable
class SliceOrderProvider(Protocol):
    """Dhan-native server-side order slicing.

    Dhan supports server-side /sliceorder endpoint that atomically splits
    large orders into smaller child orders. This differs from client-side
    slicing (e.g., Upstox with 100ms spacing) which has partial-fill risk
    on process crash.
    """

    def place_slice_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str = "",
    ) -> OrderResponse: ...


@runtime_checkable
class AlertsProvider(Protocol):
    """Dhan-native price alerts and notifications.

    Dhan provides server-side price alert creation and management.
    """

    def create_alert(self, symbol: str, price: float, condition: str) -> dict[str, Any]: ...
    def get_alerts(self) -> list[dict[str, Any]]: ...
    def delete_alert(self, alert_id: str) -> bool: ...


@runtime_checkable
class EDISProvider(Protocol):
    """Dhan-native EDIS (Electronic Debit Instruction Slip) for CDSL.

    Required for CNC (delivery) sell operations on Dhan. Generates TPIN
    for authorizing electronic debits from the demat account.
    """

    def get_tpin_status(self) -> dict[str, Any]: ...
    def generate_tpin(self) -> dict[str, Any]: ...
    def get_edis_form(self, isin: str, qty: int, exchange: str) -> dict[str, Any]: ...


@runtime_checkable
class IPManagementProvider(Protocol):
    """Dhan-native dynamic IP whitelisting.

    Dhan provides server-side IP whitelisting for API access control.
    """

    def whitelist_ip(self, ip_address: str) -> dict[str, Any]: ...
    def get_whitelisted_ips(self) -> list[str]: ...
    def remove_whitelisted_ip(self, ip_address: str) -> dict[str, Any]: ...


@runtime_checkable
class ExitAllProvider(Protocol):
    """Dhan-native panic button — close all positions and cancel all orders.

    Emergency functionality for rapidly exiting all market exposure.
    """

    def close_all_positions(self) -> dict[str, Any]: ...
    def cancel_all_orders(self) -> dict[str, Any]: ...
