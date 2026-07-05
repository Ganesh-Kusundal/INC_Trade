"""Unit tests for MarketRouter metrics instrumentation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from inc_trade.domain.entities import MarketDepth, Quote
from inc_trade.infrastructure.cache.memory_cache import MemoryCache
from inc_trade.market.market_router import MarketRouter


class _StubProvider:
    def __init__(self) -> None:
        self.call_count = 0
        self.raise_on_next = False

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        self.call_count += 1
        if self.raise_on_next:
            self.raise_on_next = False
            raise RuntimeError("provider down")
        return Quote(symbol=symbol, exchange=exchange, ltp=Decimal("100"))

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return self.quote(symbol, exchange).ltp

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        return MarketDepth(symbol=symbol, exchange=exchange, bids=(), asks=())

    def ltp_batch(self, symbols, exchange: str = "NSE") -> dict[str, Decimal]:
        return {s: self.ltp(s, exchange) for s in symbols}

    def quote_batch(self, symbols, exchange: str = "NSE") -> dict[str, Quote]:
        return {s: self.quote(s, exchange) for s in symbols}


class TestRouterMetrics:
    def test_initial_metrics_zero(self) -> None:
        router = MarketRouter(cache=MemoryCache(), primary=_StubProvider())
        m = router.metrics()
        assert m["quote_cache_hits"] == 0
        assert m["quote_cache_misses"] == 0
        # First call is a miss
        router.quote("A", "NSE")
        m = router.metrics()
        assert m["quote_cache_misses"] == 1

    def test_cache_hit_increments(self) -> None:
        provider = _StubProvider()
        router = MarketRouter(cache=MemoryCache(), primary=provider)
        router.quote("A", "NSE")
        # Second call should be a cache hit
        router.quote("A", "NSE")
        m = router.metrics()
        assert m["quote_cache_hits"] == 1
        assert m["quote_cache_misses"] == 1

    def test_provider_error_increments(self) -> None:
        provider = _StubProvider()
        provider.raise_on_next = True
        router = MarketRouter(cache=MemoryCache(), primary=provider)
        with pytest.raises(RuntimeError):
            router.quote("A", "NSE")
        m = router.metrics()
        assert m["provider_errors"] == 1

    def test_ltp_metrics(self) -> None:
        provider = _StubProvider()
        router = MarketRouter(cache=MemoryCache(), primary=provider)
        router.ltp("A", "NSE")
        router.ltp("A", "NSE")  # cache hit
        m = router.metrics()
        assert m["ltp_cache_hits"] >= 1
        assert m["ltp_cache_misses"] >= 1

    def test_metrics_snapshot_is_copy(self) -> None:
        router = MarketRouter(cache=MemoryCache(), primary=_StubProvider())
        m1 = router.metrics()
        m1["quote_cache_hits"] = 999
        m2 = router.metrics()
        assert m2["quote_cache_hits"] != 999
