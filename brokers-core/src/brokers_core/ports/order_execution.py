"""Order execution port — order lifecycle operations.

Narrow interface (ISP) for order management. Broker adapters
implement this to provide order placement, cancellation, and queries.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from brokers_core.domain.entities import Order, OrderResponse
from brokers_core.domain.enums import OrderType, ProductType, Side, Validity


@runtime_checkable
class OrderExecutionPort(Protocol):
    def place_order(
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
    ) -> OrderResponse: ...

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> OrderResponse: ...

    def cancel_order(self, order_id: str) -> OrderResponse: ...

    def get_order(self, order_id: str) -> Order | None: ...

    def get_orderbook(self) -> list[Order]: ...
