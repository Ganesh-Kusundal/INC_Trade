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
        ref = self._resolver.resolve(symbol, exchange)
        sid = ref.security_id_int()
        segment = ref.exchange_segment
        payload = {segment: [sid]}
        assert_valid_dhan_payload(payload, context="market_data.ltp")
        data = self._client.post(ENDPOINTS["ltp"], json=payload)
        feed = data.get("data", {})

        entry: dict = {}
        if isinstance(feed, dict):
            segment_data = feed.get(segment)
            if isinstance(segment_data, dict):
                entry = segment_data.get(str(sid)) or {}
            if not entry:
                entry = (
                    feed.get(str(sid))
                    or feed.get(f"{segment}:{sid}")
                    or feed.get(symbol)
                    or {}
                )

        price = (
            entry.get("last_price") if "last_price" in entry else entry.get("lastPrice")
        )
        if price is None:
            if isinstance(entry, (int, float, str, Decimal)):
                price = entry
            else:
                price = 0
        return Decimal(str(price))

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        ref = self._resolver.resolve(symbol, exchange)
        sid = ref.security_id_int()
        segment = ref.exchange_segment
        payload = {segment: [sid]}
        assert_valid_dhan_payload(payload, context="market_data.quote")
        data = self._client.post(ENDPOINTS["quote"], json=payload)
        symbol_data = self._extract_symbol_feed(data, segment, sid, symbol)
        return map_quote(symbol, symbol_data)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        ref = self._resolver.resolve(symbol, exchange)
        sid = ref.security_id_int()
        segment = ref.exchange_segment
        payload = {segment: [sid]}
        assert_valid_dhan_payload(payload, context="market_data.depth")
        data = self._client.post(ENDPOINTS["quote"], json=payload)
        symbol_data = self._extract_symbol_feed(data, segment, sid, symbol)
        return map_depth(symbol, symbol_data)

    @staticmethod
    def _extract_symbol_feed(
        data: dict, segment: str, sid: int, symbol: str
    ) -> dict:
        feed = data.get("data", {})
        exchange_short = SEGMENT_TO_EXCHANGE.get(segment, segment)
        segment_data = feed.get(segment)
        if isinstance(segment_data, dict):
            nested = segment_data.get(str(sid))
            if isinstance(nested, dict):
                return nested
        return (
            feed.get(str(sid))
            or feed.get(symbol)
            or feed.get(f"{segment}:{sid}")
            or feed.get(f"{exchange_short}:{symbol}")
            or {}
        )

    def ltp_batch(
        self, symbols: list[str], exchange: str = "NSE"
    ) -> dict[str, Decimal]:
        """Fetch LTP for multiple symbols using native batch API."""
        if not symbols:
            return {}
        segment_map: dict[str, list[int]] = {}
        symbol_map: dict[int, str] = {}
        for sym in symbols:
            try:
                ref = self._resolver.resolve(sym, exchange)
                sid = ref.security_id_int()
                segment = ref.exchange_segment
                segment_map.setdefault(segment, []).append(sid)
                symbol_map[sid] = sym
            except Exception:
                continue
        if not segment_map:
            return {}
        assert_valid_dhan_payload(segment_map, context="market_data.ltp_batch")
        data = self._client.post(ENDPOINTS["ltp"], json=segment_map)
        result: dict[str, Decimal] = {}
        feed = data.get("data", {})
        if not isinstance(feed, dict):
            return result
        for segment, sids in feed.items():
            if not isinstance(sids, dict):
                continue
            for sid_str, info in sids.items():
                try:
                    sid = int(sid_str)
                except (TypeError, ValueError):
                    continue
                if sid not in symbol_map:
                    continue
                if isinstance(info, dict):
                    price = info.get("last_price", info.get("lastPrice", 0))
                else:
                    price = info
                result[symbol_map[sid]] = Decimal(str(price))
        return result

    def quote_batch(
        self, symbols: list[str], exchange: str = "NSE"
    ) -> dict[str, Quote]:
        """Fetch quotes for multiple symbols using native batch API."""
        if not symbols:
            return {}
        segment_map: dict[str, list[int]] = {}
        symbol_map: dict[int, str] = {}
        for sym in symbols:
            try:
                ref = self._resolver.resolve(sym, exchange)
                sid = ref.security_id_int()
                segment = ref.exchange_segment
                segment_map.setdefault(segment, []).append(sid)
                symbol_map[sid] = sym
            except Exception:
                continue
        if not segment_map:
            return {}
        assert_valid_dhan_payload(segment_map, context="market_data.quote_batch")
        data = self._client.post(ENDPOINTS["quote"], json=segment_map)
        result: dict[str, Quote] = {}
        feed = data.get("data", {})
        if not isinstance(feed, dict):
            return result
        for segment, sids in feed.items():
            if not isinstance(sids, dict):
                continue
            exchange_short = SEGMENT_TO_EXCHANGE.get(segment, segment)
            for sid_str, info in sids.items():
                try:
                    sid = int(sid_str)
                except (TypeError, ValueError):
                    continue
                if sid not in symbol_map:
                    continue
                sym = symbol_map[sid]
                if not isinstance(info, dict):
                    info = {}
                symbol_data = (
                    info
                    or feed.get(str(sid))
                    or feed.get(sym)
                    or feed.get(f"{segment}:{sid}")
                    or feed.get(f"{exchange_short}:{sym}")
                    or {}
                )
                result[sym] = map_quote(sym, symbol_data)
        return result

