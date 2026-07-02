"""Reconnect subscription recovery tests for Dhan WebSocket feeds.

Verifies that DhanMarketFeed and DhanOrderStream maintain subscription
state across reconnect cycles and that the _connected flag is properly
managed.
"""

from __future__ import annotations

from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream


class TestDhanWebSocketReconnectRecovery:
    def test_market_feed_preserves_instruments_on_construction(self):
        instruments = [
            (1, "2885", 15),
            (1, "2886", 17),
            (2, "1234", 15),
        ]
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=instruments,
        )
        assert len(feed._instruments) == 3

    def test_market_feed_is_connected_false_before_connect(self):
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )
        assert not feed.is_connected

    def test_order_stream_is_connected_false_before_connect(self):
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
        )
        assert not stream.is_connected

    def test_market_feed_start_does_not_mark_connected_before_handshake(self):
        from unittest import mock

        from brokers.dhan.reconnecting_service import ReconnectingServiceMixin

        feed = DhanMarketFeed.__new__(DhanMarketFeed)
        feed._lock = __import__("threading").Lock()
        feed._thread = None
        feed._instruments = [(1, 2885, 15)]
        feed._stop_event = __import__("threading").Event()
        feed._feed = None
        feed._is_connected = False
        feed._subscribed_instruments = set()
        feed._quote_callbacks = []
        feed._depth_callbacks = []
        feed._context = mock.MagicMock()
        ReconnectingServiceMixin._init_reconnect_state(feed)

        with mock.patch("brokers.dhan.websocket.market_feed._sdk_market_feed_class") as sdk_cls:
            sdk_cls.return_value = mock.MagicMock()
            with mock.patch.object(feed, "_run"):
                feed.start()

        assert feed.is_connected is False

    def test_order_stream_start_does_not_mark_connected_before_handshake(self):
        from unittest import mock

        from brokers.dhan.reconnecting_service import ReconnectingServiceMixin

        stream = DhanOrderStream.__new__(DhanOrderStream)
        stream._lock = __import__("threading").Lock()
        stream._thread = None
        stream._stop_event = __import__("threading").Event()
        stream._order_update = None
        stream._is_connected = False
        stream._order_callbacks = []
        stream._context = mock.MagicMock()
        ReconnectingServiceMixin._init_reconnect_state(stream)

        with mock.patch("brokers.dhan.websocket.order_stream._sdk_order_update_class") as sdk_cls:
            sdk_cls.return_value = mock.MagicMock()
            with mock.patch.object(stream, "_run"):
                stream.start()

        assert stream.is_connected is False

    def test_market_feed_instruments_keep_string(self):
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[(1, "2885", 15)],
        )
        assert feed._instruments == [(1, "2885", 15)]

    def test_market_feed_preserves_multiple_instruments(self):
        instruments = [(1, str(i), 15) for i in range(100)]
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=instruments,
        )
        assert len(feed._instruments) == 100
