"""Orders capability group for Upstox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain import OrderRequest, OrderResponse


@dataclass
class OrdersCapability:
    """Order placement, modification, and advanced order types."""

    order_command: Any
    order_query: Any
    slice: Any
    cover: Any
    gtt: Any
    alert: Any
    exit_all: Any
    order_client: Any

    def place(self, request: OrderRequest) -> OrderResponse:
        return self.order_command.place_order(request)

    def cancel(self, order_id: str) -> OrderResponse:
        return self.order_command.cancel_order(order_id)

    def modify(self, order_id: str, **changes: Any) -> OrderResponse:
        return self.order_command.modify_order(order_id, **changes)
