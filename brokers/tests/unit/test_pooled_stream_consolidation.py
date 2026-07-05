"""Unit tests for the _PooledDhanStreamBase consolidation.

Verifies that the refactor of PooledDhanDepth20Stream and
PooledDhanDepth200Stream into a shared base class preserves all
public API behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.adapters.dhan.streaming_pool import (
    WS_DEPTH20_URL,
    WS_DEPTH200_URL,
    PooledDhanDepth20Stream,
    PooledDhanDepth200Stream,
    _PooledDhanStreamBase,
)


@pytest.fixture
def token() -> str:
    return "test_token_123"


@pytest.fixture
def client_id() -> str:
    return "client_456"


class TestInheritanceAndClassConfig:
    """Verify base-class structure and class-level configuration."""

    def test_depth20_subclass_of_base(self) -> None:
        assert issubclass(PooledDhanDepth20Stream, _PooledDhanStreamBase)

    def test_depth200_subclass_of_base(self) -> None:
        assert issubclass(PooledDhanDepth200Stream, _PooledDhanStreamBase)

    def test_depth20_uses_correct_url(self) -> None:
        assert PooledDhanDepth20Stream.WS_URL == WS_DEPTH20_URL

    def test_depth200_uses_correct_url(self) -> None:
        assert PooledDhanDepth200Stream.WS_URL == WS_DEPTH200_URL

    def test_urls_differ_between_subclasses(self) -> None:
        assert PooledDhanDepth20Stream.WS_URL != PooledDhanDepth200Stream.WS_URL

    def test_request_code_default_is_23(self) -> None:
        assert _PooledDhanStreamBase.REQUEST_CODE == 23
        assert PooledDhanDepth20Stream.REQUEST_CODE == 23
        assert PooledDhanDepth200Stream.REQUEST_CODE == 23


class TestInit:
    def test_depth20_init_stores_attributes(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        assert s._access_token == token
        assert s._client_id == client_id
        assert s._connection is None
        assert s._on_depth_update is None

    def test_depth200_init_stores_attributes(self, token, client_id) -> None:
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        assert s._access_token == token
        assert s._client_id == client_id
        assert s._connection is None
        assert s._on_depth_update is None

    def test_init_with_callable_token(self, client_id) -> None:
        def token_fn() -> str:
            return "tok"

        s = PooledDhanDepth20Stream(access_token=token_fn, client_id=client_id)
        assert s._access_token is token_fn


class TestHeaders:
    def test_depth20_headers(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        assert s._get_ws_headers() == {
            "access-token": token,
            "client-id": client_id,
        }

    def test_depth200_headers(self, token, client_id) -> None:
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        assert s._get_ws_headers() == {
            "access-token": token,
            "client-id": client_id,
        }

    def test_callable_token_resolved_in_headers(self, client_id) -> None:
        def token_fn() -> str:
            return "fresh_tok"

        s = PooledDhanDepth20Stream(access_token=token_fn, client_id=client_id)
        headers = s._get_ws_headers()
        assert headers["access-token"] == "fresh_tok"
        assert headers["client-id"] == client_id


class TestGetConnection:
    @patch("brokers.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_depth20_uses_correct_url(self, mock_pool, token, client_id) -> None:
        mock_pool.get_connection.return_value = MagicMock()
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s._get_connection()
        # First positional arg is the URL
        args, _kwargs = mock_pool.get_connection.call_args
        assert args[0] == WS_DEPTH20_URL

    @patch("brokers.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_depth200_uses_correct_url(self, mock_pool, token, client_id) -> None:
        mock_pool.get_connection.return_value = MagicMock()
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        s._get_connection()
        args, _kwargs = mock_pool.get_connection.call_args
        assert args[0] == WS_DEPTH200_URL

    @patch("brokers.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_get_connection_reuses_cached(self, mock_pool, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s._get_connection()
        s._get_connection()
        # Should only request from pool once (cached after first call)
        assert mock_pool.get_connection.call_count == 1

    @patch("brokers.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_connection_factory_uses_request_code_23(self, mock_pool, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s._get_connection()
        _args, kwargs = mock_pool.get_connection.call_args
        factory = kwargs["connection_factory"]
        # Invoke factory like the pool would; capture what it forwards to DhanStreamChannel
        with patch("brokers.adapters.dhan.streaming_pool.DhanStreamChannel") as mock_channel:
            factory("url", {}, lambda m: None)
            mock_channel.assert_called_once()
            call_kwargs = mock_channel.call_args.kwargs
            assert call_kwargs["request_code"] == 23


class TestSubscribeUnsubscribe:
    @patch("brokers.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_depth20_subscribe_uses_segment(self, mock_pool, token, client_id) -> None:
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s.subscribe("RELIANCE", "NSE")
        mock_conn.subscribe.assert_called_once_with("NSE_EQ|RELIANCE")

    @patch("brokers.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_depth200_subscribe_uses_segment(self, mock_pool, token, client_id) -> None:
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        s.subscribe("TCS", "NSE")
        mock_conn.subscribe.assert_called_once_with("NSE_EQ|TCS")

    @patch("brokers.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_depth20_unsubscribe(self, mock_pool, token, client_id) -> None:
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s.unsubscribe("RELIANCE", "NSE")
        mock_conn.unsubscribe.assert_called_once_with("NSE_EQ|RELIANCE")

    @patch("brokers.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_depth200_unsubscribe(self, mock_pool, token, client_id) -> None:
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        s.unsubscribe("TCS", "NSE")
        mock_conn.unsubscribe.assert_called_once_with("NSE_EQ|TCS")


class TestStartStop:
    @patch("brokers.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_depth20_start_stop(self, mock_pool, token, client_id) -> None:
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s.start()
        mock_conn.start.assert_called_once()
        s.stop()
        mock_pool.release_connection.assert_called_once_with(mock_conn)
        assert s._connection is None

    @patch("brokers.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_depth200_start_stop(self, mock_pool, token, client_id) -> None:
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        s.start()
        mock_conn.start.assert_called_once()
        s.stop()
        mock_pool.release_connection.assert_called_once_with(mock_conn)
        assert s._connection is None

    def test_stop_without_connection_is_safe(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        # Should not raise even with no connection
        s.stop()
        assert s._connection is None


class TestUpdateToken:
    def test_update_token_is_noop_for_depth20(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s.update_token("new_token")
        # Callable pattern is in use; the raw token attribute is unchanged
        assert s._access_token == token

    def test_update_token_is_noop_for_depth200(self, token, client_id) -> None:
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        s.update_token("new_token")
        assert s._access_token == token


class TestIsConnected:
    def test_depth20_is_connected_false_when_disconnected(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        mock_conn = MagicMock()
        mock_conn.is_connected = False
        s._connection = mock_conn
        assert s.is_connected is False

    def test_depth20_is_connected_true(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        mock_conn = MagicMock()
        mock_conn.is_connected = True
        s._connection = mock_conn
        assert s.is_connected is True

    def test_depth200_is_connected_true(self, token, client_id) -> None:
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        mock_conn = MagicMock()
        mock_conn.is_connected = True
        s._connection = mock_conn
        assert s.is_connected is True


class TestOnDepthUpdateProperty:
    def test_depth20_getter_setter(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        cb = MagicMock()
        s.on_depth_update = cb
        assert s.on_depth_update is cb

    def test_depth200_getter_setter(self, token, client_id) -> None:
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        cb = MagicMock()
        s.on_depth_update = cb
        assert s.on_depth_update is cb

    def test_depth20_set_to_none(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s.on_depth_update = MagicMock()
        s.on_depth_update = None
        assert s.on_depth_update is None


class TestHandleMessage:
    def test_depth20_valid_json_invokes_callback(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        results: list[dict] = []
        s.on_depth_update = results.append
        s._handle_message('{"depth": [1, 2]}')
        assert results == [{"depth": [1, 2]}]

    def test_depth200_valid_json_invokes_callback(self, token, client_id) -> None:
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        results: list[dict] = []
        s.on_depth_update = results.append
        s._handle_message('{"bids": []}')
        assert results == [{"bids": []}]

    def test_depth20_invalid_json_silently_ignored(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        results: list[dict] = []
        s.on_depth_update = results.append
        s._handle_message("not json")
        assert results == []

    def test_depth200_invalid_json_silently_ignored(self, token, client_id) -> None:
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        results: list[dict] = []
        s.on_depth_update = results.append
        s._handle_message("not json")
        assert results == []

    def test_handle_message_no_callback_no_error(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        # No callback set, should not raise
        s._handle_message('{"x": 1}')


class TestPublicApiBackwardsCompat:
    """The public surface (constructor signature, public methods, properties)
    of both subclasses must match what the original duplicate classes had.
    """

    def test_depth20_has_all_public_methods(self, token, client_id) -> None:
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        for name in (
            "subscribe",
            "unsubscribe",
            "update_token",
            "start",
            "stop",
            "_get_connection",
            "_get_ws_headers",
            "_handle_message",
        ):
            assert callable(getattr(s, name)), f"missing method: {name}"
        # is_connected + on_depth_update are properties
        assert isinstance(type(s).is_connected, property)
        assert isinstance(type(s).on_depth_update, property)

    def test_depth200_has_all_public_methods(self, token, client_id) -> None:
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        for name in (
            "subscribe",
            "unsubscribe",
            "update_token",
            "start",
            "stop",
            "_get_connection",
            "_get_ws_headers",
            "_handle_message",
        ):
            assert callable(getattr(s, name)), f"missing method: {name}"
        assert isinstance(type(s).is_connected, property)
        assert isinstance(type(s).on_depth_update, property)
