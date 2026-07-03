"""Simple WebSocket rate limiting for Dhan broker.

Provides basic rate limiting for WebSocket connections with connection
rate limiting and connection pool size management for depth-200 feeds.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class SimpleWebSocketRateLimiter:
    """Simple WebSocket rate limiter for Dhan connections.

    Provides basic rate limiting with:
    - Connection rate limiting using timestamps
    - Connection pool size management for depth-200 feeds
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._last_connection_time = 0.0
        self._min_connection_interval = 1.0
        self._depth_200_connections = 0
        self._max_depth_200_connections = 5
        self._connection_violations = 0

    def can_create_connection(self) -> bool:
        """Check if a new WebSocket connection can be created."""
        with self._lock:
            current_time = time.monotonic()
            time_since_last = current_time - self._last_connection_time

            if time_since_last >= self._min_connection_interval:
                self._last_connection_time = current_time
                return True
            else:
                self._connection_violations += 1
                logger.warning(
                    "websocket_connection_rate_limit_violation",
                    extra={
                        "violations": self._connection_violations,
                        "retry_after": self._min_connection_interval - time_since_last,
                    },
                )
                return False

    def can_create_depth_200_connection(self) -> bool:
        """Check if a new depth-200 connection can be created."""
        with self._lock:
            if self._depth_200_connections < self._max_depth_200_connections:
                return True
            else:
                logger.warning(
                    "depth_200_connection_limit_reached",
                    extra={
                        "current_connections": self._depth_200_connections,
                        "max_connections": self._max_depth_200_connections,
                    },
                )
                return False

    def get_connection_delay(self) -> float:
        """Get the delay until next connection can be created."""
        with self._lock:
            current_time = time.monotonic()
            time_since_last = current_time - self._last_connection_time
            delay = self._min_connection_interval - time_since_last
            return max(0.0, delay)

    def get_stats(self) -> dict[str, Any]:
        """Get rate limiter statistics."""
        with self._lock:
            return {
                "connections": {
                    "violations": self._connection_violations,
                    "delay_seconds": self.get_connection_delay(),
                },
                "depth_200": {
                    "current_connections": self._depth_200_connections,
                    "max_connections": self._max_depth_200_connections,
                },
            }

    def reset_violations(self) -> None:
        """Reset all rate limit violation counters."""
        with self._lock:
            self._connection_violations = 0


_dhan_ws_rate_limiter: SimpleWebSocketRateLimiter | None = None
_dhan_ws_rate_limiter_lock = threading.Lock()


def get_dhan_ws_rate_limiter() -> SimpleWebSocketRateLimiter:
    """Get or create the global Dhan WebSocket rate limiter."""
    global _dhan_ws_rate_limiter

    with _dhan_ws_rate_limiter_lock:
        if _dhan_ws_rate_limiter is None:
            _dhan_ws_rate_limiter = SimpleWebSocketRateLimiter()
        return _dhan_ws_rate_limiter


def reset_dhan_ws_rate_limiter() -> None:
    """Reset the global Dhan WebSocket rate limiter."""
    global _dhan_ws_rate_limiter

    with _dhan_ws_rate_limiter_lock:
        if _dhan_ws_rate_limiter is not None:
            _dhan_ws_rate_limiter.reset_violations()
