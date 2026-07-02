"""Lifecycle-managed wrapper for UpstoxMarketDataV3Multiplexer.

Wraps the raw WebSocket multiplexer in a ManagedService so it can be
registered with the LifecycleManager and participate in deterministic
start/stop. This mirrors the Dhan DhanMarketFeed pattern.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from infrastructure.lifecycle.lifecycle import (
    HealthState,
    HealthStatus,
    ManagedService,
)

logger = logging.getLogger(__name__)


class UpstoxWebSocketService(ManagedService):
    """ManagedService wrapper for UpstoxMarketDataV3Multiplexer.

    Registers with the LifecycleManager so ``lifecycle.start_all()``
    connects the WebSocket and ``lifecycle.stop_all()`` disconnects it
    cleanly on CLI exit.
    """

    def __init__(self, multiplexer: Any, name: str = "upstox.websocket") -> None:
        self._mux = multiplexer
        self.name = name
        self._started = False
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._mux.is_connected

    def start(self) -> None:
        """Connect the WebSocket (async, scheduled on the event loop)."""
        with self._lock:
            if self._started:
                return
            self._started = True
        try:
            from brokers.common.async_compat import run_async_compat

            run_async_compat(self._mux.connect())
            logger.info("upstox_websocket_started", extra={"service": self.name})
        except Exception as exc:
            with self._lock:
                self._started = False
            logger.warning("upstox_websocket_start_failed: %s", exc)

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """Disconnect the WebSocket cleanly."""
        with self._lock:
            if not self._started:
                return
            self._started = False
        try:
            from brokers.common.async_compat import run_async_compat

            run_async_compat(self._mux.disconnect())
            logger.info("upstox_websocket_stopped", extra={"service": self.name})
        except Exception as exc:
            logger.debug("upstox_websocket_stop_failed: %s", exc)

    def health(self) -> HealthStatus:
        if self._started and self._mux.is_connected:
            state = HealthState.HEALTHY
        elif self._started:
            state = HealthState.DEGRADED
        else:
            state = HealthState.STOPPED
        return HealthStatus(
            state=state,
            service=self.name,
            last_check=datetime.now(timezone.utc),
        )


class UpstoxPortfolioStreamService(ManagedService):
    """ManagedService wrapper for UpstoxPortfolioStream."""

    def __init__(self, stream: Any, name: str = "upstox.portfolio_stream") -> None:
        self._stream = stream
        self.name = name
        self._started = False
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._stream.is_connected

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        try:
            from brokers.common.async_compat import run_async_compat

            run_async_compat(self._stream.connect())
            logger.info("upstox_portfolio_stream_started", extra={"service": self.name})
        except Exception as exc:
            with self._lock:
                self._started = False
            logger.warning("upstox_portfolio_stream_start_failed: %s", exc)

    def stop(self, timeout_seconds: float = 5.0) -> None:
        with self._lock:
            if not self._started:
                return
            self._started = False
        try:
            from brokers.common.async_compat import run_async_compat

            run_async_compat(self._stream.disconnect())
            logger.info("upstox_portfolio_stream_stopped", extra={"service": self.name})
        except Exception as exc:
            logger.debug("upstox_portfolio_stream_stop_failed: %s", exc)

    def health(self) -> HealthStatus:
        if self._started and self._stream.is_connected:
            state = HealthState.HEALTHY
        elif self._started:
            state = HealthState.DEGRADED
        else:
            state = HealthState.STOPPED
        return HealthStatus(
            state=state,
            service=self.name,
            last_check=datetime.now(timezone.utc),
        )
