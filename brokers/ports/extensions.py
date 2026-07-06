"""Broker-agnostic extension protocols — common across all brokers.

These protocols represent capabilities that ANY broker could potentially
support. They live in the ports layer because they define the contract
between application services and broker adapters.

Broker-specific extension protocols belong in:
    - ``adapters/dhan/extensions/protocols.py`` (Dhan-specific)
    - ``adapters/upstox/extensions/protocols.py`` (Upstox-specific)

Usage::

    from brokers.ports.extensions import (
        ForeverOrderProvider,
        KillSwitchProvider,
        MarginProvider,
    )

    registry: ExtensionRegistryPort = ...
    margin = registry.resolve("dhan", MarginProvider)
    if margin is not None:
        result = margin.calculate_margin(...)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from brokers.domain.entities import Order, OrderResponse
from brokers.domain.enums import OrderType, ProductType


@runtime_checkable
class MarginProvider(Protocol):
    """Broker supports margin calculation previews.

    Any broker that can calculate margin requirements before order placement
    implements this protocol. The RiskManager depends on this port, not on
    broker-specific implementations.
    """

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
class KillSwitchProvider(Protocol):
    """Broker supports manual emergency kill switch activation.

    A kill switch immediately blocks all order placement. Supported by
    brokers that provide server-side order blocking.
    """

    def kill_switch(self, enable: bool) -> bool: ...


@runtime_checkable
class ForeverOrderProvider(Protocol):
    """Broker supports forever/GTT (Good-Till-Triggered) orders.

    Multi-broker protocol: Dhan implements it natively as ForeverOrders,
    Upstox implements it via GTT adapter. Both expose the same interface
    so strategies can be broker-agnostic.
    """

    def place_forever_order(self, request: dict[str, Any]) -> Order: ...
    def modify_forever_order(self, order_id: str, changes: dict[str, Any]) -> Order: ...
    def cancel_forever_order(self, order_id: str) -> bool: ...
    def get_forever_orders(self) -> list[Order]: ...
