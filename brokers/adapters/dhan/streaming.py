"""Dhan streaming adapter — real-time market data via WebSocket.

Uses sync threading (websocket-client library) for the WebSocket connection.
Runs the WebSocket in a background daemon thread.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from decimal import Decimal
from typing import Callable

import websocket

from brokers.adapters.dhan.config import EXCHANGE_MAP

logger = logging.getLogger(__name__)

WS_URL = "wss://api.dhan.co/v2/ws/feed"
TickCallback = Callable[[dict], None]


class DhanStreaming:
    """Real-time market data streaming via Dhan WebSocket.

    Usage::

        streaming = DhanStreaming(access_token="...", client_id="...")
        streaming.on_tick = lambda tick: print(tick)
        streaming.subscribe("RELIANCE", "NSE")
        streaming.start()
        # ... later
        streaming.stop()
    """

    def __init__(
        self,
        access_token: str,
        client_id: str,
        ws_url: str = WS_URL,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
    ):
        self._access_token = access_token
        self._client_id = client_id
        self._ws_url = ws_url
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay

        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

        self._subscriptions: set[str] = set()
        self._on_tick: TickCallback | None = None
        self._on_connect: Callable[[], None] | None = None
        self._on_disconnect: Callable[[], None] | None = None

    @property
    def on_tick(self) -> TickCallback | None:
        return self._on_tick

    @on_tick.setter
    def on_tick(self, callback: TickCallback | None) -> None:
        self._on_tick = callback

    @property
    def on_connect(self) -> Callable[[], None] | None:
        return self._on_connect

    @on_connect.setter
    def on_connect(self, callback: Callable[[], None] | None) -> None:
        self._on_connect = callback

    @property
    def on_disconnect(self) -> Callable[[], None] | None:
        return self._on_disconnect

    @on_disconnect.setter
    def on_disconnect(self, callback: Callable[[], None] | None) -> None:
        self._on_disconnect = callback

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._running

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        segment = EXCHANGE_MAP.get(exchange.upper(), exchange)
        key = f"{segment}|{symbol}"
        with self._lock:
            self._subscriptions.add(key)
        if self._ws and self._running:
            self._send_subscribe([key])

    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        segment = EXCHANGE_MAP.get(exchange.upper(), exchange)
        key = f"{segment}|{symbol}"
        with self._lock:
            self._subscriptions.discard(key)
        if self._ws and self._running:
            self._send_unsubscribe([key])

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._ws:
            self._ws.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._ws = None
        self._thread = None

    def _run(self) -> None:
        delay = self._reconnect_delay
        while self._running:
            self._ws = websocket.WebSocketApp(
                self._ws_url,
                header={
                    "access-token": self._access_token,
                    "client-id": self._client_id,
                },
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self._ws.run_forever(ping_interval=30, ping_timeout=10)
            if self._running:
                logger.warning("dhan_ws_reconnecting", extra={"delay": delay})
                time.sleep(delay)
                delay = min(delay * 2, self._max_reconnect_delay)

    def _on_open(self, ws) -> None:
        logger.info("dhan_ws_connected")
        if self._on_connect:
            self._on_connect()
        with self._lock:
            subs = list(self._subscriptions)
        if subs:
            self._send_subscribe(subs)

    def _on_message(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return
        tick = self._parse_tick(data)
        if tick and self._on_tick:
            self._on_tick(tick)

    def _on_error(self, ws, error) -> None:
        logger.warning("dhan_ws_error", extra={"error": str(error)})

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        logger.info("dhan_ws_disconnected")
        if self._on_disconnect:
            self._on_disconnect()

    def _send_subscribe(self, keys: list[str]) -> None:
        if not self._ws:
            return
        msg = json.dumps(
            {
                "type": "subscribe",
                "instrumentKeys": keys,
            }
        )
        self._ws.send(msg)

    def _send_unsubscribe(self, keys: list[str]) -> None:
        if not self._ws:
            return
        msg = json.dumps(
            {
                "type": "unsubscribe",
                "instrumentKeys": keys,
            }
        )
        self._ws.send(msg)

    @staticmethod
    def _parse_tick(data: dict) -> dict | None:
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
