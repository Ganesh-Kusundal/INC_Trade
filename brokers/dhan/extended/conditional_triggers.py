"""Dhan conditional triggers — automated price-based order triggers.

API: POST /alerts/orders — create conditional trigger
     GET /alerts/orders — list triggers
     DELETE /alerts/orders/{id} — cancel trigger
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ConditionalTriggerRequest:
    """Request for a conditional trigger order."""

    security_id: str
    exchange_segment: str
    transaction_type: str  # BUY or SELL
    quantity: int
    price: float
    trigger_price: float
    comparison_type: str = "LTP_GTE"  # LTP_GTE, LTP_LTE
    order_type: str = "LIMIT"
    product_type: str = "CNC"
    validity: str = "DAY"


class DhanConditionalTriggers:
    """Conditional trigger management for Dhan.

    Usage::

        triggers = DhanConditionalTriggers(client=dhan_client)
        result = triggers.place(ConditionalTriggerRequest(...))
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def place(self, request: ConditionalTriggerRequest) -> dict[str, Any]:
        """Create a conditional trigger order."""
        payload = {
            "dhanClientId": self._client.client_id,
            "securityId": request.security_id,
            "exchangeSegment": request.exchange_segment,
            "transactionType": request.transaction_type,
            "quantity": str(request.quantity),
            "price": str(request.price),
            "triggerPrice": str(request.trigger_price),
            "comparisonType": request.comparison_type,
            "orderType": request.order_type,
            "productType": request.product_type,
            "validity": request.validity,
        }
        logger.info("dhan_conditional_trigger_place", security_id=request.security_id)
        return self._client.post("/alerts/orders", json=payload)

    def get_triggers(self) -> dict[str, Any]:
        """Get all conditional triggers."""
        return self._client.get("/alerts/orders")

    def cancel(self, trigger_id: str) -> dict[str, Any]:
        """Cancel a conditional trigger."""
        logger.info("dhan_conditional_trigger_cancel", trigger_id=trigger_id)
        return self._client.delete(f"/alerts/orders/{trigger_id}")


__all__ = ["DhanConditionalTriggers", "ConditionalTriggerRequest"]
