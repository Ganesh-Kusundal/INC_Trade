"""Unit tests for Upstox portfolio WebSocket stream."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from brokers.adapters.upstox.portfolio_stream import UpstoxPortfolioStream


class TestUpstoxPortfolioStream:
    def setup_method(self):
        self.authorizer = MagicMock()
        self.token_provider = MagicMock(return_value="test-token")
        self.stream = UpstoxPortfolioStream(
            feed_authorizer=self.authorizer,
            token_provider=self.token_provider,
        )

    def test_initial_state(self):
        assert self.stream.is_connected is False
        assert self.stream._listeners == []
        assert self.stream._runner is None

    def test_add_listener(self):
        listener = MagicMock()
        self.stream.add_listener(listener)
        assert listener in self.stream._listeners

    def test_remove_listener(self):
        listener = MagicMock()
        self.stream.add_listener(listener)
        self.stream.remove_listener(listener)
        assert listener not in self.stream._listeners

    def test_remove_nonexistent_listener(self):
        listener = MagicMock()
        self.stream.remove_listener(listener)
        assert listener not in self.stream._listeners

    @patch("brokers.adapters.upstox.portfolio_stream.ReconnectingWebSocketRunner")
    def test_start_creates_runner(self, mock_runner_cls):
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        self.stream.start()
        mock_runner.start.assert_called_once()
        assert self.stream._runner is mock_runner

    @patch("brokers.adapters.upstox.portfolio_stream.ReconnectingWebSocketRunner")
    def test_start_noop_if_already_running(self, mock_runner_cls):
        mock_runner = MagicMock()
        mock_runner.is_running = True
        self.stream._runner = mock_runner
        self.stream.start()
        mock_runner_cls.assert_not_called()

    def test_stop_sets_runner_none(self):
        mock_runner = MagicMock()
        self.stream._runner = mock_runner
        self.stream.stop()
        mock_runner.stop.assert_called_once()
        assert self.stream._runner is None
        assert self.stream.is_connected is False

    def test_stop_when_no_runner(self):
        self.stream._runner = None
        self.stream.stop()
        assert self.stream.is_connected is False

    def test_on_message_json(self):
        listener = MagicMock()
        self.stream.add_listener(listener)
        msg = json.dumps({"update_type": "order_update", "order_id": "123"})
        self.stream._on_message(None, msg)
        listener.assert_called_once_with("order_update", {"update_type": "order_update", "order_id": "123"})

    def test_on_message_bytes(self):
        listener = MagicMock()
        self.stream.add_listener(listener)
        msg = json.dumps({"type": "position_update"}).encode("utf-8")
        self.stream._on_message(None, msg)
        listener.assert_called_once_with("position_update", {"type": "position_update"})

    def test_on_message_invalid_json_no_crash(self):
        listener = MagicMock()
        self.stream.add_listener(listener)
        self.stream._on_message(None, "not valid json {{{")
        listener.assert_not_called()

    def test_on_message_listener_error_does_not_crash(self):
        bad_listener = MagicMock(side_effect=RuntimeError("boom"))
        good_listener = MagicMock()
        self.stream.add_listener(bad_listener)
        self.stream.add_listener(good_listener)
        msg = json.dumps({"update_type": "test"})
        self.stream._on_message(None, msg)
        good_listener.assert_called_once_with("test", {"update_type": "test"})

    def test_on_message_fallback_type_field(self):
        listener = MagicMock()
        self.stream.add_listener(listener)
        msg = json.dumps({"type": "holdings_update"})
        self.stream._on_message(None, msg)
        listener.assert_called_once_with("holdings_update", {"type": "holdings_update"})

    def test_on_message_unknown_when_no_type(self):
        listener = MagicMock()
        self.stream.add_listener(listener)
        msg = json.dumps({"data": "something"})
        self.stream._on_message(None, msg)
        listener.assert_called_once_with("unknown", {"data": "something"})

    def test_update_access_token(self):
        self.stream.update_access_token("new-token")
        token = self.stream._token_provider()
        assert token == "new-token"

    def test_resolve_headers_uses_token_provider(self):
        headers = self.stream._resolve_headers()
        assert headers == {"Authorization": "Bearer test-token"}

    def test_resolve_url_uses_authorizer(self):
        self.authorizer.authorize_portfolio_stream.return_value = "wss://example.com/ws"
        url = self.stream._resolve_url()
        assert url == "wss://example.com/ws"

    def test_resolve_url_empty_raises(self):
        self.authorizer.authorize_portfolio_stream.return_value = ""
        try:
            self.stream._resolve_url()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass

    def test_on_open_sets_connected(self):
        self.stream._on_open(None)
        assert self.stream.is_connected is True

    def test_on_close_sets_disconnected(self):
        self.stream._on_close(None, 1000, "")
        assert self.stream.is_connected is False
