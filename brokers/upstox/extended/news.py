"""Upstox news — market news retrieval.

API: GET /v2/news — get news with filters
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxNews:
    """Market news retrieval for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_news(
        self,
        category: str = "",
        symbol: str = "",
        from_date: str = "",
        to_date: str = "",
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if category:
            params["category"] = category
        if symbol:
            params["symbol"] = symbol
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        query = "&".join(f"{k}={v}" for k, v in params.items())
        endpoint = f"/v2/news?{query}" if query else "/v2/news"
        data = self._client.get(endpoint)
        result = data.get("data", data) if isinstance(data, dict) else data
        return result if isinstance(result, list) else []

    def get_news_for_instruments(self, instrument_keys: list[str]) -> list[dict[str, Any]]:
        keys = ",".join(instrument_keys)
        data = self._client.get(f"/v2/news?instrument_keys={keys}")
        result = data.get("data", data) if isinstance(data, dict) else data
        return result if isinstance(result, list) else []


__all__ = ["UpstoxNews"]
