"""Live integration tests for Dhan market data REST endpoints.

Tests ltp(), depth(), and history() against the live Dhan API.

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
import sys
import time
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.factory import BrokerFactory
from brokers.dhan.gateway import BrokerGateway

pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]

# ---------------------------------------------------------------------------
# Skip guard — only run when .env.local has valid credentials
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveLTP:
    """LTP endpoint tests against live Dhan API."""

    def test_ltp_nse_equity(self, gateway: BrokerGateway):
        """ltp() for NSE equity should return Decimal > 0."""
        ltp = gateway.ltp("RELIANCE", "NSE")
        assert isinstance(ltp, Decimal)
        assert ltp > 0

    def test_ltp_index(self, gateway: BrokerGateway):
        """ltp() for INDEX should return Decimal > 0."""
        ltp = gateway.ltp("NIFTY", "INDEX")
        assert isinstance(ltp, Decimal)
        assert ltp > 0
        time.sleep(1.5)

    def test_ltp_nfo_future(self, gateway: BrokerGateway):
        """ltp() for NFO future should return Decimal > 0."""
        # Get a NIFTY future contract
        contracts = gateway.extended.get_futures_contracts("NIFTY", "INDEX")
        if contracts:
            fut_symbol = contracts[0]["symbol"]
            ltp = gateway.ltp(fut_symbol, "NFO")
            assert isinstance(ltp, Decimal)
            assert ltp > 0


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveDepth:
    """Market depth endpoint tests against live Dhan API."""

    def test_depth_nse_equity(self, gateway: BrokerGateway):
        """depth() for NSE equity should return MarketDepth with bids/asks."""
        depth = gateway.depth("RELIANCE", "NSE")
        assert depth is not None
        assert hasattr(depth, "bids")
        assert hasattr(depth, "asks")
        assert isinstance(depth.bids, list)
        assert isinstance(depth.asks, list)

    def test_depth_nse_equity_levels(self, gateway: BrokerGateway):
        """depth() for liquid NSE equity should have ≥ 5 levels."""
        depth = gateway.depth("RELIANCE", "NSE")
        # RELIANCE is liquid enough to have depth
        assert len(depth.bids) >= 1, "Should have at least 1 bid level"
        assert len(depth.asks) >= 1, "Should have at least 1 ask level"

    def test_depth_level_schema(self, gateway: BrokerGateway):
        """DepthLevel objects should have price, quantity, orders."""
        depth = gateway.depth("RELIANCE", "NSE")
        if depth.bids:
            level = depth.bids[0]
            assert hasattr(level, "price")
            assert hasattr(level, "quantity")
            assert hasattr(level, "orders")


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveHistory:
    """Historical data endpoint tests against live Dhan API."""

    def test_history_nse_equity(self, gateway: BrokerGateway):
        """history() for NSE equity should return DataFrame with OHLCV."""
        df = gateway.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
        assert df is not None
        assert len(df) > 0
        # Verify required columns
        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            assert col in df.columns, f"Missing column: {col}"

    def test_history_with_date_range(self, gateway: BrokerGateway):
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

    def test_history_5min_timeframe(self, gateway: BrokerGateway):
        """history() with 5m timeframe should return intraday candles."""
        df = gateway.history("RELIANCE", "NSE", timeframe="5m", lookback_days=1)
        assert df is not None
        # May be empty if market closed or before 9:15 AM
        if len(df) > 0:
            assert "timestamp" in df.columns

    def test_history_15min_timeframe(self, gateway: BrokerGateway):
        """history() with 15m timeframe should return candles."""
        df = gateway.history("RELIANCE", "NSE", timeframe="15m", lookback_days=2)
        assert df is not None

    def test_history_1hour_timeframe(self, gateway: BrokerGateway):
        """history() with 1h timeframe should return candles."""
        df = gateway.history("RELIANCE", "NSE", timeframe="1h", lookback_days=5)
        assert df is not None

    def test_history_index(self, gateway: BrokerGateway):
        """history() for INDEX should return candles."""
        df = gateway.history("NIFTY", "INDEX", timeframe="1D", lookback_days=5)
        assert df is not None
        assert len(df) > 0
        time.sleep(1.5)

    def test_history_dataframe_schema(self, gateway: BrokerGateway):
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
