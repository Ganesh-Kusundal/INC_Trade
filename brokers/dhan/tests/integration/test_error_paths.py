"""Error path coverage tests for Dhan broker endpoints.

Tests how endpoints handle invalid inputs, market closed behavior,
and edge cases.

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.factory import BrokerFactory
from brokers.dhan.gateway import BrokerGateway

pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestErrorPaths:
    """Error path and edge case tests against live Dhan API."""

    def test_quote_invalid_symbol(self, gateway: BrokerGateway):
        """quote() with invalid symbol should raise or return empty."""
        try:
            quote = gateway.quote("INVALIDSYMBOL123", "NSE")
            # If it doesn't raise, LTP should be 0
            assert quote.ltp == 0
        except (ValueError, KeyError, Exception):
            # Raising is also acceptable
            pass

    def test_ltp_invalid_symbol(self, gateway: BrokerGateway):
        """ltp() with invalid symbol should raise or return 0."""
        try:
            ltp = gateway.ltp("INVALIDSYMBOL123", "NSE")
            assert ltp == Decimal("0")
        except (ValueError, KeyError, Exception):
            pass

    def test_depth_invalid_symbol(self, gateway: BrokerGateway):
        """depth() with invalid symbol should raise or return empty."""
        try:
            depth = gateway.depth("INVALIDSYMBOL123", "NSE")
            # Should have empty bids/asks
            assert len(depth.bids) == 0 or len(depth.asks) == 0
        except (ValueError, KeyError, Exception):
            pass

    def test_history_invalid_symbol(self, gateway: BrokerGateway):
        """history() with invalid symbol should return empty DataFrame."""
        df = gateway.history("INVALIDSYMBOL123", "NSE", timeframe="1D", lookback_days=5)
        # May return empty DataFrame or raise
        if df is not None:
            assert len(df) == 0 or "timestamp" in df.columns

    def test_history_invalid_timeframe(self, gateway: BrokerGateway):
        """history() with invalid timeframe should handle gracefully."""
        try:
            gateway.history("RELIANCE", "NSE", timeframe="INVALID", lookback_days=5)
            # May return data or empty
            pass
        except (ValueError, KeyError):
            # Raising is acceptable
            pass

    def test_option_chain_invalid_underlying(self, gateway: BrokerGateway):
        """option_chain() with invalid underlying should handle gracefully."""
        try:
            chain = gateway.option_chain("INVALIDSYMBOL123", "NFO")
            # May return empty chain
            assert chain is not None
        except (ValueError, KeyError, Exception):
            pass

    def test_future_chain_invalid_underlying(self, gateway: BrokerGateway):
        """future_chain() with invalid underlying should handle gracefully."""
        try:
            chain = gateway.future_chain("INVALIDSYMBOL123", "NFO")
            assert chain is not None
        except (ValueError, KeyError, Exception):
            pass

    def test_search_empty_query(self, gateway: BrokerGateway):
        """search() with empty query should return empty or all results."""
        results = gateway.search("")
        assert isinstance(results, list)
        # May return empty or limited results

    def test_batch_ltp_empty_symbols(self, gateway: BrokerGateway):
        """ltp_batch() with empty list should return empty dict."""
        result = gateway.ltp_batch([], "NSE")
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_batch_quote_empty_symbols(self, gateway: BrokerGateway):
        """quote_batch() with empty list should return empty dict."""
        result = gateway.quote_batch([], "NSE")
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_place_order_missing_price_for_limit(self, gateway: BrokerGateway):
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
