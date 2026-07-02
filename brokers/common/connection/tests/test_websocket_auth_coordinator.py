"""Regression tests for WebSocket re-auth after token refresh."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.common.connection.websocket_auth_coordinator import WebSocketAuthCoordinator


def _make_feed20():
    from brokers.dhan.depth_20 import DhanDepth20Feed

    return DhanDepth20Feed("test_client", "old_token")


def _make_feed200():
    from brokers.dhan.depth_200 import DhanDepth200Feed

    return DhanDepth200Feed("test_client", "old_token")


class TestDepthFeedTokenReconnect:
    def test_update_token_closes_active_websocket(self):
        feed = _make_feed20()
        mock_ws = MagicMock()
        feed._ws = mock_ws

        feed.update_token("fresh_token")

        assert feed._access_token == "fresh_token"
        mock_ws.close.assert_called_once()

    def test_update_token_same_value_is_noop(self):
        feed = _make_feed20()
        mock_ws = MagicMock()
        feed._ws = mock_ws
        feed._access_token = "unchanged"

        feed.update_token("unchanged")

        mock_ws.close.assert_not_called()

    def test_update_token_empty_string_is_noop(self):
        feed = _make_feed20()
        mock_ws = MagicMock()
        feed._ws = mock_ws

        feed.update_token("")

        mock_ws.close.assert_not_called()

    def test_request_auth_reconnect_without_socket_is_safe(self):
        feed = _make_feed20()
        feed._ws = None
        feed.request_auth_reconnect()

    def test_depth_200_feed_reconnects_on_token_change(self):
        feed = _make_feed200()
        mock_ws = MagicMock()
        feed._ws = mock_ws

        feed.update_token("new_depth_200_token")

        assert feed._access_token == "new_depth_200_token"
        mock_ws.close.assert_called_once()


class TestWebSocketAuthCoordinator:
    def test_notify_depth_feeds_updates_both_feeds(self):
        feed20 = _make_feed20()
        feed200 = _make_feed200()
        ws20 = MagicMock()
        ws200 = MagicMock()
        feed20._ws = ws20
        feed200._ws = ws200

        class _Conn:
            depth_20_feed = feed20
            depth_200_feed = feed200

        count = WebSocketAuthCoordinator.notify_depth_feeds(_Conn(), "broadcast_token")

        assert count == 2
        assert feed20._access_token == "broadcast_token"
        assert feed200._access_token == "broadcast_token"
        ws20.close.assert_called()
        ws200.close.assert_called()

    def test_request_reconnect_on_token_change_without_hooks_is_safe(self):
        bare = object()
        WebSocketAuthCoordinator.request_reconnect_on_token_change(bare, "token")

    def test_notify_depth_feeds_skips_missing_attributes(self):
        conn = MagicMock(spec=[])
        assert WebSocketAuthCoordinator.notify_depth_feeds(conn, "token") == 0
