"""Upstox portfolio adapter — positions, holdings, funds, trades."""

from __future__ import annotations

import logging

from brokers_core.config.endpoints import _UpstoxUrls
from brokers_core.domain import Balance, Holding, Position, Trade
from brokers_core.ports.http_client_port import HttpClientPort

from brokers_core.adapters.upstox.mapper import (
    map_balance,
    map_holding,
    map_position,
    map_trade,
    unwrap_data,
)

logger = logging.getLogger(__name__)


class UpstoxPortfolio:
    def __init__(self, client: HttpClientPort, urls: _UpstoxUrls):
        self._client = client
        self._urls = urls

    def positions(self) -> list[Position]:
        data = self._client.get(self._urls.positions_url())
        items = unwrap_data(data)
        if isinstance(items, list):
            return [map_position(p) for p in items]
        return []

    def holdings(self) -> list[Holding]:
        data = self._client.get(self._urls.holdings_url())
        items = unwrap_data(data)
        if isinstance(items, list):
            return [map_holding(h) for h in items]
        return []

    def funds(self) -> Balance:
        data = self._client.get(self._urls.funds_url())
        return map_balance(data)

    def trades(self) -> list[Trade]:
        data = self._client.get(self._urls.trades_for_day_url())
        items = unwrap_data(data)
        if isinstance(items, list):
            return [map_trade(t) for t in items]
        return []
