"""Upstox GTT (Good Till Triggered) orders.

API: POST /v3/order/gtt/place — place GTT order
     PUT /v3/order/gtt/modify — modify GTT order
     DELETE /v3/order/gtt/cancel — cancel GTT order
     GET /v3/order/gtt/get-orders — list GTT orders
     GET /v3/order/gtt/get-details — get GTT order details

Methods are ``async`` so they can be awaited through the typed extension
access layer. Synchronous HTTP calls are offloaded via ``asyncio.to_thread``.
"""
from __future__ import annotations
import asyncio
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxGTT:
    """GTT order management for Upstox (async — see module doc)."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    async def place_single(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("upstox_gtt_place_single")
        return await asyncio.to_thread(
            self._client.post, "/v3/order/gtt/place", json=payload
        )

    async def place_multi(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("upstox_gtt_place_multi")
        return await asyncio.to_thread(
            self._client.post, "/v3/order/gtt/place", json=payload
        )

    async def modify(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("upstox_gtt_modify")
        return await asyncio.to_thread(
            self._client.put, "/v3/order/gtt/modify", json=payload
        )

    async def cancel(self, gtt_order_id: str) -> dict[str, Any]:
        logger.info("upstox_gtt_cancel", gtt_order_id=gtt_order_id)
        return await asyncio.to_thread(
            self._client.delete, f"/v3/order/gtt/cancel?order_id={gtt_order_id}"
        )

    async def get_orders(self) -> list[dict[str, Any]]:
        data = await asyncio.to_thread(self._client.get, "/v3/order/gtt/get-orders")
        result = data.get("data", data) if isinstance(data, dict) else data
        return result if isinstance(result, list) else []

    async def get_details(self, gtt_order_id: str) -> dict[str, Any]:
        data = await asyncio.to_thread(
            self._client.get, f"/v3/order/gtt/get-details?order_id={gtt_order_id}"
        )
        return data.get("data", data) if isinstance(data, dict) else {}


__all__ = ["UpstoxGTT"]
