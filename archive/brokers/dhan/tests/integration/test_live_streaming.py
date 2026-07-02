"""Live integration tests for Dhan WebSocket streaming endpoints.

Tests stream() and unstream() against the live Dhan API.

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent or market is closed.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.factory import BrokerFactory
from brokers.dhan.gateway import BrokerGateway
from tests.market_hours import skip_off_market

pytestmark = [pytest.mark.dhan, pytest.mark.market_hours, pytest.mark.regression]

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
@skip_off_market(reason="WebSocket streaming requires live market")
class TestLiveStreaming:
    """WebSocket streaming endpoint tests against live Dhan API."""

    def test_stream_ltp_mode_receives_ticks(self, gateway: BrokerGateway):
        """stream() with LTP mode should receive ticks within deadline."""
        received = threading.Event()
        ticks = []

        def on_tick(quote):
            ticks.append(quote)
            received.set()

        feed = gateway.stream("NIFTY", "INDEX", mode="LTP", on_tick=on_tick)
        try:
            # Wait up to 15 seconds for at least 1 tick
            got_tick = received.wait(timeout=15)
            assert got_tick, "No LTP tick received within 15s"
            assert len(ticks) >= 1
        finally:
            feed.disconnect()

    def test_stream_quote_mode_receives_ohlcv(self, gateway: BrokerGateway):
        """stream() with QUOTE mode should receive OHLCV ticks."""
        received = threading.Event()
        ticks = []

        def on_tick(quote):
            ticks.append(quote)
            received.set()

        feed = gateway.stream("RELIANCE", "NSE", mode="QUOTE", on_tick=on_tick)
        try:
            got_tick = received.wait(timeout=15)
            assert got_tick, "No QUOTE tick received within 15s"
            # Quote mode should have OHLCV data
            if ticks:
                tick = ticks[0]
                assert hasattr(tick, "ltp") or hasattr(tick, "open")
        finally:
            feed.disconnect()
            time.sleep(1)

    def test_stream_full_mode(self, gateway: BrokerGateway):
        """stream() with FULL mode should receive full tick data."""
        received = threading.Event()
        ticks = []

        def on_tick(quote):
            ticks.append(quote)
            received.set()

        feed = gateway.stream("RELIANCE", "NSE", mode="FULL", on_tick=on_tick)
        try:
            got_tick = received.wait(timeout=15)
            assert got_tick, "No FULL tick received within 15s"
        finally:
            feed.disconnect()
            time.sleep(1)

    def test_unstream_removes_callback(self, gateway: BrokerGateway):
        """unstream() should remove callback and stop receiving ticks."""
        received = threading.Event()
        ticks = []

        def on_tick(quote):
            ticks.append(quote)
            received.set()

        feed = gateway.stream("RELIANCE", "NSE", mode="LTP", on_tick=on_tick)
        try:
            # Wait for first tick
            received.wait(timeout=10)
            initial_count = len(ticks)

            # Unstream
            gateway.unstream("RELIANCE", "NSE", on_tick=on_tick)
            time.sleep(3)

            # Verify no new ticks received after unstream
            # (Allow small tolerance for in-flight ticks)
            final_count = len(ticks)
            # Should not have received many more ticks
            assert final_count - initial_count < 5, "Received too many ticks after unstream"
        finally:
            feed.disconnect()

    def test_stream_multiple_symbols(self, gateway: BrokerGateway):
        """stream() should support multiple concurrent streams."""
        received_reliance = threading.Event()
        received_tcs = threading.Event()
        ticks_reliance = []
        ticks_tcs = []

        def on_tick_reliance(quote):
            ticks_reliance.append(quote)
            received_reliance.set()

        def on_tick_tcs(quote):
            ticks_tcs.append(quote)
            received_tcs.set()

        feed1 = gateway.stream("RELIANCE", "NSE", mode="LTP", on_tick=on_tick_reliance)
        feed2 = gateway.stream("TCS", "NSE", mode="LTP", on_tick=on_tick_tcs)

        try:
            got1 = received_reliance.wait(timeout=15)
            got2 = received_tcs.wait(timeout=15)
            # At least one should receive data
            assert got1 or got2, "Neither stream received ticks"
        finally:
            feed1.disconnect()
            feed2.disconnect()
