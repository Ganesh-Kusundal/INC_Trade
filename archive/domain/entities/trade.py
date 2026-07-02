"""Trade domain entity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from domain.types import ProductType, Side


@dataclass(slots=True, frozen=True)
class Trade:
    """Canonical trade — returned by every broker adapter."""

    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal = Decimal("0")
    trade_value: Decimal = Decimal("0")
    timestamp: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None

    @property
    def value(self) -> Decimal:
        if self.trade_value > 0:
            return self.trade_value
        return self.price * Decimal(str(self.quantity))
