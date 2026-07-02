"""Live integration tests for Upstox market quotes (NSE, INDEX).

These tests require a valid .env.upstox with UPSTOX_API_KEY and UPSTOX_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
class TestLiveQuotes:
    """End-to-end quote retrieval against the live Upstox API."""

    def test_nse_equity_quote(self, gateway):
        """RELIANCE on NSE should return a quote with ltp > 0."""
        quote = gateway.quote("RELIANCE", "NSE")
        assert quote.ltp > 0

    def test_index_quote(self, gateway):
        """NIFTY index should return a quote with ltp > 0."""
        quote = gateway.quote("NIFTY", "INDEX")
        assert quote.ltp > 0

    def test_quote_schema(self, gateway):
        """quote() should return Quote with required fields."""
        quote = gateway.quote("RELIANCE", "NSE")
        assert hasattr(quote, "ltp")
        assert hasattr(quote, "open")
        assert hasattr(quote, "high")
        assert hasattr(quote, "low")
        assert hasattr(quote, "close")
        assert hasattr(quote, "volume")
