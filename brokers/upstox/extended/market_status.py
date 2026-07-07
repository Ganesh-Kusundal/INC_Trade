"""Upstox market status — check exchange/segment trading status.

API: GET /v2/market-status/{exchange} — get market status
     GET /v2/market-status — get all market statuses
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxMarketStatus:
    """Market status retrieval for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_status(self, exchange: str = "NSE") -> dict[str, Any]:
        data = self._client.get(f"/v2/market-status/{exchange}")
        return data.get("data", data) if isinstance(data, dict) else {}  # type: ignore[no-any-return]

    def get_all_statuses(self) -> list[dict[str, Any]]:
        data = self._client.get("/v2/market-status")
        result = data.get("data", data) if isinstance(data, dict) else data
        return result if isinstance(result, list) else []


__all__ = ["UpstoxMarketStatus"]
