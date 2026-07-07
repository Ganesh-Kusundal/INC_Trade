"""Dhan slice order — split large orders into exchange-compliant slices.

API: POST /orders with quantity chunking handled client-side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_FREEZE_QUANTITY = 900  # NSE equity default; F&O varies


@dataclass(frozen=True, slots=True)
class SliceOrderRequest:
    """Request for a sliced order."""

    security_id: str
    exchange_segment: str
    transaction_type: str  # BUY or SELL
    quantity: int
    order_type: str = "LIMIT"
    product_type: str = "INTRADAY"
    price: float = 0.0
    trigger_price: float = 0.0
    validity: str = "DAY"
    freeze_quantity: int = _DEFAULT_FREEZE_QUANTITY


@dataclass
class SliceOrderResult:
    """Result of a sliced order placement."""

    order_ids: list[str] = field(default_factory=list)
    total_slices: int = 0
    message: str = ""

    @property
    def success(self) -> bool:
        return len(self.order_ids) > 0


class DhanSliceOrder:
    """Slice large orders into exchange-compliant quantities.

    Usage::

        slicer = DhanSliceOrder(client=dhan_client)
        result = slicer.place(SliceOrderRequest(
            security_id="2885",
            exchange_segment="NSE_EQ",
            transaction_type="BUY",
            quantity=5000,
            freeze_quantity=900,
        ))
        print(result.order_ids)
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def place(self, request: SliceOrderRequest) -> SliceOrderResult:
        """Place a sliced order, splitting into freeze_quantity chunks."""
        freeze = request.freeze_quantity or _DEFAULT_FREEZE_QUANTITY
        remaining = request.quantity
        order_ids: list[str] = []
        slice_num = 0

        while remaining > 0:
            chunk = min(remaining, freeze)
            remaining -= chunk
            slice_num += 1

            payload = {
                "dhanClientId": self._client.client_id,
                "securityId": request.security_id,
                "exchangeSegment": request.exchange_segment,
                "transactionType": request.transaction_type,
                "quantity": chunk,
                "orderType": request.order_type,
                "productType": request.product_type,
                "validity": request.validity,
            }
            if request.price > 0:
                payload["price"] = request.price
            if request.trigger_price > 0:
                payload["triggerPrice"] = request.trigger_price

            logger.info(
                "dhan_slice_order",
                security_id=request.security_id,
                slice=slice_num,
                chunk=chunk,
            )
            data = self._client.post("/orders", json=payload)
            raw = data.get("data", data) if isinstance(data, dict) else {}
            if isinstance(raw, dict):
                order_id = str(raw.get("orderId", ""))
                if order_id:
                    order_ids.append(order_id)

        return SliceOrderResult(
            order_ids=order_ids,
            total_slices=slice_num,
            message=f"Placed {len(order_ids)}/{slice_num} slices",
        )


__all__ = ["DhanSliceOrder", "SliceOrderRequest", "SliceOrderResult"]
