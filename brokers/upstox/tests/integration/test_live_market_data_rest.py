"""Live integration tests for Upstox market data REST endpoints.

Tests ltp(), depth(), and history() against the live Upstox API.

These tests require a valid .env.upstox with UPSTOX_API_KEY and UPSTOX_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

from decimal import Decimal

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
class TestLiveLTP:
    """LTP endpoint tests against live Upstox API."""

    def test_ltp_nse_equity(self, gateway):
        """ltp() for NSE equity should return Decimal > 0."""
        ltp = gateway.ltp("RELIANCE", "NSE")
        assert isinstance(ltp, Decimal)
        assert ltp > 0

    def test_ltp_index(self, gateway):
        """ltp() for INDEX should return Decimal > 0."""
        ltp = gateway.ltp("NIFTY", "INDEX")
        assert isinstance(ltp, Decimal)
        assert ltp > 0


@skip_live
class TestLiveDepth:
    """Market depth endpoint tests against live Upstox API."""

    def test_depth_nse_equity(self, gateway):
        """depth() for NSE equity should return MarketDepth with bids/asks."""
        depth = gateway.depth("RELIANCE", "NSE")
        assert depth is not None
        assert hasattr(depth, "bids")
        assert hasattr(depth, "asks")
        assert isinstance(depth.bids, list)
        assert isinstance(depth.asks, list)

    def test_depth_nse_equity_levels(self, gateway):
        """depth() for liquid NSE equity should have ≥ 1 levels."""
        depth = gateway.depth("RELIANCE", "NSE")
        # RELIANCE is liquid enough to have depth
        assert len(depth.bids) >= 1, "Should have at least 1 bid level"
        assert len(depth.asks) >= 1, "Should have at least 1 ask level"

    def test_depth_level_schema(self, gateway):
        """DepthLevel objects should have price, quantity, orders."""
        depth = gateway.depth("RELIANCE", "NSE")
        if depth.bids:
            level = depth.bids[0]
            assert hasattr(level, "price")
            assert hasattr(level, "quantity")
            assert hasattr(level, "orders")


@skip_live
class TestLiveHistory:
    """Historical data endpoint tests against live Upstox API."""

    def test_history_nse_equity(self, gateway):
        """history() for NSE equity should return DataFrame with OHLCV."""
        df = gateway.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
        assert df is not None
        assert len(df) > 0
        # Verify required columns
        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            assert col in df.columns, f"Missing column: {col}"

    def test_history_with_date_range(self, gateway):
        """history() with explicit from_date/to_date should work."""
        df = gateway.history(
            "RELIANCE",
            "NSE",
            timeframe="1D",
            from_date="2026-06-20",
            to_date="2026-06-25",
        )
        assert df is not None
        assert len(df) > 0

    def test_history_5min_timeframe(self, gateway):
        """history() with 5MIN timeframe should return intraday candles."""
        df = gateway.history("RELIANCE", "NSE", timeframe="5MIN", lookback_days=1)
        assert df is not None
        # May be empty if market closed or before 9:15 AM
        if len(df) > 0:
            assert "timestamp" in df.columns

    def test_history_15min_timeframe(self, gateway):
        """history() with 15MIN timeframe should return candles."""
        df = gateway.history("RELIANCE", "NSE", timeframe="15MIN", lookback_days=2)
        assert df is not None

    def test_history_1hour_timeframe(self, gateway):
        """history() with 60MIN timeframe should return candles."""
        df = gateway.history("RELIANCE", "NSE", timeframe="60MIN", lookback_days=5)
        assert df is not None

    def test_history_index(self, gateway):
        """history() for INDEX should return candles."""
        df = gateway.history("NIFTY", "INDEX", timeframe="1D", lookback_days=5)
        assert df is not None
        assert len(df) > 0

    def test_history_dataframe_schema(self, gateway):
        """history() DataFrame should have canonical schema."""
        df = gateway.history("RELIANCE", "NSE", timeframe="1D", lookback_days=3)
        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            assert col in df.columns, f"Missing column: {col}"

        # Verify data types
        assert len(df["open"]) > 0
        assert len(df["high"]) > 0
        assert len(df["low"]) > 0
        assert len(df["close"]) > 0
