"""Dhan streaming with connection pooling — uses global WebSocket pool."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from inc_trade.infrastructure.websocket_pool import (
    WebSocketConnection,
    WebSocketConnectionPool,
)

from brokers.adapters.dhan.segments import resolve_segment

logger = logging.getLogger(__name__)

# WebSocket URLs
WS_FEED_URL = "wss://api.dhan.co/v2/ws/feed"
WS_DEPTH20_URL = "wss://depth-api-feed.dhan.co/twentydepth"
WS_DEPTH200_URL = "wss://full-depth-api.dhan.co/twohundreddepth"
WS_ORDER_URL = "wss://api-order-update.dhan.co"


class DhanStreamChannel(WebSocketConnection):
    """Parameterized Dhan WebSocket channel — replaces the near-identical
    Depth20Connection and Depth200Connection classes.

    Usage:
        depth20 = DhanStreamChannel(
            ws_url=WS_DEPTH20_URL,
            headers=headers,
            on_message=on_depth20,
            request_code=23,
        )
    """

    def __init__(self, *args: Any, request_code: int = 23, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._request_code = request_code

    def _send_subscribe(self, keys: list[str]) -> None:
        instrument_list = []
        for key in keys:
            parts = key.split("|")
            if len(parts) == 2:
                instrument_list.append({"ExchangeSegment": parts[0], "SecurityId": parts[1]})
        if self._ws and instrument_list:
            msg = json.dumps(
                {
                    "RequestCode": self._request_code,
                    "InstrumentCount": len(instrument_list),
                    "InstrumentList": instrument_list,
                }
            )
            self._ws.send(msg)

    def _send_unsubscribe(self, keys: list[str]) -> None:
        self._send_subscribe(keys)


Depth20Connection = DhanStreamChannel  # backward compat
Depth200Connection = DhanStreamChannel  # backward compat


class OrderStreamConnection(WebSocketConnection):
    """Custom connection class for order stream format."""

    def __init__(
        self,
        ws_url: str,
        headers: dict[str, str],
        on_message: Callable[[str], None],
        on_open: Callable[[], None] | None = None,
        on_close: Callable[[int, str], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
        *,
        access_token: str | Callable[[], str] = "",
        client_id: str = "",
    ) -> None:
        super().__init__(
            ws_url,
            headers,
            on_message,
            on_open,
            on_close,
            on_error,
            reconnect_delay,
            max_reconnect_delay,
        )
        self._access_token = access_token
        self._client_id = client_id

    def _send_subscribe(self, keys: list[str]) -> None:
        access_token = self._access_token() if callable(self._access_token) else self._access_token
        if self._ws:
            msg = json.dumps(
                {
                    "LoginReq": {
                        "MsgCode": 42,
                        "ClientId": self._client_id,
                        "Token": access_token,
                    },
                    "UserType": "SELF",
                }
            )
            self._ws.send(msg)

    def _send_unsubscribe(self, keys: list[str]) -> None:
        if self._ws:
            msg = json.dumps({"type": "unsubscribe", "channel": "orders"})
            self._ws.send(msg)


class PooledDhanStreaming:
    """Dhan market data streaming using connection pool."""

    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
    ) -> None:
        self._access_token = access_token
        self._client_id = client_id
        self._connection: WebSocketConnection | None = None
        self._on_tick: Callable[[dict[str, Any]], None] | None = None
        self._on_connect: Callable[[], None] | None = None
        self._on_disconnect: Callable[[int, str], None] | None = None
        self._on_error: Callable[[Exception], None] | None = None

    def _get_ws_headers(self) -> dict[str, str]:
        """Get WebSocket connection headers."""
        access_token = self._access_token() if callable(self._access_token) else self._access_token
        return {
            "access-token": access_token,
            "client-id": self._client_id,
        }

    def _get_connection(self) -> WebSocketConnection:
        """Get pooled connection."""
        if self._connection is None:
            headers = self._get_ws_headers()

            def on_message(message: str) -> None:
                self._handle_message(message)

            self._connection = WebSocketConnectionPool.get_connection(
                WS_FEED_URL,
                headers,
                on_message,
                on_open=self._on_connect,
                on_close=self._on_disconnect,
                on_error=self._on_error,
            )
        return self._connection

    def _handle_message(self, message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return

        tick = self._parse_tick(data)
        if tick and self._on_tick:
            self._on_tick(tick)

    @staticmethod
    def _parse_tick(data: dict[str, Any]) -> dict[str, Any] | None:
        """Parse raw tick data."""
        if not isinstance(data, dict):
            return None
        return {
            "symbol": data.get("symbol", data.get("tradingSymbol", "")),
            "exchange": data.get("exchange", ""),
            "ltp": Decimal(str(data.get("lastPrice", data.get("ltp", 0)))),
            "volume": int(data.get("volume", 0)),
            "timestamp": data.get("timestamp", ""),
            "raw": data,
        }

    @property
    def on_tick(self) -> Callable[[dict[str, Any]], None] | None:
        return self._on_tick

    @on_tick.setter
    def on_tick(self, callback: Callable[[dict[str, Any]], None] | None) -> None:
        self._on_tick = callback

    @property
    def on_connect(self) -> Callable[[], None] | None:
        return self._on_connect

    @on_connect.setter
    def on_connect(self, callback: Callable[[], None] | None) -> None:
        self._on_connect = callback

    @property
    def on_disconnect(self) -> Callable[[int, str], None] | None:
        return self._on_disconnect

    @on_disconnect.setter
    def on_disconnect(self, callback: Callable[[int, str], None] | None) -> None:
        self._on_disconnect = callback

    @property
    def on_error(self) -> Callable[[Exception], None] | None:
        return self._on_error

    @on_error.setter
    def on_error(self, callback: Callable[[Exception], None] | None) -> None:
        self._on_error = callback

    @property
    def is_connected(self) -> bool:
        """Check if connected to WebSocket."""
        conn = self._get_connection()
        return conn.is_connected

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Subscribe to symbol."""
        segment = resolve_segment(exchange)
        key = f"{segment}|{symbol}"
        conn = self._get_connection()
        conn.subscribe(key)

    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Unsubscribe from symbol."""
        segment = resolve_segment(exchange)
        key = f"{segment}|{symbol}"
        conn = self._get_connection()
        conn.unsubscribe(key)

    def update_token(self, new_token: str) -> None:
        """Update access token."""
        # Token updates are handled by the connection pool automatically
        # through the callable access_token pattern
        pass

    def start(self) -> None:
        """Start WebSocket connection."""
        conn = self._get_connection()
        conn.start()

    def stop(self) -> None:
        """Stop WebSocket connection."""
        if self._connection:
            WebSocketConnectionPool.release_connection(self._connection)
            self._connection = None


class _PooledDhanStreamBase:
    """Base class for pooled Dhan streaming channels (depth / order).

    Consolidates the common logic of ``PooledDhanDepth20Stream`` and
    ``PooledDhanDepth200Stream``, which are identical except for the
    WebSocket URL.
    """

    WS_URL: str = ""
    REQUEST_CODE: int = 23

    def __init__(
        self,
        ws_url: str,
        access_token: str | Callable[[], str],
        client_id: str,
    ) -> None:
        self._ws_url = ws_url
        self._access_token = access_token
        self._client_id = client_id
        self._connection: WebSocketConnection | None = None
        self._on_depth_update: Callable[[dict[str, Any]], None] | None = None

    def _get_ws_headers(self) -> dict[str, str]:
        """Get WebSocket connection headers."""
        access_token = self._access_token() if callable(self._access_token) else self._access_token
        return {
            "access-token": access_token,
            "client-id": self._client_id,
        }

    def _get_connection(self) -> WebSocketConnection:
        """Get pooled connection."""
        if self._connection is None:
            headers = self._get_ws_headers()

            def on_message(message: str) -> None:
                self._handle_message(message)

            self._connection = WebSocketConnectionPool.get_connection(
                self._ws_url,
                headers,
                on_message,
                connection_factory=lambda *a, **kw: DhanStreamChannel(
                    *a, request_code=self.REQUEST_CODE, **kw
                ),
            )
        return self._connection

    def _handle_message(self, message: str) -> None:
        """Handle incoming depth update message."""
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return

        if self._on_depth_update:
            self._on_depth_update(data)

    @property
    def on_depth_update(self) -> Callable[[dict[str, Any]], None] | None:
        return self._on_depth_update

    @on_depth_update.setter
    def on_depth_update(self, callback: Callable[[dict[str, Any]], None] | None) -> None:
        self._on_depth_update = callback

    @property
    def is_connected(self) -> bool:
        """Check if connected to WebSocket."""
        if self._connection is None:
            return False
        return self._connection.is_connected

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Subscribe to symbol (delegates to _PooledDhanStreamBase stub)."""
        # Subclasses may override for broker-specific subscribe logic
        _ = symbol, exchange

    def close(self) -> None:
        """Close WebSocket connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None


class PooledDhanDepth20Stream(_PooledDhanStreamBase):
    """Dhan Depth 20 streaming using connection pool."""

    WS_URL = WS_DEPTH20_URL
    REQUEST_CODE = 23

    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
    ) -> None:
        super().__init__(WS_DEPTH20_URL, access_token, client_id)

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Subscribe to symbol."""
        segment = resolve_segment(exchange)
        key = f"{segment}|{symbol}"
        conn = self._get_connection()
        conn.subscribe(key)

    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Unsubscribe from symbol."""
        segment = resolve_segment(exchange)
        key = f"{segment}|{symbol}"
        conn = self._get_connection()
        conn.unsubscribe(key)

    def update_token(self, new_token: str) -> None:
        """Update access token."""
        pass  # Handled by callable pattern

    def start(self) -> None:
        """Start WebSocket connection."""
        conn = self._get_connection()
        conn.start()

    def stop(self) -> None:
        """Stop WebSocket connection."""
        if self._connection:
            WebSocketConnectionPool.release_connection(self._connection)
            self._connection = None


class PooledDhanDepth200Stream(_PooledDhanStreamBase):
    """Dhan Depth 200 streaming using connection pool."""

    WS_URL = WS_DEPTH200_URL
    REQUEST_CODE = 23

    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
    ) -> None:
        super().__init__(WS_DEPTH200_URL, access_token, client_id)

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Subscribe to symbol."""
        segment = resolve_segment(exchange)
        key = f"{segment}|{symbol}"
        conn = self._get_connection()
        conn.subscribe(key)

    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Unsubscribe from symbol."""
        segment = resolve_segment(exchange)
        key = f"{segment}|{symbol}"
        conn = self._get_connection()
        conn.unsubscribe(key)

    def update_token(self, new_token: str) -> None:
        """Update access token."""
        pass  # Handled by callable pattern

    def start(self) -> None:
        """Start WebSocket connection."""
        conn = self._get_connection()
        conn.start()

    def stop(self) -> None:
        """Stop WebSocket connection."""
        if self._connection:
            WebSocketConnectionPool.release_connection(self._connection)
            self._connection = None


class PooledDhanOrderStream:
    """Dhan order stream using connection pool."""

    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
    ) -> None:
        self._access_token = access_token
        self._client_id = client_id
        self._connection: WebSocketConnection | None = None
        self._on_order_update: Callable[[dict[str, Any]], None] | None = None

    def _get_ws_headers(self) -> dict[str, str]:
        """Get WebSocket connection headers."""
        # Order stream uses different auth mechanism
        return {}

    def _get_connection(self) -> WebSocketConnection:
        """Get pooled connection."""
        if self._connection is None:
            headers = self._get_ws_headers()

            def on_message(message: str) -> None:
                self._handle_message(message)

            def _factory(
                ws_url: str,
                hdrs: dict[str, str],
                msg_handler: Callable[[str], None],
                on_open: Callable[[], None] | None = None,
                on_close: Callable[[int, str], None] | None = None,
                on_error: Callable[[Exception], None] | None = None,
                reconnect_delay: float = 5.0,
                max_reconnect_delay: float = 60.0,
            ) -> OrderStreamConnection:
                return OrderStreamConnection(
                    ws_url,
                    hdrs,
                    msg_handler,
                    on_open,
                    on_close,
                    on_error,
                    reconnect_delay,
                    max_reconnect_delay,
                    access_token=self._access_token,
                    client_id=self._client_id,
                )

            self._connection = WebSocketConnectionPool.get_connection(
                WS_ORDER_URL,
                headers,
                on_message,
                connection_factory=_factory,
            )
        return self._connection

    def _handle_message(self, message: str) -> None:
        """Handle incoming order update message."""
        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return

        if self._on_order_update:
            self._on_order_update(data)

    @property
    def on_order_update(self) -> Callable[[dict[str, Any]], None] | None:
        return self._on_order_update

    @on_order_update.setter
    def on_order_update(self, callback: Callable[[dict[str, Any]], None] | None) -> None:
        self._on_order_update = callback

    @property
    def is_connected(self) -> bool:
        """Check if connected to WebSocket."""
        conn = self._get_connection()
        return conn.is_connected

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Order stream auto-subscribes on connect."""
        # Order stream doesn't need symbol subscription
        # It automatically receives all order updates
        conn = self._get_connection()
        # Ensure connection is active
        if conn.is_connected:
            # Resend auth if needed
            conn._send_subscribe([])

    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Order stream doesn't support unsubscribe."""
        # Order stream doesn't have per-symbol unsubscribe
        pass

    def update_token(self, new_token: str) -> None:
        """Update access token."""
        pass  # Handled by callable pattern

    def start(self) -> None:
        """Start WebSocket connection."""
        conn = self._get_connection()
        conn.start()

    def stop(self) -> None:
        """Stop WebSocket connection."""
        if self._connection:
            WebSocketConnectionPool.release_connection(self._connection)
            self._connection = None
