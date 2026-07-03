"""Base WebSocket streaming adapter — shared boilerplate for broker streaming adapters."""

from __future__ import annotations

import json
import logging
import threading
from decimal import Decimal
from typing import Any, Callable

import websocket

from brokers.domain.entities import Quote
from brokers.infrastructure.reconnect_strategy import ReconnectStrategy
from brokers.ports.streaming import StreamHandle, StreamingPort

logger = logging.getLogger(__name__)

TickCallback = Callable[[dict], None]
ConnectCallback = Callable[[], None]
DisconnectCallback = Callable[[], None]


class BaseWebSocketStreaming(StreamingPort):
    """Base class for WebSocket streaming adapters.

    Provides common connection management, subscription tracking, and callback handling.
    Subclasses must implement:
    - _get_ws_headers() -> dict
    - _build_subscribe_message(keys: list[str]) -> str
    - _build_unsubscribe_message(keys: list[str]) -> str
    - _parse_tick(data: dict) -> dict | None
    """

    def __init__(
        self,
        ws_url: str,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
        log_prefix: str = "ws",
    ):
        self._ws_url = ws_url
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._log_prefix = log_prefix

        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._running = False

        self._subscriptions: set[str] = set()
        self._on_tick: TickCallback | None = None
        self._tick_handlers: dict[str, list[TickCallback]] = {}
        self._on_connect: ConnectCallback | None = None
        self._on_disconnect: DisconnectCallback | None = None

        # For depth feeds
        self._on_depth: Callable[[Any], None] | None = None

    @property
    def on_tick(self) -> TickCallback | None:
        return self._on_tick

    @on_tick.setter
    def on_tick(self, callback: TickCallback | None) -> None:
        self._on_tick = callback

    def register_tick_handler(self, subscription_key: str, callback: TickCallback) -> None:
        """Register a per-subscription tick handler (does not overwrite global on_tick)."""
        self._tick_handlers.setdefault(subscription_key, []).append(callback)

    def clear_tick_handlers(self, subscription_key: str | None = None) -> None:
        if subscription_key is None:
            self._tick_handlers.clear()
        else:
            self._tick_handlers.pop(subscription_key, None)

    def _dispatch_tick(self, tick: dict, subscription_key: str | None = None) -> None:
        if self._on_tick:
            self._on_tick(tick)
        if subscription_key:
            for handler in self._tick_handlers.get(subscription_key, []):
                handler(tick)

    @property
    def on_connect(self) -> ConnectCallback | None:
        return self._on_connect

    @on_connect.setter
    def on_connect(self, callback: ConnectCallback | None) -> None:
        self._on_connect = callback

    @property
    def on_disconnect(self) -> DisconnectCallback | None:
        return self._on_disconnect

    @on_disconnect.setter
    def on_disconnect(self, callback: DisconnectCallback | None) -> None:
        self._on_disconnect = callback

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._running

    def subscribe(self, key: str, exchange: str | None = None) -> None:
        self._subscriptions.add(key)
        if self._ws and self._running:
            self._send_subscribe([key])

    def unsubscribe(self, key: str, exchange: str | None = None) -> None:
        self._subscriptions.discard(key)
        if self._ws and self._running:
            self._send_unsubscribe([key])

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name=self._log_prefix, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._ws:
            self._ws.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._ws = None
        self._thread = None

    def _get_ws_url(self) -> str:
        """Return the WebSocket URL. Can be overridden by subclasses for dynamic URLs."""
        return self._ws_url

    def _run(self) -> None:
        strategy = ReconnectStrategy(
            base_delay=self._reconnect_delay,
            max_delay=self._max_reconnect_delay,
            max_retries=0,  # retry indefinitely until stopped
        )
        while self._running:
            self._ws = websocket.WebSocketApp(
                self._get_ws_url(),
                header=self._get_ws_headers(),
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self._ws.run_forever(ping_interval=30, ping_timeout=10)
            if self._running:
                logger.warning(
                    f"{self._log_prefix}_reconnecting",
                    extra={"delay": strategy.current_delay},
                )
                strategy.wait()

    def _on_open(self, ws) -> None:
        logger.info(f"{self._log_prefix}_connected")
        if self._on_connect:
            self._on_connect()
        subs = list(self._subscriptions)
        if subs:
            self._send_subscribe(subs)

    def _on_message(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return
        tick = self._parse_tick(data)
        if tick:
            key = tick.get("subscription_key") or tick.get("key")
            self._dispatch_tick(tick, str(key) if key else None)

    def _on_error(self, ws, error) -> None:
        logger.warning(f"{self._log_prefix}_error", extra={"error": str(error)})

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        logger.info(f"{self._log_prefix}_disconnected")
        if self._on_disconnect:
            self._on_disconnect()

    def _send_subscribe(self, keys: list[str]) -> None:
        if not self._ws:
            return
        msg = self._build_subscribe_message(keys)
        self._ws.send(msg)

    def _send_unsubscribe(self, keys: list[str]) -> None:
        if not self._ws:
            return
        msg = self._build_unsubscribe_message(keys)
        self._ws.send(msg)

    def _get_ws_headers(self) -> dict[str, str]:
        """Return WebSocket connection headers. Must be implemented by subclass."""
        raise NotImplementedError

    def _build_subscribe_message(self, keys: list[str]) -> str:
        """Return JSON message for subscribing to keys. Must be implemented by subclass."""
        raise NotImplementedError

    def _build_unsubscribe_message(self, keys: list[str]) -> str:
        """Return JSON message for unsubscribing from keys. Must be implemented by subclass."""
        raise NotImplementedError

    def _parse_tick(self, data: dict) -> dict | None:
        """Parse raw WebSocket data into a tick dict. Must be implemented by subclass."""
        raise NotImplementedError

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Callable[[Quote], Any] | None = None,
    ) -> StreamHandle:
        """Subscribe to a live tick stream (sync facade).

        Parameters
        ----------
        symbol : str
            Instrument symbol.
        exchange : str
            Exchange identifier (default: "NSE").
        mode : str
            Stream mode: "LTP", "QUOTE", or "DEPTH".
        on_tick : callable or None
            Callback invoked with canonical Quote for each update.

        Returns
        -------
        Stream handle with .disconnect() and .is_connected().
        """

        if on_tick is not None:

            def _on_tick(tick: dict) -> None:
                quote = Quote(
                    symbol=tick.get("symbol", ""),
                    ltp=Decimal(str(tick.get("ltp", 0))),
                    exchange=exchange,
                    open=Decimal(str(tick.get("open", 0))),
                    high=Decimal(str(tick.get("high", 0))),
                    low=Decimal(str(tick.get("low", 0))),
                    close=Decimal(str(tick.get("close", 0))),
                    volume=int(tick.get("volume", 0)),
                )
                on_tick(quote)

            self.on_tick = _on_tick

        self.subscribe(symbol, exchange)
        if not self.is_connected:
            self.start()

        return _StreamHandle(self, symbol, exchange)

    def stream_depth(
        self,
        symbol: str,
        exchange: str = "NSE",
        depth_type: str = "DEPTH_5",
        on_depth: Any = None,
    ) -> StreamHandle:
        """Subscribe to market depth streaming (sync facade).

        Parameters
        ----------
        symbol : str
            Instrument symbol.
        exchange : str
            Exchange identifier.
        depth_type : str
            Depth mode: "DEPTH_5", "DEPTH_20", "DEPTH_200".
        on_depth : callable or None
            Callback invoked with MarketDepth updates.

        Returns
        -------
        Stream handle with .stop() and .is_connected().
        """

        if on_depth is not None:
            self._on_depth = on_depth

        self.subscribe(symbol, exchange)
        if not self.is_connected:
            self.start()

        return StreamingHandle(self, symbol, exchange)

    async def connect(self) -> None:
        """Establish the WebSocket connection (async wrapper for start)."""
        self.start()

    async def disconnect(self) -> None:
        """Close the WebSocket connection (async wrapper for stop)."""
        self.stop()

    async def subscribe_quotes(
        self,
        symbols: list[str],
        exchange: str,
        callback: Callable[[Quote], Any],
    ) -> None:
        """Subscribe to real-time market quotes (async wrapper)."""

        def _on_tick(tick: dict) -> None:
            quote = Quote(
                symbol=tick.get("symbol", ""),
                ltp=Decimal(str(tick.get("ltp", 0))),
                exchange=exchange,
                open=Decimal(str(tick.get("open", 0))),
                high=Decimal(str(tick.get("high", 0))),
                low=Decimal(str(tick.get("low", 0))),
                close=Decimal(str(tick.get("close", 0))),
                volume=int(tick.get("volume", 0)),
            )
            callback(quote)

        self.on_tick = _on_tick
        for symbol in symbols:
            self.subscribe(symbol, exchange)

    async def unsubscribe_quotes(
        self,
        symbols: list[str],
        exchange: str,
    ) -> None:
        """Unsubscribe from real-time market quotes (async wrapper)."""
        for symbol in symbols:
            self.unsubscribe(symbol, exchange)


class StreamHandle:
    def __init__(self, streaming, symbol: str, exchange: str) -> None:
        self._streaming = streaming
        self._symbol = symbol
        self._exchange = exchange

    def stop(self) -> None:
        self._streaming.unsubscribe(self._symbol, self._exchange)

    def disconnect(self) -> None:
        self.stop()


class _StreamHandle:
    """Concrete stream handle returned by synchronous streaming facades.

    Implements the ``StreamHandle`` protocol from ``ports/streaming``.
    """

    def __init__(self, streaming: BaseWebSocketStreaming, symbol: str, exchange: str) -> None:
        self._streaming = streaming
        self._symbol = symbol
        self._exchange = exchange

    def disconnect(self) -> None:
        self._streaming.unsubscribe(self._symbol, self._exchange)

    @property
    def is_connected(self) -> bool:
        return self._streaming.is_connected
