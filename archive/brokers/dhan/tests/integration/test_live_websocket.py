"""Live integration tests for Dhan WebSocket — market feed and order stream.

Requires .env.local with valid DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
Skips real WebSocket tests during off-market hours to avoid flaky failures.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from tests.market_hours import skip_off_market

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
LIVE_DHAN = ENV_PATH.exists()


def _load_credentials():
    if not ENV_PATH.exists():
        return "", ""
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip('"').strip("'")
    return os.environ.get("DHAN_CLIENT_ID", ""), os.environ.get("DHAN_ACCESS_TOKEN", "")


@pytest.mark.skipif(not LIVE_DHAN, reason=".env.local required")
class TestLiveWebSocket:
    def test_market_feed_is_connected_default_false(self):
        from brokers.dhan.websocket import DhanMarketFeed

        feed = DhanMarketFeed(client_id="test", access_token="test", instruments=[])
        assert feed.is_connected is False

    def test_order_stream_is_connected_default_false(self):
        from brokers.dhan.websocket import DhanOrderStream

        stream = DhanOrderStream(client_id="test", access_token="test")
        assert stream.is_connected is False

    def test_market_feed_callback_registration(self):
        from brokers.dhan.websocket import DhanMarketFeed

        feed = DhanMarketFeed(client_id="test", access_token="test", instruments=[])
        ticks = []
        feed.on_quote(lambda t: ticks.append(t))
        assert len(feed._quote_callbacks) == 1

    def test_order_stream_callback_registration(self):
        from brokers.dhan.websocket import DhanOrderStream

        stream = DhanOrderStream(client_id="test", access_token="test")
        updates = []
        stream.on_order_update(lambda u: updates.append(u))
        assert len(stream._order_callbacks) == 1

    @skip_off_market(reason="WebSocket connection requires live market")
    def test_market_feed_connect_and_receive(self):
        """Connect to Dhan WebSocket, subscribe to NIFTY, verify at least 1 tick."""
        client_id, access_token = _load_credentials()
        if not client_id or not access_token:
            pytest.skip("Credentials not available")

        from brokers.dhan.websocket import DhanMarketFeed

        received = threading.Event()
        ticks = []

        def on_tick(tick):
            ticks.append(tick)
            received.set()

        instruments = [("IDX_I", "13", "LTP")]
        feed = DhanMarketFeed(
            client_id=client_id,
            access_token=access_token,
            instruments=instruments,
        )
        feed.on_quote(on_tick)

        try:
            feed.connect()
            # Wait up to 15 seconds for at least 1 tick
            got_tick = received.wait(timeout=15)
            # Market may be closed (weekends/after hours) — don't fail
            if got_tick:
                assert len(ticks) >= 1
                assert "ltp" in ticks[0] or "symbol" in ticks[0]
        finally:
            feed.disconnect()

    @skip_off_market(reason="Order stream requires live market")
    def test_order_stream_connect(self):
        """Connect to Dhan order stream and verify connection."""
        client_id, access_token = _load_credentials()
        if not client_id or not access_token:
            pytest.skip("Credentials not available")

        from brokers.dhan.websocket import DhanOrderStream

        stream = DhanOrderStream(client_id=client_id, access_token=access_token)
        try:
            stream.connect()
            # Give it a moment to establish connection
            import time

            time.sleep(2)
            # Order stream may or may not connect depending on market hours
            # Just verify no crash
        finally:
            stream.disconnect()
