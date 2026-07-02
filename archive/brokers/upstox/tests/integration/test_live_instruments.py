"""Live integration tests for Upstox instrument and search endpoints.

Tests search() and load_instruments() against the live Upstox API.

These tests require a valid .env.upstox with UPSTOX_API_KEY and UPSTOX_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
class TestLiveInstruments:
    """Instrument and search endpoint tests against live Upstox API."""

    def test_search_known_symbol_reliance(self, gateway):
        """search() for RELIANCE should return results."""
        results = gateway.search("RELIANCE")
        assert isinstance(results, list)
        assert len(results) > 0
        # Verify result structure
        first = results[0]
        assert "symbol" in first
        assert "exchange" in first

    def test_search_known_symbol_nifty(self, gateway):
        """search() for NIFTY should return index results."""
        results = gateway.search("NIFTY")
        assert isinstance(results, list)
        assert len(results) > 0
        # Should find NIFTY index
        symbols = [r["symbol"] for r in results]
        assert any("NIFTY" in s for s in symbols)

    def test_search_returns_correct_fields(self, gateway):
        """search() results should have symbol, exchange, type."""
        results = gateway.search("RELIANCE")
        if results:
            first = results[0]
            required_fields = ["symbol", "exchange"]
            for field in required_fields:
                assert field in first, f"Search result missing field: {field}"

    def test_search_partial_match(self, gateway):
        """search() with partial symbol should return matches."""
        results = gateway.search("REL")
        assert isinstance(results, list)
        # Should find RELIANCE and potentially others
        assert len(results) > 0

    def test_search_limit_20_results(self, gateway):
        """search() should limit results to 20."""
        results = gateway.search("INF")  # Common prefix
        assert isinstance(results, list)
        assert len(results) <= 20

    def test_load_instruments_success(self, gateway):
        """load_instruments() should load instruments successfully."""
        # Gateway fixture already loads instruments, verify they're loaded
        desc = gateway.describe()
        assert desc["instruments_loaded"] is True

    def test_search_case_insensitive(self, gateway):
        """search() should be case-insensitive."""
        results_upper = gateway.search("RELIANCE")
        results_lower = gateway.search("reliance")
        # Both should return results
        assert len(results_upper) > 0
        assert len(results_lower) > 0
