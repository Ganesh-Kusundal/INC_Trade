"""Upstox mutual funds — holdings and order placement.

API: GET /v2/mf/holdings — get MF holdings
     POST /v2/mf/order/place — place MF order
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxMutualFunds:
    """Mutual fund management for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_holdings(self) -> list[dict[str, Any]]:
        data = self._client.get("/v2/mf/holdings")
        result = data.get("data", data) if isinstance(data, dict) else data
        return result if isinstance(result, list) else []

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("upstox_mf_order_place")
        return self._client.post("/v2/mf/order/place", json=payload)


__all__ = ["UpstoxMutualFunds"]
