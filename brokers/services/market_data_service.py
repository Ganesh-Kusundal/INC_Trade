"""Market data service — application-level market data with caching.

Adds TTL-based caching on top of the raw MarketDataPort to avoid
hitting the broker API for every LTP/quote call.
"""

from __future__ import annotations

import logging
import threading
import time
from decimal import Decimal
from typing import cast

from brokers.domain import MarketDepth, Quote
from brokers.ports.market_data import MarketDataPort

logger = logging.getLogger(__name__)

_CacheEntry = tuple[float, Quote | MarketDepth]


class MarketDataService:
    def __init__(self, provider: MarketDataPort, cache_ttl_seconds: float = 1.0):
        self._provider = provider
        self._ttl = cache_ttl_seconds
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        q = self.quote(symbol, exchange)
        return q.ltp

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        key = f"quote:{exchange}:{symbol}"
        cached = self._get_cached(key)
        if cached is not None:
            return cast(Quote, cached)
        result = self._provider.quote(symbol, exchange)
        self._set_cached(key, result)
        return result

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        key = f"depth:{exchange}:{symbol}"
        cached = self._get_cached(key)
        if cached is not None:
            return cast(MarketDepth, cached)
        result = self._provider.depth(symbol, exchange)
        self._set_cached(key, result)
        return result

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        quotes = self.quote_batch(symbols, exchange)
        return {sym: q.ltp for sym, q in quotes.items()}

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        result: dict[str, Quote] = {}
        missing_symbols: list[str] = []

        for sym in symbols:
            key = f"quote:{exchange}:{sym}"
            cached = self._get_cached(key)
            if cached is not None:
                result[sym] = cast(Quote, cached)
            else:
                missing_symbols.append(sym)

        if missing_symbols:
            missing_quotes = self._provider.quote_batch(missing_symbols, exchange)
            for sym, quote_data in missing_quotes.items():
                self._set_cached(f"quote:{exchange}:{sym}", quote_data)
                result[sym] = quote_data

        return result

    def invalidate(self, symbol: str = "", exchange: str = "") -> None:
        with self._lock:
            if not symbol:
                self._cache.clear()
            else:
                for prefix in ("quote", "depth"):
                    self._cache.pop(f"{prefix}:{exchange}:{symbol}", None)

    def _get_cached(self, key: str) -> Quote | MarketDepth | None:
        with self._lock:
            entry = self._cache.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts > self._ttl:
            with self._lock:
                self._cache.pop(key, None)
            return None
        return value

    def _set_cached(self, key: str, value: Quote | MarketDepth) -> None:
        with self._lock:
            self._cache[key] = (time.monotonic(), value)
