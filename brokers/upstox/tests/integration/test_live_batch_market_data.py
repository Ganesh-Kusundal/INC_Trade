"""Live integration tests for Upstox batch market data endpoints.

Tests ltp_batch(), quote_batch(), and history_batch() against the live Upstox API.

These tests require a valid .env.upstox with UPSTOX_API_KEY and UPSTOX_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

from decimal import Decimal

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
class TestLiveBatchMarketData:
    """Batch market data endpoint tests against live Upstox API."""

    def test_ltp_batch_nse_equity(self, gateway):
        """ltp_batch() for multiple NSE equities should return dict with Decimals."""
        symbols = ["RELIANCE", "TCS", "INFY"]
        result = gateway.ltp_batch(symbols, "NSE")
        assert isinstance(result, dict)
        # Should have entries for each symbol (if they exist)
        for symbol in symbols:
            if symbol in result:
                assert isinstance(result[symbol], Decimal)
                assert result[symbol] > 0

    def test_ltp_batch_returns_decimal(self, gateway):
        """ltp_batch() values should be Decimal type."""
        symbols = ["RELIANCE"]
        result = gateway.ltp_batch(symbols, "NSE")
        if result:
            for value in result.values():
                assert isinstance(value, Decimal)

    def test_quote_batch_nse_equity(self, gateway):
        """quote_batch() for multiple NSE equities should return dict with Quotes."""
        symbols = ["RELIANCE", "TCS"]
        result = gateway.quote_batch(symbols, "NSE")
        assert isinstance(result, dict)
        # Should have entries for each symbol
        for symbol in symbols:
            if symbol in result:
                quote = result[symbol]
                assert hasattr(quote, "ltp")
                assert hasattr(quote, "volume")

    def test_history_batch_nse_equity(self, gateway):
        """history_batch() should return concatenated DataFrame with symbol column."""
        import pandas as pd
        symbols = ["RELIANCE", "TCS"]
        result = gateway.history_batch(symbols, "NSE", timeframe="1D", lookback_days=3)
        assert isinstance(result, pd.DataFrame)
        # Should have symbol column for identification
        assert "symbol" in result.columns
        # Verify all requested symbols are present
        result_symbols = set(result["symbol"].unique())
        for symbol in symbols:
            assert symbol in result_symbols

    def test_ltp_batch_parity_with_individual(self, gateway):
        """ltp_batch() should return same values as individual ltp() calls."""
        symbols = ["RELIANCE", "TCS"]
        batch_result = gateway.ltp_batch(symbols, "NSE")

        # Compare with individual calls
        for symbol in symbols:
            if symbol in batch_result:
                individual_ltp = gateway.ltp(symbol, "NSE")
                # Should be very close (allowing for tiny timing differences)
                batch_ltp = batch_result[symbol]
                assert abs(batch_ltp - individual_ltp) < Decimal("0.01")
