"""Shared WebSocket reconnect loop for sync adapters."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import websocket

from brokers_core.domain.constants.timeouts import DEFAULT_MAX_RECONNECT_DELAY, DEFAULT_RECONNECT_DELAY
from brokers_core.infrastructure.reconnect_strategy import ReconnectStrategy

logger = logging.getLogger(__name__)

OnOpen = Callable[[websocket.WebSocketApp], None]
OnMessage = Callable[[websocket.WebSocketApp, str | bytes], None]
OnError = Callable[[websocket.WebSocketApp, Any], None]
OnClose = Callable[[websocket.WebSocketApp, Any, Any], None]


class ReconnectingWebSocketRunner:
    """Run a WebSocketApp with exponential backoff until stopped."""

    def __init__(
        self,
        *,
        url: str | Callable[[], str],
        header: dict[str, str] | Callable[[], dict[str, str]] | None = None,
        on_open: OnOpen | None = None,
        on_message: OnMessage | None = None,
        on_error: OnError | None = None,
        on_close: OnClose | None = None,
        reconnect_delay: float = DEFAULT_RECONNECT_DELAY,
        max_reconnect_delay: float = DEFAULT_MAX_RECONNECT_DELAY,
        ping_interval: int = 30,
        ping_timeout: int = 10,
        log_prefix: str = "ws",
    ) -> None:
        self._url = url
        self._header = header
        self._on_open = on_open
        self._on_message = on_message
        self._on_error = on_error
        self._on_close = on_close
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._log_prefix = log_prefix
        self._running = False
        self._thread: threading.Thread | None = None
        self._ws: websocket.WebSocketApp | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def ws(self) -> websocket.WebSocketApp | None:
        return self._ws

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name=self._log_prefix, daemon=True)
        self._thread.start()

    def stop(self, join_timeout: float = 5.0) -> None:
        self._running = False
        if self._ws:
            self._ws.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=join_timeout)
        self._ws = None
        self._thread = None

    def _resolve_url(self) -> str:
        return self._url() if callable(self._url) else self._url

    def _resolve_header(self) -> dict[str, str]:
        if self._header is None:
            return {}
        return self._header() if callable(self._header) else self._header

    def _run(self) -> None:
        strategy = ReconnectStrategy(
            base_delay=self._reconnect_delay,
            max_delay=self._max_reconnect_delay,
            max_retries=0,  # retry indefinitely until stopped
        )
        while self._running:
            self._ws = websocket.WebSocketApp(
                self._resolve_url(),
                header=self._resolve_header(),
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self._ws.run_forever(
                ping_interval=self._ping_interval,
                ping_timeout=self._ping_timeout,
            )
            if self._running:
                logger.warning(
                    "%s_reconnecting", self._log_prefix, extra={"delay": strategy.current_delay}
                )
                strategy.wait()
