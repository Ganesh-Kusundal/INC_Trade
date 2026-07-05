"""Capability-based port interfaces.

These protocols allow brokers to declare and expose specific capabilities
without requiring all brokers to implement every method. Brokers only
implement the capabilities they genuinely support.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from inc_trade.domain.entities import Order, OrderResponse
from inc_trade.domain.enums import OrderType, ProductType, Side, Validity


@runtime_checkable
class Capabilities(Protocol):
    """Protocol for discovering broker capabilities at runtime.

    Used by services to determine which features are available before
    attempting to use them. This enables graceful degradation and
    broker-agnostic client code.
    """

    def has_feature(self, feature: str) -> bool:
        """Check if a feature is supported by this broker.

        Args:
            feature: Capability constant (e.g., FEATURE_GTT, FEATURE_FOREVER_ORDERS)

        Returns:
            True if the broker supports this feature, False otherwise.
        """
        ...

    def get_feature_metadata(self, feature: str) -> dict[str, Any]:
        """Get metadata about a feature.

        Args:
            feature: Capability constant

        Returns:
            Dictionary with keys: description, supported_exchanges, limitations
        """
        ...


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

    def place_super_order(self, request: dict[str, Any]) -> OrderResponse: ...
    def get_super_order(self, order_id: str) -> Order | None: ...


@runtime_checkable
class ForeverOrderProvider(Protocol):
    """Broker supports forever/GTT orders."""

    def place_forever_order(self, request: dict[str, Any]) -> Order: ...
    def modify_forever_order(self, order_id: str, changes: dict[str, Any]) -> Order: ...
    def cancel_forever_order(self, order_id: str) -> bool: ...
    def get_forever_orders(self) -> list[Order]: ...


@runtime_checkable
class NewsProvider(Protocol):
    """Broker provides market news feeds."""

    def get_news(self, symbol: str | None = None) -> list[dict[str, Any]]: ...


@runtime_checkable
class KillSwitchProvider(Protocol):
    """Broker supports manual emergency kill switch activation."""

    def kill_switch(self, enable: bool) -> bool: ...


@runtime_checkable
class GTTProvider(Protocol):
    """Broker supports Good Till Triggered (GTT) orders."""

    def place_gtt(self, request: dict[str, Any]) -> OrderResponse: ...
    def modify_gtt(self, gtt_id: str, changes: dict[str, Any]) -> OrderResponse: ...
    def cancel_gtt(self, gtt_id: str) -> OrderResponse: ...
    def get_gtt_orders(self) -> list[Order]: ...


@runtime_checkable
class AlertsProvider(Protocol):
    """Broker supports price alerts and notifications."""

    def create_alert(self, symbol: str, price: float, condition: str) -> dict[str, Any]: ...
    def get_alerts(self) -> list[dict[str, Any]]: ...
    def delete_alert(self, alert_id: str) -> bool: ...


@runtime_checkable
class EDISProvider(Protocol):
    """Broker supports EDIS (Electronic Debit Instruction Slip) for CDSL."""

    def get_tpin_status(self) -> dict[str, Any]: ...
    def generate_tpin(self) -> dict[str, Any]: ...
    def get_edis_form(self, isin: str, qty: int, exchange: str) -> dict[str, Any]: ...


@runtime_checkable
class IPManagementProvider(Protocol):
    """Broker supports dynamic IP whitelisting."""

    def whitelist_ip(self, ip_address: str) -> dict[str, Any]: ...
    def get_whitelisted_ips(self) -> list[str]: ...
    def remove_whitelisted_ip(self, ip_address: str) -> dict[str, Any]: ...


@runtime_checkable
class ExitAllProvider(Protocol):
    """Broker supports panic button to close all positions/cancel all orders."""

    def close_all_positions(self) -> dict[str, Any]: ...
    def cancel_all_orders(self) -> dict[str, Any]: ...


@runtime_checkable
class SliceOrderProvider(Protocol):
    """Broker natively supports splitting large orders (slicing)."""

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
