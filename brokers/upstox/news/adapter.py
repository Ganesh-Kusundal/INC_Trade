"""Upstox news adapter — implements ``NewsProvider`` port."""

from __future__ import annotations

from typing import Any

from brokers.common.gateway_interfaces import NewsProvider
from brokers.upstox.news.client import UpstoxNewsClient


class UpstoxNewsAdapter(NewsProvider):
    def __init__(self, client: UpstoxNewsClient) -> None:
        self._client = client

    def get_news(self, **filters: Any) -> list[Any]:
        return self._client.get_news(
            category=filters.get("category", "holdings"),
            symbol=filters.get("symbol"),
            from_date=filters.get("from_date"),
            to_date=filters.get("to_date"),
            instrument_keys=filters.get("instrument_keys"),
        )
