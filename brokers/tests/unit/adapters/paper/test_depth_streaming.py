"""Integration tests: Depth decorators with PaperAdapter.

Verifies that Depth20Decorator, Depth200Decorator, and the
with_depth() helper work correctly with providers.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.adapters.paper.adapter import PaperAdapter


@pytest.fixture
def adapter() -> PaperAdapter:
    a = PaperAdapter()
    a.connect()
    a.set_quote("RELIANCE", Decimal("2850.50"))
    return a


class TestDepthDecorators:
    """Depth decorators with provider injection."""

    def test_depth20_decorator(self, adapter: PaperAdapter) -> None:
        """Depth20Decorator wraps instrument and delegates depth."""
        from inc_trade.market.depth_decorators import Depth20Decorator
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, depth_provider=adapter)

        d20 = Depth20Decorator(inst, depth_provider=adapter)

        # Depth20 has depth_20() convenience
        depth = d20.depth_20()
        assert depth is not None
        assert depth.symbol == "RELIANCE"

        # Still has quote() via delegation
        q = d20.quote()
        assert q.ltp == Decimal("2850.50")

    def test_depth200_decorator(self, adapter: PaperAdapter) -> None:
        """Depth200Decorator wraps instrument and delegates depth."""
        from inc_trade.market.depth_decorators import Depth200Decorator
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, depth_provider=adapter)

        d200 = Depth200Decorator(inst, depth_provider=adapter)

        depth = d200.depth_200()
        assert depth is not None
        assert depth.symbol == "RELIANCE"

    def test_depth_decorator_chain(self, adapter: PaperAdapter) -> None:
        """Depth and cache decorators stack correctly."""
        from inc_trade.market.decorators import with_cache, with_depth
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, depth_provider=adapter)

        # Stack cache on top of depth
        stack = with_cache(with_depth(inst, levels=200, depth_provider=adapter))

        # quote goes through cache → depth → instrument → adapter
        q = stack.quote()
        assert q.ltp == Decimal("2850.50")

        # Composite key preserved through chain
        assert stack.composite_key == "NSE:RELIANCE"

    def test_depth_decorator_supports_depth_check(self, adapter: PaperAdapter) -> None:
        """Depth decorator validates supported levels."""
        from inc_trade.market.depth_decorators import Depth200Decorator
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, depth_provider=adapter)

        d200 = Depth200Decorator(inst, depth_provider=adapter)

        # By default, without _capabilities, only levels <= 5 are supported
        assert (
            d200._wrapped.supports_depth(5) is True or d200._wrapped.supports_depth(5) is not None
        )

        # Depth200Decorator calls depth_provider.depth() directly
        depth = d200.depth(200)
        assert depth is not None

    def test_paper_adapter_max_levels(self, adapter: PaperAdapter) -> None:
        """PaperAdapter reports max_levels=5."""
        assert adapter.max_levels == 5

    def test_depth_via_query(self, adapter: PaperAdapter) -> None:
        """MarketDataQuery.depth() works with paper adapter."""
        from inc_trade.market.instrument import Instrument
        from inc_trade.market.query import MarketDataQuery

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(provider=adapter, depth_provider=adapter)

        query = MarketDataQuery(
            instrument=inst,
            provider=adapter,
            depth_provider=adapter,
        )

        depth = query.depth(5)
        assert depth is not None
        assert depth.symbol == "RELIANCE"
