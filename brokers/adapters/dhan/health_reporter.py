"""Dhan health reporter — connection status and health metrics.

Extracted from DhanGateway to reduce the god object. Aggregates auth
validity, scheduler health, broadcast metrics, WebSocket connection
status, and circuit breaker states.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from inc_trade.ports.http_client_port import HttpClientPort

from brokers.adapters.dhan.auth import DhanAuth
from brokers.adapters.dhan.connection_manager import DhanConnectionManager
from brokers.adapters.dhan.depth20 import DhanDepth20Stream
from brokers.adapters.dhan.depth200 import DhanDepth200Stream
from brokers.adapters.dhan.order_stream import DhanOrderStream
from brokers.adapters.dhan.streaming import DhanStreaming

logger = logging.getLogger(__name__)


class DhanHealthReporter:
    """Reports health status for Dhan gateway connections and lifecycle.

    Aggregates auth validity, scheduler health, broadcast metrics,
    WebSocket connection status, and circuit breaker states.
    """

    def __init__(
        self,
        auth: DhanAuth,
        connection_manager: DhanConnectionManager,
        http_client: HttpClientPort,
        streaming: DhanStreaming,
        order_stream: DhanOrderStream,
        depth20_stream: DhanDepth20Stream,
        depth200_stream: DhanDepth200Stream,
    ):
        self._auth = auth
        self._conn_mgr = connection_manager
        self._client = http_client
        self._streaming = streaming
        self._order_stream = order_stream
        self._depth20_stream = depth20_stream
        self._depth200_stream = depth200_stream

    def health(self) -> dict[str, Any]:
        """Full health report for the gateway."""
        return {
            "auth_valid": self._auth.is_valid(),
            "scheduler": self._conn_mgr.scheduler.health() if self._conn_mgr.scheduler else None,
            "broadcast": self._conn_mgr.broadcast.token_refresh_metrics,
            "connections": self.connection_status(),
            "circuit_breakers": self._client.circuit_breaker_states(),
        }

    def connection_status(self) -> dict[str, bool]:
        """Per-feed WebSocket connection status."""
        return {
            "market_feed": self._streaming.is_connected,
            "order_stream": self._order_stream.is_connected,
            "depth_20": self._feed_connected(self._depth20_stream),
            "depth_200": self._feed_connected(self._depth200_stream),
            "has_active_subscriptions": bool(
                getattr(self._streaming, "_subscriptions", None)
                and len(self._streaming._subscriptions) > 0
            ),
        }

    def get_connection_metadata(self) -> dict[str, Any]:
        """Non-bool diagnostic metadata for feeds."""
        metadata: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            if hasattr(self._streaming, "health"):
                health = self._streaming.health()
                metrics = getattr(health, "metrics", None) or {}
                metadata["market_feed_stale"] = bool(metrics.get("is_stale", False))
        return metadata

    def circuit_breaker_states(self) -> dict[str, int]:
        """Circuit breaker states: 0=CLOSED, 1=OPEN, 2=HALF_OPEN."""
        return self._client.circuit_breaker_states()

    def get_token_refresh_metrics(self) -> dict[str, int]:
        """Token refresh counters from broadcast + scheduler."""
        return self._conn_mgr.get_token_refresh_metrics()

    @staticmethod
    def _feed_connected(feed: Any) -> bool:
        connected = getattr(feed, "is_connected", None)
        if callable(connected):
            return bool(connected())
        if connected is not None:
            return bool(connected)
        return bool(getattr(feed, "_is_connected", False))
