"""Integration tests: Decorator pattern with PaperAdapter + CQS.

Verifies that the decorator chain (CachedDecorator, DepthDecorator,
with_depth, with_cache, with_logging) works correctly with the
provider-injection pattern and CQS MarketDataQuery.

Key scenarios:
1. Instrument.with_providers() + CachedDecorator → cached quote/ltp
2. Instrument.with_providers() + DepthDecorator → depth delegation
3. Decorator chain: with_logging(with_cache(with_depth(inst)))
4. MarketDataQuery from session unaffected by decorators (CQS purity)
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from brokers.adapters.paper.adapter import PaperAdapter


@pytest.fixture
def adapter() -> PaperAdapter:
    a = PaperAdapter()
    a.connect()
    a.set_quote("RELIANCE", Decimal("2850.50"))
    return a


class TestCachedDecoratorIntegration:
    """CachedDecorator with provider injection."""

    def test_decorator_caches_quote(self, adapter: PaperAdapter) -> None:
        """CachedDecorator returns cached quote within TTL."""
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, query=None)

        from inc_trade.market.cache_decorator import CachedDecorator

        cached = CachedDecorator(inst, ttl_seconds=10.0)

        # First call fetches fresh
        q1 = cached.quote()
        assert q1.ltp == Decimal("2850.50")

        # Update underlying quote
        adapter.set_quote("RELIANCE", Decimal("2900.00"))

        # Second call should still return cached value
        q2 = cached.quote()
        assert q2.ltp == Decimal("2850.50")  # cached, not 2900

    def test_decorator_cache_expires(self, adapter: PaperAdapter) -> None:
        """CachedDecorator fetches fresh after TTL expires."""
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, query=None)

        from inc_trade.market.cache_decorator import CachedDecorator

        cached = CachedDecorator(inst, ttl_seconds=0.01)  # 10ms TTL

        # First call
        q1 = cached.quote()
        assert q1.ltp == Decimal("2850.50")

        # Update underlying quote
        adapter.set_quote("RELIANCE", Decimal("2900.00"))

        # Wait for TTL to expire
        time.sleep(0.02)

        # Should fetch fresh
        q2 = cached.quote()
        assert q2.ltp == Decimal("2900.00")  # fresh, not 2850.50

    def test_decorator_caches_ltp(self, adapter: PaperAdapter) -> None:
        """CachedDecorator caches LTP separately."""
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, query=None)

        from inc_trade.market.cache_decorator import CachedDecorator

        cached = CachedDecorator(inst, ttl_seconds=10.0)

        ltp1 = cached.ltp()
        assert ltp1 == Decimal("2850.50")

        adapter.set_quote("RELIANCE", Decimal("2900.00"))

        ltp2 = cached.ltp()
        assert ltp2 == Decimal("2850.50")  # cached

    def test_decorator_invalidate(self, adapter: PaperAdapter) -> None:
        """CachedDecorator.invalidate() clears the cache."""
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, query=None)

        from inc_trade.market.cache_decorator import CachedDecorator

        cached = CachedDecorator(inst, ttl_seconds=10.0)

        cached.quote()
        adapter.set_quote("RELIANCE", Decimal("2900.00"))
        cached.invalidate()

        q = cached.quote()
        assert q.ltp == Decimal("2900.00")  # fresh after invalidation


class TestDepthDecoratorIntegration:
    """DepthDecorator with provider injection."""

    def test_with_depth_decorates_instrument(self, adapter: PaperAdapter) -> None:
        """with_depth() wraps instrument with DepthDecorator."""
        from inc_trade.market.decorators import with_depth
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, depth_provider=adapter)

        decorated = with_depth(inst, levels=200, depth_provider=adapter)

        # Decorated instrument can still call quote()
        q = decorated.quote()
        assert q.ltp is not None

    def test_with_depth_returns_original_for_5_or_less(self, adapter: PaperAdapter) -> None:
        """with_depth() returns original instrument for levels <= 5."""
        from inc_trade.market.decorators import with_depth
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        result = with_depth(inst, levels=5)
        assert result is inst  # same object, no decorator needed

    def test_decorator_chain_preserves_identity(self, adapter: PaperAdapter) -> None:
        """Decorator chain preserves instrument identity."""
        from inc_trade.market.decorators import with_cache, with_depth
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, depth_provider=adapter)

        chain = with_cache(with_depth(inst, levels=200, depth_provider=adapter))

        q = chain.quote()
        assert q is not None
        assert chain.composite_key == "NSE:RELIANCE"

    def test_with_cache_decorates_instrument(self, adapter: PaperAdapter) -> None:
        """with_cache() wraps instrument with CachedDecorator."""
        from inc_trade.market.decorators import with_cache
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter)

        cached = with_cache(inst, ttl_seconds=5.0)

        q = cached.quote()
        assert q.ltp is not None


class TestCqsPurity:
    """Verifies that MarketDataQuery is NOT affected by instrument decorators."""

    def test_query_bypasses_instrument_decorator(self, adapter: PaperAdapter) -> None:
        """MarketDataQuery goes directly to adapter, bypassing decorator."""
        from inc_trade.market.decorators import with_cache
        from inc_trade.market.instrument import Instrument
        from inc_trade.market.query import MarketDataQuery

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, query=None)

        # Wrap in cache decorator
        cached = with_cache(inst, ttl_seconds=10.0)

        # Create query directly (simulates session.query())
        query = MarketDataQuery(instrument=cached, provider=adapter)

        # First call
        ltp1 = query.ltp()
        assert ltp1 == Decimal("2850.50")

        # Update underlying
        adapter.set_quote("RELIANCE", Decimal("2900.00"))

        # Query should get fresh value (bypasses decorator cache)
        ltp2 = query.ltp()
        assert ltp2 == Decimal("2900.00")  # fresh, not cached

    def test_instrument_convenience_uses_decorator(self, adapter: PaperAdapter) -> None:
        """Instrument.quote() convenience goes through the decorator."""
        from inc_trade.market.decorators import with_cache
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter)

        cached = with_cache(inst, ttl_seconds=10.0)

        # First call populates cache
        ltp1 = cached.ltp()
        assert ltp1 == Decimal("2850.50")

        adapter.set_quote("RELIANCE", Decimal("2900.00"))

        # Instrument convenience should return cached (going through decorator)
        ltp2 = cached.ltp()
        assert ltp2 == Decimal("2850.50")  # cached value
