"""Dhan margin calculator — real-time margin requirement calculations.

API: POST /margincalculator — calculate margin requirements
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MarginResult:
    """Margin calculation result."""

    total_margin: float = 0.0
    span_margin: float = 0.0
    exposure_margin: float = 0.0
    available_balance: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarginResult:
        return cls(
            total_margin=float(data.get("totalMargin", 0) or 0),
            span_margin=float(data.get("spanMargin", 0) or 0),
            exposure_margin=float(data.get("exposureMargin", 0) or 0),
            available_balance=float(data.get("availableBalance", 0) or 0),
        )


class DhanMargin:
    """Margin calculator for Dhan.

    Usage::

        margin = DhanMargin(client=dhan_client)
        result = margin.calculate(security_id="1333", exchange_segment="NSE_EQ",
                                   transaction_type="BUY", quantity=10, price=2500.0)
        print(f"Required margin: {result.total_margin}")
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def calculate(
        self,
        security_id: str,
        exchange_segment: str,
        transaction_type: str = "BUY",
        quantity: int = 1,
        price: float = 0.0,
        product_type: str = "CNC",
        order_type: str = "MARKET",
    ) -> MarginResult:
        """Calculate margin requirements for a hypothetical order."""
        payload = {
            "dhanClientId": self._client.client_id,
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "transactionType": transaction_type,
            "quantity": str(quantity),
            "price": str(price),
            "productType": product_type,
            "orderType": order_type,
        }
        data = self._client.post("/margincalculator", json=payload)
        raw = data.get("data", data) if isinstance(data, dict) else {}
        return MarginResult.from_dict(raw if isinstance(raw, dict) else {})


__all__ = ["DhanMargin", "MarginResult"]
