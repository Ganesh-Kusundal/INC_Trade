"""Contract tests — MarketDataPort protocol compliance.

Every broker adapter's market data implementation must satisfy
the MarketDataPort protocol contract.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from inc_trade.ports.market_data import MarketDataPort


class MarketDataContractTests:
    """Mixin-style contract tests for MarketDataPort.

    Subclass with a ``@pytest.fixture`` named ``market_data``
    that returns a ``MarketDataPort`` instance.
    """

    def test_ltp_returns_decimal(self, market_data: MarketDataPort) -> None:
        price = market_data.ltp("RELIANCE")
        assert isinstance(price, Decimal)

    def test_ltp_is_positive(self, market_data: MarketDataPort) -> None:
        price = market_data.ltp("RELIANCE")
        assert price > 0

    def test_quote_returns_quote(self, market_data: MarketDataPort) -> None:
        from inc_trade.domain import Quote

        q = market_data.quote("RELIANCE")
        assert isinstance(q, Quote)
        assert q.symbol == "RELIANCE"
        assert q.ltp > 0

    def test_depth_returns_depth(self, market_data: MarketDataPort) -> None:
        from inc_trade.domain import MarketDepth

        d = market_data.depth("RELIANCE")
        assert isinstance(d, MarketDepth)
        assert d.symbol == "RELIANCE"

    def test_ltp_batch_returns_dict(self, market_data: MarketDataPort) -> None:
        prices = market_data.ltp_batch(["RELIANCE", "TCS"])
        assert isinstance(prices, dict)
        assert all(isinstance(v, Decimal) for v in prices.values())

    def test_quote_batch_returns_dict(self, market_data: MarketDataPort) -> None:
        from inc_trade.domain import Quote

        quotes = market_data.quote_batch(["RELIANCE", "TCS"])
        assert isinstance(quotes, dict)
        assert all(isinstance(q, Quote) for q in quotes.values())


@pytest.mark.contract
class TestMarketDataContractConformance:
    """Verify that any MarketDataPort implementation satisfies the contract.

    Run with::

        pytest tests/contract/ -v
    """

    @pytest.fixture
    def market_data(self) -> MarketDataPort:
        """Override in broker-specific subclasses with real instance."""
        from inc_trade.ports.market_data import MarketDataPort

        pytest.skip("No concrete MarketDataPort fixture provided")

    def test_ltp_returns_decimal(self, market_data: MarketDataPort) -> None:
        MarketDataContractTests().test_ltp_returns_decimal(market_data)

    def test_ltp_is_positive(self, market_data: MarketDataPort) -> None:
        MarketDataContractTests().test_ltp_is_positive(market_data)

    def test_quote_returns_quote(self, market_data: MarketDataPort) -> None:
        MarketDataContractTests().test_quote_returns_quote(market_data)

    def test_depth_returns_depth(self, market_data: MarketDataPort) -> None:
        MarketDataContractTests().test_depth_returns_depth(market_data)

    def test_ltp_batch_returns_dict(self, market_data: MarketDataPort) -> None:
        MarketDataContractTests().test_ltp_batch_returns_dict(market_data)

    def test_quote_batch_returns_dict(self, market_data: MarketDataPort) -> None:
        MarketDataContractTests().test_quote_batch_returns_dict(market_data)

    # ── Broker-specific subclasses ──────────────────────────────────────


class TestDhanMarketDataContract(TestMarketDataContractConformance):
    @pytest.fixture
    def market_data(self) -> MarketDataPort:
        from brokers.adapters.dhan.gateway import DhanGateway

        pytest.skip("Dhan integration test — requires credentials")


class TestUpstoxMarketDataContract(TestMarketDataContractConformance):
    @pytest.fixture
    def market_data(self) -> MarketDataPort:
        from brokers.adapters.upstox.gateway import UpstoxGateway

        pytest.skip("Upstox integration test — requires credentials")


class TestPaperMarketDataContract(TestMarketDataContractConformance):
    @pytest.fixture
    def market_data(self) -> MarketDataPort:
        from brokers.adapters.paper.gateway import PaperGateway

        gw = PaperGateway()
        return gw.market_data
