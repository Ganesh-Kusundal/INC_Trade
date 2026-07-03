"""Capability-based port interfaces.

These protocols allow brokers to declare and expose specific capabilities
without requiring all brokers to implement every method. Brokers only
implement the capabilities they genuinely support.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from brokers.domain.entities import Order, OrderResponse
from brokers.domain.enums import OrderType, ProductType, Side, Validity


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
class NewsProvider(Protocol):
    """Broker provides market news feeds."""

    def get_news(self, symbol: str | None = None) -> list[dict]: ...




@runtime_checkable
class KillSwitchProvider(Protocol):
    """Broker supports manual emergency kill switch activation."""

    def kill_switch(self, enable: bool) -> bool: ...


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
