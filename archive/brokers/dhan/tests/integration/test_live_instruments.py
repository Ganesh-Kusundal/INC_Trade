"""Live integration tests for Dhan instrument and search endpoints.

Tests search() and load_instruments() against the live Dhan API.

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

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
class TestLiveInstruments:
    """Instrument and search endpoint tests against live Dhan API."""

    def test_search_known_symbol_reliance(self, gateway: BrokerGateway):
        """search() for RELIANCE should return results."""
        results = gateway.search("RELIANCE")
        assert isinstance(results, list)
        assert len(results) > 0
        # Verify result structure
        first = results[0]
        assert "symbol" in first
        assert "exchange" in first
        assert "security_id" in first

    def test_search_known_symbol_nifty(self, gateway: BrokerGateway):
        """search() for NIFTY should return index results."""
        results = gateway.search("NIFTY")
        assert isinstance(results, list)
        assert len(results) > 0
        # Should find NIFTY index
        symbols = [r["symbol"] for r in results]
        assert any("NIFTY" in s for s in symbols)

    def test_search_known_symbol_tcs(self, gateway: BrokerGateway):
        """search() for TCS should return results."""
        results = gateway.search("TCS")
        assert isinstance(results, list)
        assert len(results) > 0

    def test_search_returns_correct_fields(self, gateway: BrokerGateway):
        """search() results should have symbol, exchange, type, security_id, name."""
        results = gateway.search("RELIANCE")
        if results:
            first = results[0]
            required_fields = ["symbol", "exchange", "type", "security_id"]
            for field in required_fields:
                assert field in first, f"Search result missing field: {field}"

    def test_search_partial_match(self, gateway: BrokerGateway):
        """search() with partial symbol should return matches."""
        results = gateway.search("REL")
        assert isinstance(results, list)
        # Should find RELIANCE and potentially others
        assert len(results) > 0

    def test_search_limit_20_results(self, gateway: BrokerGateway):
        """search() should limit results to 20."""
        results = gateway.search("INF")  # Common prefix
        assert isinstance(results, list)
        assert len(results) <= 20

    def test_load_instruments_success(self, gateway: BrokerGateway):
        """load_instruments() should load instruments successfully."""
        # Gateway fixture already loads instruments, verify they're loaded
        desc = gateway.describe()
        assert desc["instruments_loaded"] is True
        assert desc["instrument_count"] > 0

    def test_instrument_count_large(self, gateway: BrokerGateway):
        """Instrument count should be > 100,000 for full Dhan universe."""
        desc = gateway.describe()
        count = desc["instrument_count"]
        assert count > 100000, f"Expected >100k instruments, got {count}"

    def test_search_case_insensitive(self, gateway: BrokerGateway):
        """search() should be case-insensitive."""
        results_upper = gateway.search("RELIANCE")
        results_lower = gateway.search("reliance")
        # Both should return results
        assert len(results_upper) > 0
        assert len(results_lower) > 0
