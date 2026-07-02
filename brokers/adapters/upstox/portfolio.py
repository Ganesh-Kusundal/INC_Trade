"""Upstox portfolio adapter — positions, holdings, funds, trades."""

from __future__ import annotations

import logging

from brokers.adapters.upstox.config import ENDPOINTS
from brokers.adapters.upstox.http import UpstoxHttpClient
from brokers.adapters.upstox.mapper import (
    map_balance,
    map_holding,
    map_position,
    map_trade,
)
from brokers.domain import Balance, Holding, Position, Trade

logger = logging.getLogger(__name__)


class UpstoxPortfolio:
    def __init__(self, client: UpstoxHttpClient):
        self._client = client

    def positions(self) -> list[Position]:
        data = self._client.get(ENDPOINTS["positions"])
        items = data.get("data", [])
        if isinstance(items, list):
            return [map_position(p) for p in items]
        return []

    def holdings(self) -> list[Holding]:
        data = self._client.get(ENDPOINTS["holdings"])
        items = data.get("data", [])
        if isinstance(items, list):
            return [map_holding(h) for h in items]
        return []

    def funds(self) -> Balance:
        data = self._client.get(ENDPOINTS["funds"])
        return map_balance(data)

    def trades(self) -> list[Trade]:
        data = self._client.get(ENDPOINTS["trades"])
        items = data.get("data", [])
        if isinstance(items, list):
            return [map_trade(t) for t in items]
        return []
