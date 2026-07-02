"""Live integration tests for Dhan batch market data endpoints.

Tests ltp_batch(), quote_batch(), and history_batch() against the live Dhan API.

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
import sys
import time
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.factory import BrokerFactory

pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]
from brokers.dhan.gateway import BrokerGateway

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
class TestLiveBatchMarketData:
    """Batch market data endpoint tests against live Dhan API."""

    def test_ltp_batch_nse_equity(self, gateway: BrokerGateway):
        """ltp_batch() for multiple NSE equity symbols should return dict."""
        symbols = ["RELIANCE", "TCS", "INFY"]
        result = gateway.ltp_batch(symbols, "NSE")
        assert isinstance(result, dict)
        assert len(result) == len(symbols)
        # Verify all symbols have LTP > 0
        for sym in symbols:
            assert sym in result
            assert result[sym] > 0

    def test_ltp_batch_returns_decimal(self, gateway: BrokerGateway):
        """ltp_batch() values should be Decimal instances."""
        symbols = ["RELIANCE", "TCS"]
        result = gateway.ltp_batch(symbols, "NSE")
        for sym, ltp in result.items():
            assert isinstance(ltp, Decimal), f"LTP for {sym} is not Decimal"

    def test_quote_batch_nse_equity(self, gateway: BrokerGateway):
        """quote_batch() for multiple symbols should return dict of quotes."""
        symbols = ["RELIANCE", "TCS"]
        result = gateway.quote_batch(symbols, "NSE")
        assert isinstance(result, dict)
        assert len(result) == len(symbols)
        # Verify quote structure
        for sym in symbols:
            assert sym in result
            quote = result[sym]
            assert hasattr(quote, "ltp") or "ltp" in quote
            assert hasattr(quote, "symbol") or "symbol" in quote

    def test_history_batch_nse_equity(self, gateway: BrokerGateway):
        """history_batch() for multiple symbols should return concatenated DataFrame."""
        symbols = ["RELIANCE", "TCS"]
        result = gateway.history_batch(symbols, "NSE", timeframe="1D", lookback_days=3)
        assert result is not None
        assert isinstance(result, pd.DataFrame)
        # Verify concatenated DataFrame has symbol column
        assert "symbol" in result.columns, "symbol column missing from history_batch result"
        # Verify all symbols are present
        result_symbols = set(result["symbol"].unique())
        for sym in symbols:
            assert sym in result_symbols, f"{sym} missing from history_batch result"

    def test_ltp_batch_parity_with_individual(self, gateway: BrokerGateway):
        """ltp_batch() results should match individual ltp() calls."""
        symbols = ["RELIANCE", "TCS"]
        # Get batch results
        batch_result = gateway.ltp_batch(symbols, "NSE")
        time.sleep(2)
        # Get individual results
        individual_results = {}
        for sym in symbols:
            individual_results[sym] = gateway.ltp(sym, "NSE")
        # Compare (allow small differences due to market movement)
        for sym in symbols:
            batch_ltp = batch_result[sym]
            individual_ltp = individual_results[sym]
            # Should be within 1% of each other
            if individual_ltp > 0:
                diff_pct = abs(batch_ltp - individual_ltp) / individual_ltp * 100
                assert diff_pct < 1.0, f"{sym}: batch vs individual diff {diff_pct:.2f}%"
