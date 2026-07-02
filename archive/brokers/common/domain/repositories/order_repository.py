"""Order repository protocol — datalake/API depends on this, not concrete OMS."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from domain import Order, OrderResponse
from domain.requests import OrderRequest


@runtime_checkable
class OrderRepository(Protocol):
    """Persistence/query port for orders."""

    def get_orders(self, *, symbol: str | None = None, status: Any = None) -> list[Order]:
        """Return orders, optionally filtered."""
        ...

    def get_order(self, order_id: str) -> Order | None:
        """Return a single order by id."""
        ...

    def place_order(self, request: OrderRequest) -> OrderResponse:
        """Submit a new order."""
        ...

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an existing order."""
        ...


__all__ = ["OrderRepository"]
