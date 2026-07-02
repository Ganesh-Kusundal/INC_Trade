"""Dhan market data adapter — LTP, quote, depth."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.adapters.dhan.config import ENDPOINTS, SEGMENT_TO_EXCHANGE
from brokers.adapters.dhan.http import DhanHttpClient
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.invariants import assert_valid_dhan_payload
from brokers.adapters.dhan.mapper import map_depth, map_quote
from brokers.domain import MarketDepth, Quote

logger = logging.getLogger(__name__)


class DhanMarketData:
    def __init__(self, client: DhanHttpClient, resolver: DhanInstrumentResolver):
        self._client = client
        self._resolver = resolver

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        q = self.quote(symbol, exchange)
        return q.ltp

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        ref = self._resolver.resolve(symbol, exchange)
        sid = ref.security_id_int()
        segment = ref.exchange_segment
        payload = {segment: [sid]}
        assert_valid_dhan_payload(payload, context="market_data.quote")
        data = self._client.post(ENDPOINTS["quote"], json=payload)
        feed = data.get("data", {})
        exchange_short = SEGMENT_TO_EXCHANGE.get(segment, segment)
        symbol_data = (
            feed.get(str(sid))
            or feed.get(symbol)
            or feed.get(f"{segment}:{sid}")
            or feed.get(f"{exchange_short}:{symbol}")
            or {}
        )
        return map_quote(symbol, symbol_data)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        ref = self._resolver.resolve(symbol, exchange)
        sid = ref.security_id_int()
        segment = ref.exchange_segment
        payload = {segment: [sid]}
        assert_valid_dhan_payload(payload, context="market_data.depth")
        data = self._client.post(ENDPOINTS["quote"], json=payload)
        feed = data.get("data", {})
        exchange_short = SEGMENT_TO_EXCHANGE.get(segment, segment)
        symbol_data = (
            feed.get(str(sid))
            or feed.get(symbol)
            or feed.get(f"{segment}:{sid}")
            or feed.get(f"{exchange_short}:{symbol}")
            or {}
        )
        return map_depth(symbol, symbol_data)
