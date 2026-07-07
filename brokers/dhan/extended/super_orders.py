"""Dhan super/bracket orders — place, modify, cancel bracket orders.

Dhan API endpoints:
- POST /super/orders — place super order (ENTRY)
- PUT /super/orders — modify super order (TARGET, STOP_LOSS)
- DELETE /super/orders/{order_id} — cancel super order
- GET /super/orders — get all super orders
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SuperOrderRequest:
    """Request payload for placing a super/bracket order."""

    security_id: str
    exchange_segment: str
    transaction_type: str  # BUY or SELL
    quantity: int
    price: float
    target_price: float
    stop_loss_price: float
    order_type: str = "LIMIT"
    product_type: str = "INTRADAY"
    validity: str = "DAY"
    trailing_gap: float = 0.0


class DhanSuperOrders:
    """Super/bracket order management for Dhan.

    Usage::

        super_orders = DhanSuperOrders(client=dhan_client)
        result = super_orders.place(SuperOrderRequest(...))
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def place(self, request: SuperOrderRequest) -> dict[str, Any]:
        """Place a super (bracket) order with target and stop-loss legs."""
        payload = {
            "dhanClientId": self._client.client_id,
            "securityId": request.security_id,
            "exchangeSegment": request.exchange_segment,
            "transactionType": request.transaction_type,
            "quantity": request.quantity,
            "price": request.price,
            "targetPrice": request.target_price,
            "stopLossPrice": request.stop_loss_price,
            "orderType": request.order_type,
            "productType": request.product_type,
            "validity": request.validity,
            "trailingJump": request.trailing_gap,
        }
        logger.info("dhan_super_order_place", security_id=request.security_id)
        return self._client.post("/super/orders", json=payload)

    def modify(
        self,
        order_id: str,
        *,
        leg_name: str = "TARGET",
        price: float | None = None,
        quantity: int | None = None,
    ) -> dict[str, Any]:
        """Modify a super order leg (TARGET or STOP_LOSS)."""
        payload: dict[str, Any] = {
            "dhanClientId": self._client.client_id,
            "orderId": order_id,
            "legName": leg_name,
        }
        if price is not None:
            payload["price"] = str(price)
        if quantity is not None:
            payload["quantity"] = str(quantity)
        logger.info("dhan_super_order_modify", order_id=order_id, leg=leg_name)
        return self._client.put("/super/orders", json=payload)

    def cancel(self, order_id: str) -> dict[str, Any]:
        """Cancel a super order."""
        logger.info("dhan_super_order_cancel", order_id=order_id)
        return self._client.delete(f"/super/orders/{order_id}")

    def get_orders(self) -> dict[str, Any]:
        """Get all super orders."""
        return self._client.get("/super/orders")


__all__ = ["DhanSuperOrders", "SuperOrderRequest"]
