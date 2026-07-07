"""Upstox margin calculator — order margin and brokerage calculations.

API: POST /v2/margin/order — calculate margin for order
     GET /v2/margin/brokerage — get brokerage charges
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxMargin:
    """Margin calculator for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def calculate_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Calculate margin requirements for a hypothetical order."""
        data = self._client.post("/v2/margin/order", json=payload)
        return data.get("data", data) if isinstance(data, dict) else {}  # type: ignore[no-any-return]

    def get_brokerage(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Get brokerage charges for an order."""
        data = self._client.post("/v2/margin/brokerage", json=payload)
        return data.get("data", data) if isinstance(data, dict) else {}  # type: ignore[no-any-return]


__all__ = ["UpstoxMargin"]
