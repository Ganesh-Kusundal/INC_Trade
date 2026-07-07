"""Canonical request/input shapes for broker operations.

Immutable value objects carrying all parameters for order operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from brokers.domain.enums import Exchange, OrderType, ProductType, Side, Validity


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """Immutable value object carrying all parameters for place_order.

    ``instrument`` is optional — if provided, the provider can extract
    symbol/exchange from it.  If not, ``symbol`` and ``exchange`` are used.
    """

    symbol: str
    exchange: Exchange
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    price: Decimal = Decimal("0")
    trigger_price: Decimal | None = None
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModifyOrderRequest:
    """Input model for modifying an existing order."""

    order_id: str
    quantity: int | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    order_type: OrderType | None = None
    validity: Validity | None = None
    product_type: ProductType | None = None


__all__ = [
    "ModifyOrderRequest",
    "OrderRequest",
]
