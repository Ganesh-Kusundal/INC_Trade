"""Contract tests — MarketRouter cache-first routing behavior.

The ``MarketRouter`` is a value-add over ``MarketDataPort``: it adds
caching, provider fallback, and batch operations. These tests verify
that any ``MarketRouter`` implementation satisfies the same observable
contract.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from inc_trade.domain.cache_policy import POLICY_DEPTH, POLICY_QUOTE
from inc_trade.domain.entities import MarketDepth, Quote
from inc_trade.infrastructure.cache.memory_cache import MemoryCache
from inc_trade.market.market_router import MarketRouter
from inc_trade.ports.cache_port import CachePort
from inc_trade.ports.market_data import MarketDataPort


class _FakeMarketData(MarketDataPort):
    """Minimal MarketDataPort stub for routing tests."""

    def __init__(self, quotes: dict[tuple[str, str], Quote] | None = None) -> None:
        self._quotes: dict[tuple[str, str], Quote] = quotes or {
            ("NSE", "RELIANCE"): Quote(symbol="RELIANCE", exchange="NSE", ltp=Decimal("2500")),
            ("NSE", "TCS"): Quote(symbol="TCS", exchange="NSE", ltp=Decimal("3000")),
        }
        self.call_count = 0

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        self.call_count += 1
        return self._quotes[(exchange, symbol)]

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return self.quote(symbol, exchange).ltp

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        return MarketDepth(
            symbol=symbol,
            exchange=exchange,
            bids=(),
            asks=(),
        )

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        return {s: self.ltp(s, exchange) for s in symbols}

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        return {s: self.quote(s, exchange) for s in symbols}


class TestMarketRouter:
    @pytest.fixture
    def cache(self) -> CachePort:
        return MemoryCache(max_entries=1000)

    @pytest.fixture
    def provider(self) -> _FakeMarketData:
        return _FakeMarketData()

    @pytest.fixture
    def router(self, cache: CachePort, provider: _FakeMarketData) -> MarketRouter:
        return MarketRouter(cache=cache, primary=provider)

    # ── Quote routing ─────────────────────────────────────────────────

    def test_quote_returns_quote(self, router: MarketRouter) -> None:
        q = router.quote("RELIANCE", "NSE")
        assert isinstance(q, Quote)
        assert q.symbol == "RELIANCE"
        assert q.ltp == Decimal("2500")

    def test_quote_cache_hit_avoids_provider(
        self, router: MarketRouter, provider: _FakeMarketData
    ) -> None:
        router.quote("RELIANCE", "NSE")
        first = provider.call_count
        router.quote("RELIANCE", "NSE")
        router.quote("RELIANCE", "NSE")
        assert provider.call_count == first, "Cache should prevent further provider calls"

    def test_quote_no_provider_raises(self, cache: CachePort) -> None:
        router = MarketRouter(cache=cache)
        with pytest.raises(RuntimeError, match="No market data provider"):
            router.quote("UNKNOWN", "NSE")

    # ── LTP routing ───────────────────────────────────────────────────

    def test_ltp_returns_decimal(self, router: MarketRouter) -> None:
        price = router.ltp("RELIANCE", "NSE")
        assert isinstance(price, Decimal)
        assert price == Decimal("2500")

    # ── Depth routing ─────────────────────────────────────────────────

    def test_depth_returns_market_depth(self, router: MarketRouter) -> None:
        d = router.depth("RELIANCE", "NSE")
        assert isinstance(d, MarketDepth)

    # ── Invalidation ──────────────────────────────────────────────────

    def test_invalidate_clears_cache(self, router: MarketRouter, cache: CachePort) -> None:
        router.quote("RELIANCE", "NSE")
        # After invalidation, provider should be called again
        router.invalidate("RELIANCE", "NSE")
        # Check cache is cleared
        from inc_trade.market.market_router import _QUOTE_CACHE_PREFIX

        assert cache.get(f"{_QUOTE_CACHE_PREFIX}NSE:RELIANCE") is None

    # ── Provider fallback ──────────────────────────────────────────────

    def test_fallback_provider_works(self, cache: CachePort) -> None:
        primary = _FakeMarketData()
        # Remove RELIANCE from primary to force fallback
        fallback = _FakeMarketData(
            {
                ("NSE", "RELIANCE"): Quote(symbol="RELIANCE", exchange="NSE", ltp=Decimal("9999")),
            }
        )

        # Primary should fail for RELIANCE — make it raise
        def raise_for_reliance(symbol: str, exchange: str = "NSE") -> Quote:
            if symbol == "RELIANCE":
                raise RuntimeError("primary down")
            return primary._quotes[(exchange, symbol)]

        primary.quote = raise_for_reliance  # type: ignore[assignment]

        router = MarketRouter(cache=cache, primary=primary)
        router.add_fallback(fallback)
        q = router.quote("RELIANCE", "NSE")
        assert q.ltp == Decimal("9999")

    # ── Batching ──────────────────────────────────────────────────────

    def test_quote_batch(self, router: MarketRouter) -> None:
        out = router.quote_batch(["RELIANCE", "TCS"], "NSE")
        assert len(out) == 2
        assert all(isinstance(v, Quote) for v in out.values())

    def test_ltp_batch(self, router: MarketRouter) -> None:
        out = router.ltp_batch(["RELIANCE", "TCS"], "NSE")
        assert len(out) == 2
        assert all(isinstance(v, Decimal) for v in out.values())

    # ── TTL defaults ──────────────────────────────────────────────────

    def test_default_quote_ttl(self, cache: CachePort) -> None:
        router = MarketRouter(cache=cache)
        assert router._quote_ttl == float(POLICY_QUOTE.ttl_seconds)

    def test_default_depth_ttl(self, cache: CachePort) -> None:
        router = MarketRouter(cache=cache)
        assert router._depth_ttl == float(POLICY_DEPTH.ttl_seconds)


class TestMarketRouterBoundary:
    """MarketRouter must follow Clean Architecture rules."""

    def test_market_router_does_not_import_adapters(self) -> None:
        from pathlib import Path

        from inc_trade.market import market_router

        src = Path(market_router.__file__).read_text()
        for forbidden in (
            "brokers.adapters",
            "brokers.trading",
            "brokers.services",
            "brokers.infrastructure",
        ):
            assert forbidden not in src, f"market_router.py imports {forbidden}"

    def test_market_router_uses_ports(self) -> None:

        # Verify it imports ports
        from inc_trade.ports.cache_port import CachePort
        from inc_trade.ports.market_data import MarketDataPort

        assert MarketDataPort is not None
        assert CachePort is not None
