"""Dhan portfolio adapter — positions, holdings, funds, trades."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.adapters.dhan.config import ENDPOINTS
from brokers.adapters.dhan.http import DhanHttpClient
from brokers.adapters.dhan.mapper import (
    map_balance,
    map_holding,
    map_position,
    map_trade,
)
from brokers.domain import Balance, Holding, Position, Trade

logger = logging.getLogger(__name__)


class DhanPortfolio:
    def __init__(self, client: DhanHttpClient):
        self._client = client

    def positions(self) -> list[Position]:
        data = self._client.get(ENDPOINTS["positions"])
        items = data if isinstance(data, list) else data.get("data", [])
        if isinstance(items, list):
            return [map_position(p) for p in items]
        return []

    def holdings(self) -> list[Holding]:
        data = self._client.get(ENDPOINTS["holdings"])
        items = data if isinstance(data, list) else data.get("data", [])
        if isinstance(items, list):
            return [map_holding(h) for h in items]
        return []

    def funds(self) -> Balance:
        data = self._client.get(ENDPOINTS["fund_limit"])
        if isinstance(data, dict):
            if "availabelBalance" in data or "sodLimit" in data:
                return map_balance(data)
            items = data.get("data", [])
            if isinstance(items, list) and items:
                return map_balance(items[0])
        return Balance(available_cash=Decimal("0"))

    def trades(self) -> list[Trade]:
        data = self._client.get(ENDPOINTS["tradebook"])
        items = data.get("data", [])
        if isinstance(items, list):
            return [map_trade(t) for t in items]
        return []
