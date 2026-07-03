"""Upstox portfolio WebSocket stream — order/position/holding updates."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any

from brokers.adapters.upstox.feed_authorizer import UpstoxFeedAuthorizer
from brokers.infrastructure.websocket_runner import ReconnectingWebSocketRunner

logger = logging.getLogger(__name__)

PortfolioListener = Callable[[str, dict[str, Any]], None]


class UpstoxPortfolioStream:
    def __init__(
        self,
        feed_authorizer: UpstoxFeedAuthorizer,
        token_provider: Callable[[], str],
        reconnect_delay: float = 5.0,
    ) -> None:
        self._authorizer = feed_authorizer
        self._token_provider = token_provider
        self._reconnect_delay = reconnect_delay
        self._listeners: list[PortfolioListener] = []
        self._lock = threading.RLock()
        self._runner: ReconnectingWebSocketRunner | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def update_access_token(self, token: str) -> None:
        self._token_provider = lambda: token

    def add_listener(self, listener: PortfolioListener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: PortfolioListener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def start(self) -> None:
        if self._runner and self._runner.is_running:
            return
        self._runner = ReconnectingWebSocketRunner(
            url=self._resolve_url,
            header=self._resolve_headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            reconnect_delay=self._reconnect_delay,
            log_prefix="upstox_portfolio_ws",
        )
        self._runner.start()

    def stop(self) -> None:
        self._connected = False
        if self._runner:
            self._runner.stop()
            self._runner = None

    def _resolve_url(self) -> str:
        url = self._authorizer.authorize_portfolio_stream()
        if not url:
            raise RuntimeError("Portfolio stream authorize returned empty URL")
        return url

    def _resolve_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token_provider()}"}

    def _on_open(self, ws: Any) -> None:
        self._connected = True
        logger.info("upstox_portfolio_stream_connected")

    def _on_message(self, ws: Any, message: str | bytes) -> None:
        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            data = json.loads(message)
        except Exception:
            return
        update_type = str(data.get("update_type", data.get("type", "unknown")))
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(update_type, data)
            except Exception as exc:
                logger.warning("Portfolio listener error: %s", exc)

    def _on_error(self, ws: Any, error: Any) -> None:
        logger.warning("upstox_portfolio_stream_error", extra={"error": str(error)})

    def _on_close(self, ws: Any, code: int, msg: str | bytes) -> None:
        self._connected = False
        logger.info("upstox_portfolio_stream_disconnected")
