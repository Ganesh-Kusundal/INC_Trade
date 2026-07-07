"""Dhan forever/GTT orders — place, modify, cancel Good Till Triggered orders.

Dhan API endpoints:
- POST /forever/orders — place forever order (SINGLE or OCO)
- PUT /forever/orders — modify forever order
- DELETE /forever/orders/{order_id} — cancel forever order
- GET /forever/orders — get all forever orders
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ForeverOrderRequest:
    """Request payload for placing a forever/GTT order."""

    security_id: str
    exchange_segment: str
    transaction_type: str  # BUY or SELL
    quantity: int
    price: float
    trigger_price: float
    order_flag: str = "SINGLE"  # SINGLE or OCO
    order_type: str = "LIMIT"
    product_type: str = "INTRADAY"
    validity: str = "DAY"
    leg_name: str = "ENTRY"


class DhanForeverOrders:
    """Forever/GTT order management for Dhan.

    Usage::

        forever = DhanForeverOrders(client=dhan_client)
        result = forever.place(ForeverOrderRequest(...))
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def place(self, request: ForeverOrderRequest) -> dict[str, Any]:
        """Place a forever (GTT) order."""
        payload = {
            "dhanClientId": self._client.client_id,
            "securityId": request.security_id,
            "exchangeSegment": request.exchange_segment,
            "transactionType": request.transaction_type,
            "quantity": str(request.quantity),
            "price": str(request.price),
            "trigger_Price": str(request.trigger_price),
            "orderFlag": request.order_flag,
            "orderType": request.order_type,
            "productType": request.product_type,
            "validity": request.validity,
            "legName": request.leg_name,
        }
        logger.info("dhan_forever_order_place", security_id=request.security_id)
        return self._client.post("/forever/orders", json=payload)

    def modify(
        self,
        order_id: str,
        *,
        price: float | None = None,
        quantity: int | None = None,
        trigger_price: float | None = None,
    ) -> dict[str, Any]:
        """Modify a forever order."""
        payload: dict[str, Any] = {
            "dhanClientId": self._client.client_id,
            "orderId": order_id,
        }
        if price is not None:
            payload["price"] = str(price)
        if quantity is not None:
            payload["quantity"] = str(quantity)
        if trigger_price is not None:
            payload["trigger_Price"] = str(trigger_price)
        logger.info("dhan_forever_order_modify", order_id=order_id)
        return self._client.put("/forever/orders", json=payload)

    def cancel(self, order_id: str) -> dict[str, Any]:
        """Cancel a forever order."""
        logger.info("dhan_forever_order_cancel", order_id=order_id)
        return self._client.delete(f"/forever/orders/{order_id}")

    def get_orders(self) -> dict[str, Any]:
        """Get all forever orders."""
        return self._client.get("/forever/orders")


__all__ = ["DhanForeverOrders", "ForeverOrderRequest"]
