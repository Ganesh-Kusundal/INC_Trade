"""Broker order transport port — application-layer boundary to adapters."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from domain.entities import OrderResponse


@runtime_checkable
class OrderTransportPort(Protocol):
    """Minimal gateway surface for OMS submit_fn wiring."""

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: str,
        quantity: int,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        correlation_id: str | None = None,
    ) -> OrderResponse: ...


__all__ = ["OrderTransportPort"]
