"""ForeverOrderProvider extension interface.

Capability gate: ``BrokerCapabilities.supports_forever_order``
Supported by: Dhan (native ForeverOrders / OCO), Upstox (via GTT adapter)

The implementations differ in failure mode: Dhan's is a first-class API object;
Upstox's is a GTT that may behave differently on edge cases (e.g. trigger on OI
vs price).  Callers should be aware of which broker they are routing to when
building strategies that depend on OCO atomicity.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from domain.enums import OrderStatus, OrderType, ProductType, Side


@dataclass(frozen=True)
class ForeverOrderRequest:
    """Input for a good-till-trigger / forever order.

    order_flag — ``"SINGLE"`` for a single-condition trigger, ``"OCO"`` for
                 one-cancels-the-other.
    price1 / trigger1 — first condition (always required).
    price2 / trigger2 — second condition for OCO orders.
    """

    symbol: str
    exchange: str
    side: Side
    quantity: int
    order_type: OrderType
    product_type: ProductType
    price1: Decimal
    trigger1: Decimal
    order_flag: str = "SINGLE"  # "SINGLE" | "OCO"
    price2: Decimal | None = None
    trigger2: Decimal | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class ForeverOrderResult:
    """Result of forever / GTT order placement."""

    success: bool
    order_id: str = ""
    message: str = ""
    status: OrderStatus = OrderStatus.OPEN


class ForeverOrderProvider(Protocol):
    """Extension interface for good-till-trigger / forever orders."""

    async def place_forever_order(
        self,
        request: ForeverOrderRequest,
        *,
        quota: object,
    ) -> ForeverOrderResult: ...

    async def cancel_forever_order(
        self,
        order_id: str,
        *,
        quota: object,
    ) -> ForeverOrderResult: ...

    async def modify_forever_order(
        self,
        order_id: str,
        *,
        price1: Decimal | None = None,
        trigger1: Decimal | None = None,
        price2: Decimal | None = None,
        trigger2: Decimal | None = None,
        quota: object,
    ) -> ForeverOrderResult: ...
