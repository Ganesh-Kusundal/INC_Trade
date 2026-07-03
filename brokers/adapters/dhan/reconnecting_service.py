"""Shared lifecycle / reconnect / callback machinery for Dhan WebSocket services.

Extracted from the archived DhanMarketFeed/DhanDepth20Feed to provide shared
reconnect logic, backoff arithmetic, message tracking, and correlation-id
generation. Used by all Dhan WebSocket services.
"""

from __future__ import annotations

import contextlib
import itertools
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Generic, TypeVar

log = logging.getLogger(__name__)

_CallbackT = TypeVar("_CallbackT", bound=Callable[..., None])


class ReconnectingServiceMixin(Generic[_CallbackT]):
    """Mixin that owns the reconnect / message-tracking plumbing.

    Used by DhanWebSocket services (market feed, order stream, depth feeds).

    Responsibilities:
    - _stop_event: interruptible thread-stop coordination
    - _is_connected: best-effort connection flag
    - _reconnect_count: total reconnect cycles
    - _last_message_at: UTC timestamp of last received message
    - _message_count: running total of received messages
    - backoff arithmetic
    - correlation-id generation
    """

    _stop_event: threading.Event
    _is_connected: bool
    _reconnect_count: int
    _last_message_at: datetime | None
    _message_count: int
    _callback_lock: threading.RLock

    INITIAL_BACKOFF = 1.0
    MAX_BACKOFF = 30.0

    def _init_reconnect_state(self) -> None:
        """Initialize the reconnect / message-tracking state."""
        self._stop_event = threading.Event()
        self._is_connected = False
        self._reconnect_count = 0
        self._last_message_at = None
        self._last_monotonic_at: float = time.monotonic()
        self._message_count = 0
        self._callback_lock = threading.RLock()
        self._watchdog_thread: threading.Thread | None = None

    # ── Callback registration (lock + snapshot discipline) ─────────────────

    def _register_callback(
        self, callback_list: list[_CallbackT], callback: _CallbackT
    ) -> None:
        """Append callback under lock."""
        with self._callback_lock:
            callback_list.append(callback)

    def _unregister_callback(
        self, callback_list: list[_CallbackT], callback: _CallbackT
    ) -> None:
        """Remove callback under lock."""
        with self._callback_lock, contextlib.suppress(ValueError):
            callback_list.remove(callback)

    def _snapshot_callbacks(self, callback_list: list[_CallbackT]) -> list[_CallbackT]:
        """Return a snapshot of callback_list for safe iteration."""
        with self._callback_lock:
            return list(callback_list)

    # ── Message-tracking ───────────────────────────────────────────────────

    def _note_message_received(self) -> None:
        """Mark that a message was consumed. Updates freshness signal."""
        self._last_message_at = datetime.now(timezone.utc)
        self._last_monotonic_at = time.monotonic()
        self._message_count += 1

    # ── Backoff ───────────────────────────────────────────────────────────

    def _backoff_sleep(self, current: float) -> float:
        """Sleep for backoff and return next value.

        Uses Event.wait so stop() interrupts immediately.
        """
        wait = min(current, self.MAX_BACKOFF)
        self._stop_event.wait(timeout=wait)
        return min(current * 2, self.MAX_BACKOFF)

    def _on_clean_disconnect(self) -> float:
        """Reset state after clean disconnect. Always resets backoff to initial."""
        self._reconnect_count += 1
        return self.INITIAL_BACKOFF

    def _on_reconnect_failure(self, current: float) -> float:
        """Note reconnect failure and return backoff."""
        self._reconnect_count += 1
        self._emit_reconnect_metric()
        return current

    def _emit_reconnect_metric(self) -> None:
        try:
            import prometheus_client

            from brokers.adapters.dhan.metrics import dhan_ws_reconnect_total

            dhan_ws_reconnect_total.inc()
        except Exception:
            pass

    # ── Correlation-id generation ──────────────────────────────────────────

    _correlation_counter = itertools.count(1)

    @classmethod
    def next_correlation_id(cls, prefix: str = "ws") -> str:
        """Generate monotonic correlation id for event tracing."""
        n = next(cls._correlation_counter)
        return f"{prefix}-{int(time.time() * 1000)}-{n}"
