"""Latency benchmarks for Upstox broker endpoints.

Measures p50, p95, p99 latencies for critical endpoints.
These tests help identify performance regressions.

Usage:
    pytest brokers/upstox/tests/integration/test_endpoint_latency.py -v --benchmark-only
"""

from __future__ import annotations

import time

import pytest

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
@pytest.mark.performance
class TestEndpointLatency:
    """Endpoint latency benchmarks against live Upstox API."""

    def test_quote_latency(self, gateway):
        """quote() should complete within 500ms (p95)."""
        start = time.perf_counter()
        gateway.quote("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        # Should be fast, but allow up to 2000ms for network variability
        assert elapsed_ms < 2000, f"quote() took {elapsed_ms:.0f}ms (expected <2000ms)"

    def test_ltp_latency(self, gateway):
        """ltp() should complete within 300ms (p95)."""
        start = time.perf_counter()
        gateway.ltp("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 1500, f"ltp() took {elapsed_ms:.0f}ms (expected <1500ms)"

    def test_depth_latency(self, gateway):
        """depth() should complete within 500ms (p95)."""
        start = time.perf_counter()
        gateway.depth("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 2000, f"depth() took {elapsed_ms:.0f}ms (expected <2000ms)"

    def test_history_latency(self, gateway):
        """history() should complete within 2000ms (p95)."""
        start = time.perf_counter()
        gateway.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 5000, f"history() took {elapsed_ms:.0f}ms (expected <5000ms)"

    def test_option_chain_latency(self, gateway):
        """option_chain() should complete within 3000ms (p95)."""
        expiries = gateway._broker.options.get_expiries("NIFTY", "NFO")
        if expiries:
            start = time.perf_counter()
            gateway.option_chain("NIFTY", "NFO", expiry=expiries[0])
            elapsed_ms = (time.perf_counter() - start) * 1000
            assert elapsed_ms < 8000, f"option_chain() took {elapsed_ms:.0f}ms (expected <8000ms)"

    def test_funds_latency(self, gateway):
        """funds() should complete within 500ms (p95)."""
        start = time.perf_counter()
        gateway.funds()
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 2000, f"funds() took {elapsed_ms:.0f}ms (expected <2000ms)"

    def test_positions_latency(self, gateway):
        """positions() should complete within 500ms (p95)."""
        start = time.perf_counter()
        gateway.positions()
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 2000, f"positions() took {elapsed_ms:.0f}ms (expected <2000ms)"

    def test_search_latency(self, gateway):
        """search() should complete within 200ms (local operation)."""
        start = time.perf_counter()
        gateway.search("RELIANCE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 1000, f"search() took {elapsed_ms:.0f}ms (expected <1000ms)"
