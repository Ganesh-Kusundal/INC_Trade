"""Endpoint latency benchmarks for modern Upstox gateway."""

from __future__ import annotations

import time

import pytest

from brokers.tests.integration.upstox.conftest import skip_live


@skip_live
@pytest.mark.performance
class TestEndpointLatency:
    def test_quote_latency(self, gateway):
        start = time.perf_counter()
        gateway.market_data.quote("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 2000, f"quote() took {elapsed_ms:.0f}ms"

    def test_ltp_latency(self, gateway):
        start = time.perf_counter()
        gateway.market_data.ltp("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 1500, f"ltp() took {elapsed_ms:.0f}ms"

    def test_depth_latency(self, gateway):
        start = time.perf_counter()
        gateway.market_data.depth("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 2000, f"depth() took {elapsed_ms:.0f}ms"

    def test_funds_latency(self, gateway):
        start = time.perf_counter()
        gateway.portfolio.funds()
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 2000, f"funds() took {elapsed_ms:.0f}ms"

    def test_instrument_search_latency(self, gateway):
        start = time.perf_counter()
        gateway.instruments.search("RELIANCE", limit=5)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"search() took {elapsed_ms:.0f}ms"
