"""Upstox market data adapter — LTP, quote, depth."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.adapters.upstox.config import ENDPOINTS, EXCHANGE_TO_SEGMENT
from brokers.adapters.upstox.http import UpstoxHttpClient
from brokers.adapters.upstox.mapper import map_depth, map_quote
from brokers.domain import MarketDepth, Quote

logger = logging.getLogger(__name__)


def _instrument_key(symbol: str, exchange: str) -> str:
    segment = EXCHANGE_TO_SEGMENT.get(exchange.upper(), exchange)
    return f"{segment}|{symbol}"


class UpstoxMarketData:
    def __init__(self, client: UpstoxHttpClient):
        self._client = client

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        key = _instrument_key(symbol, exchange)
        data = self._client.get(ENDPOINTS["ltp"], params={"instrument_key": key})
        feed = data.get("data", {})
        symbol_data = feed.get(key, {})
        return Decimal(str(symbol_data.get("last_price", 0)))

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        key = _instrument_key(symbol, exchange)
        data = self._client.get(ENDPOINTS["quote"], params={"instrument_key": key})
        feed = data.get("data", {})
        symbol_data = feed.get(key, {})
        return map_quote(symbol, symbol_data)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        key = _instrument_key(symbol, exchange)
        data = self._client.get(ENDPOINTS["depth"], params={"instrument_key": key})
        feed = data.get("data", {})
        symbol_data = feed.get(key, {})
        return map_depth(symbol, symbol_data)
