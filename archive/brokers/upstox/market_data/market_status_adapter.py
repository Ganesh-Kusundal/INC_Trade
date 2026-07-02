"""Upstox market status adapter — implements ``MarketStatusProvider`` port."""

from __future__ import annotations

from typing import Any

from brokers.common.gateway_interfaces import MarketStatusProvider
from brokers.upstox.market_data.market_status import UpstoxMarketStatusClient


class UpstoxMarketStatusAdapter(MarketStatusProvider):
    def __init__(self, client: UpstoxMarketStatusClient) -> None:
        self._client = client

    def get_market_status(self) -> dict[str, Any]:
        return self._client.get_market_status_all()
