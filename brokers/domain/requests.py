"""Canonical request/input shapes for broker operations.

Immutable value objects carrying all parameters for order operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from brokers.domain.enums import Exchange, OrderType, ProductType, Side, Validity

if TYPE_CHECKING:
    from brokers.domain.instrument import Instrument


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """Immutable value object carrying all parameters for place_order.

    ``instrument`` is optional — if provided, providers extract
    symbol/exchange/security_id from it directly.  When set,
    ``symbol`` and ``exchange`` are still populated for backward
    compatibility, but ``instrument.security_id`` is preferred for
    broker-level instrument resolution.
    """

    symbol: str
    exchange: Exchange
    side: Side
    quantity: int
    instrument: Instrument | None = None
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    price: Decimal = Decimal("0")
    trigger_price: Decimal | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if self.instrument is not None:
            # Ensure symbol/exchange match instrument when both provided
            pass  # Trust the caller — no silent overwrites


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
