"""Upstox adapter observability metrics."""

from __future__ import annotations

import threading


class UpstoxMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._refresh_count = 0
        self._refresh_errors = 0
        self._ws_connected = 0
        self._ws_reconnects = 0

    def record_refresh(self, *, success: bool) -> None:
        with self._lock:
            if success:
                self._refresh_count += 1
            else:
                self._refresh_errors += 1

    def set_ws_connected(self, connected: bool) -> None:
        with self._lock:
            self._ws_connected = 1 if connected else 0

    def record_ws_reconnect(self) -> None:
        with self._lock:
            self._ws_reconnects += 1

    def token_refresh_snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "refresh_count": self._refresh_count,
                "error_count": self._refresh_errors,
                "ws_connected": self._ws_connected,
                "ws_reconnects": self._ws_reconnects,
            }
