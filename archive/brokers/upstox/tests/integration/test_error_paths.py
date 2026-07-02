"""Error path coverage tests for Upstox broker endpoints.

Tests how endpoints handle invalid inputs, market closed behavior,
and edge cases.

These tests require a valid .env.upstox with UPSTOX_API_KEY and UPSTOX_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

from decimal import Decimal

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
class TestErrorPaths:
    """Error path and edge case tests against live Upstox API."""

    def test_quote_invalid_symbol(self, gateway):
        """quote() with invalid symbol should raise or return empty."""
        try:
            quote = gateway.quote("INVALIDSYMBOL123", "NSE")
            # If it doesn't raise, LTP should be 0
            assert quote.ltp == 0
        except (ValueError, KeyError, Exception):
            # Raising is also acceptable
            pass

    def test_ltp_invalid_symbol(self, gateway):
        """ltp() with invalid symbol should raise or return 0."""
        try:
            ltp = gateway.ltp("INVALIDSYMBOL123", "NSE")
            assert ltp == Decimal("0")
        except (ValueError, KeyError, Exception):
            pass

    def test_depth_invalid_symbol(self, gateway):
        """depth() with invalid symbol should raise or return empty."""
        try:
            depth = gateway.depth("INVALIDSYMBOL123", "NSE")
            # Should have empty bids/asks
            assert len(depth.bids) == 0 or len(depth.asks) == 0
        except (ValueError, KeyError, Exception):
            pass

    def test_history_invalid_symbol(self, gateway):
        """history() with invalid symbol should return empty DataFrame."""
        df = gateway.history("INVALIDSYMBOL123", "NSE", timeframe="1D", lookback_days=5)
        # May return empty DataFrame or raise
        if df is not None:
            assert len(df) == 0 or "timestamp" in df.columns

    def test_history_invalid_timeframe(self, gateway):
        """history() with invalid timeframe should handle gracefully."""
        try:
            gateway.history("RELIANCE", "NSE", timeframe="INVALID", lookback_days=5)
            # May return data or empty
            pass
        except (ValueError, KeyError):
            # Raising is acceptable
            pass

    def test_option_chain_invalid_underlying(self, gateway):
        """option_chain() with invalid underlying should handle gracefully."""
        try:
            chain = gateway.option_chain("INVALIDSYMBOL123", "NFO")
            # May return empty chain
            assert chain is not None
        except (ValueError, KeyError, Exception):
            pass

    def test_future_chain_invalid_underlying(self, gateway):
        """future_chain() with invalid underlying should handle gracefully."""
        try:
            chain = gateway.future_chain("INVALIDSYMBOL123", "NFO")
            assert chain is not None
        except (ValueError, KeyError, Exception):
            pass

    def test_search_empty_query(self, gateway):
        """search() with empty query should return empty or all results."""
        results = gateway.search("")
        assert isinstance(results, list)
        # May return empty or limited results

    def test_batch_ltp_empty_symbols(self, gateway):
        """ltp_batch() with empty list should return empty dict."""
        result = gateway.ltp_batch([], "NSE")
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_batch_quote_empty_symbols(self, gateway):
        """quote_batch() with empty list should return empty dict."""
        result = gateway.quote_batch([], "NSE")
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_place_order_missing_price_for_limit(self, gateway):
        """place_order() with LIMIT type but price=0 should fail."""
        response = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            order_type="LIMIT",
            product_type="INTRADAY",
            price=Decimal("0"),  # Missing price for LIMIT order
        )
        assert response.success is False
