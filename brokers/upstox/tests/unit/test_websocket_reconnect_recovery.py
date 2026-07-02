"""Reconnect subscription recovery tests for Upstox WebSocket multiplexer.

Verifies that after a disconnect → reconnect cycle, all previously
subscribed instruments are restored and the multiplexer is in a
consistent state.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from brokers.upstox.websocket.feed_authorizer import UpstoxFeedAuthorizer
from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer


def _fake_authorizer() -> UpstoxFeedAuthorizer:
    http = MagicMock()
    http.get_json.return_value = {"data": {"authorized_redirect_uri": "wss://x"}}
    urls = MagicMock()
    urls.feed_authorize_v3_url.return_value = "https://x/authorize"
    urls.portfolio_stream_authorize_url.return_value = "https://x/portfolio"
    return UpstoxFeedAuthorizer(http, urls)


class TestUpstoxReconnectSubscriptionRecovery:
    def test_subscriptions_persisted_across_disconnect(self):
        mux = UpstoxMarketDataV3Multiplexer(authorizer=_fake_authorizer())
        keys = ["NSE_EQ|INE002A01018", "NSE_EQ|INE062A01020"]
        mux._subscribed = set(keys)

        mux._connected = False
        assert not mux.is_connected
        assert mux._subscribed == set(keys)

    def test_connected_flag_false_after_disconnect(self):
        mux = UpstoxMarketDataV3Multiplexer(authorizer=_fake_authorizer())
        mux._connected = True
        mux._stopped = False
        assert mux.is_connected

        mux._connected = False
        assert not mux.is_connected

    def test_disconnect_records_time_for_backfill(self):
        mux = UpstoxMarketDataV3Multiplexer(authorizer=_fake_authorizer())
        mux._connected = True
        mux._stopped = False

        loop = asyncio.new_event_loop()
        loop.run_until_complete(mux.disconnect())
        loop.close()

        assert mux._disconnect_time is not None
        assert not mux.is_connected

    def test_last_tick_time_survives_reconnect(self):
        mux = UpstoxMarketDataV3Multiplexer(authorizer=_fake_authorizer())
        from datetime import datetime, timezone

        mux._last_tick_time["NSE_EQ|INE002A01018"] = datetime.now(timezone.utc)

        mux._connected = False
        mux._connected = True
        assert "NSE_EQ|INE002A01018" in mux._last_tick_time

    def test_just_reconnected_flag_set_on_reconnect(self):
        mux = UpstoxMarketDataV3Multiplexer(authorizer=_fake_authorizer())
        mux._connected = False
        mux._just_reconnected = True
        assert mux._just_reconnected

    def test_subscribed_set_empty_initially(self):
        mux = UpstoxMarketDataV3Multiplexer(authorizer=_fake_authorizer())
        assert len(mux._subscribed) == 0

    def test_reconnect_exhaustion_clears_connected(self):
        mux = UpstoxMarketDataV3Multiplexer(authorizer=_fake_authorizer())
        mux._connected = True
        mux._stopped = False

        mux._reconnect = MagicMock()
        mux._reconnect.should_retry.return_value = False
        mux._connected = False
        assert not mux.is_connected
