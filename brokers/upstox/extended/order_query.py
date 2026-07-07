"""Upstox order query — detailed order lookup and trade history.

API: GET /v2/order/details — get order details
     GET /v2/order/trades/get-trades-for-order — get trades for order
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxOrderQuery:
    """Order query operations for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_order(self, order_id: str) -> dict[str, Any]:
        data = self._client.get(f"/v2/order/details?order_id={order_id}")
        return data.get("data", data) if isinstance(data, dict) else {}  # type: ignore[no-any-return]

    def get_trades_for_order(self, order_id: str) -> list[dict[str, Any]]:
        data = self._client.get(f"/v2/order/trades/get-trades-for-order?order_id={order_id}")
        result = data.get("data", data) if isinstance(data, dict) else data
        return result if isinstance(result, list) else []


__all__ = ["UpstoxOrderQuery"]
