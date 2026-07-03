"""Upstox market data adapter — LTP, quote, depth."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.adapters.upstox.http import UpstoxHttpClient
from brokers.adapters.upstox.instruments import resolve_upstox_instrument_key
from brokers.adapters.upstox.instruments import UpstoxInstruments
from brokers.adapters.upstox.mapper import map_depth, map_quote, unwrap_data
from brokers.config.endpoints import _UpstoxUrls
from brokers.domain import MarketDepth, Quote

logger = logging.getLogger(__name__)


class UpstoxMarketData:
    def __init__(
        self,
        client: UpstoxHttpClient,
        urls: _UpstoxUrls,
        instruments: UpstoxInstruments | None = None,
    ):
        self._client = client
        self._urls = urls
        self._instruments = instruments

    def _key(self, symbol: str, exchange: str) -> str:
        return resolve_upstox_instrument_key(symbol, exchange, self._instruments)

    def _find_symbol_data(self, feed: dict, key: str, symbol: str) -> dict:
        if not feed:
            return {}
        if key in feed:
            return feed[key]
        colon_key = key.replace("|", ":")
        if colon_key in feed:
            return feed[colon_key]
        for k, val in feed.items():
            if val.get("instrument_token") == key:
                return val
            parts = k.split(":")
            if len(parts) > 1 and parts[1].upper() == symbol.upper():
                return val
        if len(feed) == 1:
            return next(iter(feed.values()))
        return {}

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        key = self._key(symbol, exchange)
        data = self._client.get(
            self._urls.market_quote_ltp_url(), params={"instrument_key": key}
        )
        feed = unwrap_data(data, default={})
        symbol_data = self._find_symbol_data(feed, key, symbol)
        return Decimal(str(symbol_data.get("last_price", 0)))

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        key = self._key(symbol, exchange)
        data = self._client.get(
            self._urls.market_quote_full_url(), params={"instrument_key": key}
        )
        feed = unwrap_data(data, default={})
        symbol_data = self._find_symbol_data(feed, key, symbol)
        return map_quote(symbol, symbol_data)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        key = self._key(symbol, exchange)
        data = self._client.get(
            self._urls.market_quote_full_url(), params={"instrument_key": key}
        )
        feed = unwrap_data(data, default={})
        symbol_data = self._find_symbol_data(feed, key, symbol)
        return map_depth(symbol, symbol_data)

    def ltp_batch(
        self, symbols: list[str], exchange: str = "NSE"
    ) -> dict[str, Decimal]:
        keys = ",".join(self._key(s, exchange) for s in symbols)
        data = self._client.get(
            self._urls.market_quote_ltp_url(), params={"instrument_key": keys}
        )
        feed = unwrap_data(data, default={})
        result: dict[str, Decimal] = {}
        for sym in symbols:
            key = self._key(sym, exchange)
            symbol_data = self._find_symbol_data(feed, key, sym)
            result[sym] = Decimal(str(symbol_data.get("last_price", 0)))
        return result

    def quote_batch(
        self, symbols: list[str], exchange: str = "NSE"
    ) -> dict[str, Quote]:
        keys = ",".join(self._key(s, exchange) for s in symbols)
        data = self._client.get(
            self._urls.market_quote_full_url(), params={"instrument_key": keys}
        )
        feed = unwrap_data(data, default={})
        result: dict[str, Quote] = {}
        for sym in symbols:
            key = self._key(sym, exchange)
            symbol_data = self._find_symbol_data(feed, key, sym)
            result[sym] = map_quote(sym, symbol_data)
        return result
