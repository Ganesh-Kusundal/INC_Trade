"""Live integration tests — market quotes via modern UpstoxGateway."""

from __future__ import annotations

from brokers.tests.integration.upstox.conftest import skip_live


@skip_live
class TestLiveQuotes:
    def test_nse_equity_quote(self, gateway):
        quote = gateway.market_data.quote("RELIANCE", "NSE")
        assert quote.ltp > 0

    def test_index_ltp(self, gateway):
        ltp = gateway.market_data.ltp("NIFTY", "INDEX")
        assert ltp > 0

    def test_quote_schema(self, gateway):
        quote = gateway.market_data.quote("RELIANCE", "NSE")
        assert hasattr(quote, "ltp")
        assert hasattr(quote, "open")
        assert hasattr(quote, "high")
        assert hasattr(quote, "low")
