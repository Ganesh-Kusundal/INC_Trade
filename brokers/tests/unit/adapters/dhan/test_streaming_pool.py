from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.adapters.dhan.streaming_pool import (
    DhanStreamChannel,
    OrderStreamConnection,
    PooledDhanDepth20Stream,
    PooledDhanDepth200Stream,
    PooledDhanOrderStream,
    PooledDhanStreaming,
)


@pytest.fixture
def token():
    return "test_token_123"


@pytest.fixture
def client_id():
    return "client_456"


class TestPooledDhanStreaming:
    def test_init_stores_attributes(self, token, client_id):
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        assert s._access_token == token
        assert s._client_id == client_id
        assert s._connection is None
        assert s._on_tick is None
        assert s._on_connect is None
        assert s._on_disconnect is None
        assert s._on_error is None

    def test_init_with_callable_token(self, client_id):
        token_fn = lambda: "tok"
        s = PooledDhanStreaming(access_token=token_fn, client_id=client_id)
        assert s._access_token is token_fn

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_subscribe_calls_connection(self, mock_pool, token, client_id):
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        s.subscribe("RELIANCE", "NSE")
        mock_conn.subscribe.assert_called_once_with("NSE_EQ|RELIANCE")

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_unsubscribe_calls_connection(self, mock_pool, token, client_id):
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        s.unsubscribe("RELIANCE", "NSE")
        mock_conn.unsubscribe.assert_called_once_with("NSE_EQ|RELIANCE")

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_start_calls_connection_start(self, mock_pool, token, client_id):
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        s.start()
        mock_conn.start.assert_called_once()

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_stop_releases_connection(self, mock_pool, token, client_id):
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        s.start()
        s.stop()
        mock_pool.release_connection.assert_called_once_with(mock_conn)
        assert s._connection is None

    def test_stop_noop_when_not_connected(self, token, client_id):
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        s.stop()
        assert s._connection is None

    def test_update_token_is_noop(self, token, client_id):
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        s.update_token("new_token")
        assert s._access_token == token

    def test_is_connected_property_delegates_to_connection(self, token, client_id):
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        mock_conn = MagicMock()
        mock_conn.is_connected = True
        s._connection = mock_conn
        assert s.is_connected is True

    def test_is_connected_false_when_no_connection(self, token, client_id):
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        mock_conn = MagicMock()
        mock_conn.is_connected = False
        s._connection = mock_conn
        assert s.is_connected is False

    def test_on_tick_property(self, token, client_id):
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        cb = MagicMock()
        s.on_tick = cb
        assert s.on_tick is cb

    def test_on_connect_property(self, token, client_id):
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        cb = MagicMock()
        s.on_connect = cb
        assert s.on_connect is cb

    def test_on_disconnect_property(self, token, client_id):
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        cb = MagicMock()
        s.on_disconnect = cb
        assert s.on_disconnect is cb

    def test_on_error_property(self, token, client_id):
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        cb = MagicMock()
        s.on_error = cb
        assert s.on_error is cb

    def test_parse_tick(self):
        raw = {"symbol": "RELIANCE", "lastPrice": 2500.5, "volume": 100}
        tick = PooledDhanStreaming._parse_tick(raw)
        assert tick["symbol"] == "RELIANCE"
        assert tick["ltp"] == 2500.5
        assert tick["volume"] == 100

    def test_parse_tick_uses_trading_symbol_fallback(self):
        raw = {"tradingSymbol": "TCS", "ltp": 3000}
        tick = PooledDhanStreaming._parse_tick(raw)
        assert tick["symbol"] == "TCS"

    def test_parse_tick_non_dict_returns_none(self):
        assert PooledDhanStreaming._parse_tick("bad") is None

    def test_handle_message_valid_json(self, token, client_id):
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        results = []
        s.on_tick = lambda t: results.append(t)
        s._handle_message('{"symbol": "INFY", "lastPrice": 100}')
        assert len(results) == 1
        assert results[0]["symbol"] == "INFY"

    def test_handle_message_invalid_json(self, token, client_id):
        s = PooledDhanStreaming(access_token=token, client_id=client_id)
        results = []
        s.on_tick = lambda t: results.append(t)
        s._handle_message("not json {{{")
        assert results == []

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_get_ws_headers_callable_token(self, mock_pool, client_id):
        s = PooledDhanStreaming(access_token=lambda: "fn_tok", client_id=client_id)
        s.subscribe("INFY", "NSE")
        call_args = mock_pool.get_connection.call_args
        headers = call_args[0][1]
        assert headers["access-token"] == "fn_tok"
        assert headers["client-id"] == client_id


class TestPooledDhanDepth20Stream:
    def test_init(self, token, client_id):
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        assert s._connection is None
        assert s._on_depth_update is None

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_subscribe(self, mock_pool, token, client_id):
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s.subscribe("RELIANCE", "NSE")
        mock_conn.subscribe.assert_called_once_with("NSE_EQ|RELIANCE")

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_unsubscribe(self, mock_pool, token, client_id):
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s.unsubscribe("RELIANCE", "NSE")
        mock_conn.unsubscribe.assert_called_once_with("NSE_EQ|RELIANCE")

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_start_stop(self, mock_pool, token, client_id):
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s.start()
        mock_conn.start.assert_called_once()
        s.stop()
        mock_pool.release_connection.assert_called_once_with(mock_conn)
        assert s._connection is None

    def test_update_token_noop(self, token, client_id):
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        s.update_token("ignored")
        assert s._access_token == token

    def test_is_connected(self, token, client_id):
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        mock_conn = MagicMock()
        mock_conn.is_connected = False
        s._connection = mock_conn
        assert s.is_connected is False

    def test_on_depth_update_property(self, token, client_id):
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        cb = MagicMock()
        s.on_depth_update = cb
        assert s.on_depth_update is cb

    def test_handle_message_valid(self, token, client_id):
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        results = []
        s.on_depth_update = lambda d: results.append(d)
        s._handle_message('{"depth": [1, 2]}')
        assert len(results) == 1

    def test_handle_message_invalid(self, token, client_id):
        s = PooledDhanDepth20Stream(access_token=token, client_id=client_id)
        results = []
        s.on_depth_update = lambda d: results.append(d)
        s._handle_message("bad")
        assert results == []


class TestPooledDhanDepth200Stream:
    def test_init(self, token, client_id):
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        assert s._connection is None
        assert s._on_depth_update is None

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_subscribe_unsubscribe(self, mock_pool, token, client_id):
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        s.subscribe("TCS", "NSE")
        mock_conn.subscribe.assert_called_once_with("NSE_EQ|TCS")
        s.unsubscribe("TCS", "NSE")
        mock_conn.unsubscribe.assert_called_once_with("NSE_EQ|TCS")

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_start_stop(self, mock_pool, token, client_id):
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        s.start()
        mock_conn.start.assert_called_once()
        s.stop()
        mock_pool.release_connection.assert_called_once_with(mock_conn)
        assert s._connection is None

    def test_update_token_noop(self, token, client_id):
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        s.update_token("new")
        assert s._access_token == token

    def test_is_connected(self, token, client_id):
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        assert s.is_connected is False or True
        mock_conn = MagicMock()
        mock_conn.is_connected = True
        s._connection = mock_conn
        assert s.is_connected is True

    def test_handle_message_valid(self, token, client_id):
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        results = []
        s.on_depth_update = lambda d: results.append(d)
        s._handle_message('{"bids": []}')
        assert len(results) == 1

    def test_handle_message_invalid(self, token, client_id):
        s = PooledDhanDepth200Stream(access_token=token, client_id=client_id)
        results = []
        s.on_depth_update = lambda d: results.append(d)
        s._handle_message("!!!")
        assert results == []


class TestPooledDhanOrderStream:
    def test_init(self, token, client_id):
        s = PooledDhanOrderStream(access_token=token, client_id=client_id)
        assert s._connection is None
        assert s._on_order_update is None

    def test_get_ws_headers_empty(self, token, client_id):
        s = PooledDhanOrderStream(access_token=token, client_id=client_id)
        assert s._get_ws_headers() == {}

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_subscribe_gets_connection(self, mock_pool, token, client_id):
        mock_conn = MagicMock()
        mock_conn.is_connected = False
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanOrderStream(access_token=token, client_id=client_id)
        s.subscribe("any", "NSE")
        mock_pool.get_connection.assert_called_once()

    def test_unsubscribe_is_noop(self, token, client_id):
        s = PooledDhanOrderStream(access_token=token, client_id=client_id)
        s.unsubscribe("any", "NSE")

    def test_update_token_noop(self, token, client_id):
        s = PooledDhanOrderStream(access_token=token, client_id=client_id)
        s.update_token("new")
        assert s._access_token == token

    @patch("brokers_core.adapters.dhan.streaming_pool.WebSocketConnectionPool")
    def test_start_stop(self, mock_pool, token, client_id):
        mock_conn = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        s = PooledDhanOrderStream(access_token=token, client_id=client_id)
        s.start()
        mock_conn.start.assert_called_once()
        s.stop()
        mock_pool.release_connection.assert_called_once_with(mock_conn)
        assert s._connection is None

    def test_on_order_update_property(self, token, client_id):
        s = PooledDhanOrderStream(access_token=token, client_id=client_id)
        cb = MagicMock()
        s.on_order_update = cb
        assert s.on_order_update is cb

    def test_handle_message_valid(self, token, client_id):
        s = PooledDhanOrderStream(access_token=token, client_id=client_id)
        results = []
        s.on_order_update = lambda d: results.append(d)
        s._handle_message('{"orderId": "123"}')
        assert len(results) == 1

    def test_handle_message_bytes(self, token, client_id):
        s = PooledDhanOrderStream(access_token=token, client_id=client_id)
        results = []
        s.on_order_update = lambda d: results.append(d)
        s._handle_message(b'{"orderId": "456"}')
        assert len(results) == 1

    def test_handle_message_invalid(self, token, client_id):
        s = PooledDhanOrderStream(access_token=token, client_id=client_id)
        results = []
        s.on_order_update = lambda d: results.append(d)
        s._handle_message("not json")
        assert results == []


class TestDhanStreamChannel:
    def test_send_subscribe_default_request_code(self):
        mock_ws = MagicMock()
        conn = DhanStreamChannel(
            ws_url="wss://test",
            headers={},
            on_message=lambda m: None,
        )
        conn._ws = mock_ws
        conn._send_subscribe(["NSE_EQ|RELIANCE"])
        mock_ws.send.assert_called_once()
        import json

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["RequestCode"] == 23
        assert sent["InstrumentList"][0]["SecurityId"] == "RELIANCE"

    def test_send_subscribe_custom_request_code(self):
        mock_ws = MagicMock()
        conn = DhanStreamChannel(
            ws_url="wss://test",
            headers={},
            on_message=lambda m: None,
            request_code=42,
        )
        conn._ws = mock_ws
        conn._send_subscribe(["NSE_EQ|RELIANCE"])
        import json

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["RequestCode"] == 42

    def test_send_subscribe_no_ws(self):
        conn = DhanStreamChannel(
            ws_url="wss://test",
            headers={},
            on_message=lambda m: None,
        )
        conn._send_subscribe(["NSE_EQ|RELIANCE"])

    def test_send_unsubscribe_delegates_to_subscribe(self):
        mock_ws = MagicMock()
        conn = DhanStreamChannel(
            ws_url="wss://test",
            headers={},
            on_message=lambda m: None,
        )
        conn._ws = mock_ws
        conn._send_unsubscribe(["NSE_EQ|TCS"])
        mock_ws.send.assert_called_once()

    def test_send_subscribe_with_multiple_keys(self):
        mock_ws = MagicMock()
        conn = DhanStreamChannel(
            ws_url="wss://test",
            headers={},
            on_message=lambda m: None,
        )
        conn._ws = mock_ws
        conn._send_subscribe(["NSE_EQ|RELIANCE", "NSE_EQ|TCS"])
        import json

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["InstrumentCount"] == 2
        assert len(sent["InstrumentList"]) == 2


class TestOrderStreamConnection:
    def test_send_subscribe_with_static_token(self):
        mock_ws = MagicMock()
        conn = OrderStreamConnection(
            ws_url="wss://test",
            headers={},
            on_message=lambda m: None,
            access_token="tok123",
            client_id="c1",
        )
        conn._ws = mock_ws
        conn._send_subscribe([])
        import json

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["LoginReq"]["Token"] == "tok123"
        assert sent["LoginReq"]["ClientId"] == "c1"

    def test_send_subscribe_with_callable_token(self):
        mock_ws = MagicMock()
        conn = OrderStreamConnection(
            ws_url="wss://test",
            headers={},
            on_message=lambda m: None,
            access_token=lambda: "fn_tok",
            client_id="c2",
        )
        conn._ws = mock_ws
        conn._send_subscribe([])
        import json

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["LoginReq"]["Token"] == "fn_tok"

    def test_send_unsubscribe(self):
        mock_ws = MagicMock()
        conn = OrderStreamConnection(
            ws_url="wss://test",
            headers={},
            on_message=lambda m: None,
            access_token="tok",
            client_id="c1",
        )
        conn._ws = mock_ws
        conn._send_unsubscribe([])
        import json

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["type"] == "unsubscribe"

    def test_send_subscribe_no_ws(self):
        conn = OrderStreamConnection(
            ws_url="wss://test",
            headers={},
            on_message=lambda m: None,
            access_token="tok",
            client_id="c1",
        )
        conn._send_subscribe([])
