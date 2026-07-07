"""Upstox GTT (Good Till Triggered) orders.

API: POST /v2/order/gtt/place — place GTT order
     PUT /v2/order/gtt/modify — modify GTT order
     DELETE /v2/order/gtt/cancel — cancel GTT order
     GET /v2/order/gtt/get-orders — list GTT orders
     GET /v2/order/gtt/get-details — get GTT order details
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxGTT:
    """GTT order management for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def place_single(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("upstox_gtt_place_single")
        return self._client.post("/v2/order/gtt/place", json=payload)

    def place_multi(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("upstox_gtt_place_multi")
        return self._client.post("/v2/order/gtt/place", json=payload)

    def modify(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("upstox_gtt_modify")
        return self._client.put("/v2/order/gtt/modify", json=payload)

    def cancel(self, gtt_order_id: str) -> dict[str, Any]:
        logger.info("upstox_gtt_cancel", gtt_order_id=gtt_order_id)
        return self._client.delete(f"/v2/order/gtt/cancel?order_id={gtt_order_id}")

    def get_orders(self) -> list[dict[str, Any]]:
        data = self._client.get("/v2/order/gtt/get-orders")
        result = data.get("data", data) if isinstance(data, dict) else data
        return result if isinstance(result, list) else []

    def get_details(self, gtt_order_id: str) -> dict[str, Any]:
        data = self._client.get(f"/v2/order/gtt/get-details?order_id={gtt_order_id}")
        return data.get("data", data) if isinstance(data, dict) else {}  # type: ignore[no-any-return]


__all__ = ["UpstoxGTT"]
