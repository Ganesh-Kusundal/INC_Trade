"""Upstox margin adapter — implements ``MarginProvider`` port."""

from __future__ import annotations

from typing import Any

from brokers.common.gateway_interfaces import MarginProvider
from brokers.upstox.market_data.margin import UpstoxMarginClient


class UpstoxMarginAdapter(MarginProvider):
    def __init__(self, client: UpstoxMarginClient) -> None:
        self._client = client

    def calculate_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.calculate_margin(payload)
