"""Shared lifecycle / reconnect / callback machinery for Dhan WS services.

Plan §7.2 + §8: ``DhanMarketFeed``, ``PollingMarketFeed`` and the unified
``BinaryDepthFeed`` (depth-20 / depth-200) each implemented their own
reconnect loop, backoff, ``_last_message_at`` tracking, and callback
list helpers. This module collects that machinery into one place so a
future change to "reconnect behaviour" is a single edit, not shotgun
surgery across five classes.

What the mixin owns
-------------------
- ``_stop_event``           — interruptible thread-stop coordination
- ``_is_connected``         — best-effort connection flag
- ``_reconnect_count``      — total reconnect cycles
- ``_last_message_at``      — UTC timestamp of last received message
- ``_message_count``        — running total of received messages
- ``_callback_lock``        — guard for ``*_callbacks`` lists
- backoff arithmetic        — 1.0 → 30.0 s with reset on clean exit
- correlation-id generation  — monotonic per-process counter

What the mixin does NOT own
---------------------------
- The actual ``threading.Thread`` lifecycle (start/stop/join). That
  varies per service (``DhanMarketFeed`` uses an SDK feed, the binary
  depth feed uses raw ``websockets``, ``PollingMarketFeed`` runs an
  in-process sleep loop) and stays in each subclass.
- Domain-specific ``*_callbacks`` lists. Subclasses still own their
  own callback attribute but register through ``_register_callback``
  so the lock and the snapshotting discipline are uniform.
- Health snapshot construction. Subclasses still build their own
  :class:`HealthStatus` because the metrics they expose differ.
"""

from __future__ import annotations

import contextlib
import itertools
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Generic, TypeVar

_CallbackT = TypeVar("_CallbackT", bound=Callable[..., None])


class ReconnectingServiceMixin(Generic[_CallbackT]):
    """Mixin that owns the reconnect / message-tracking plumbing.

    Subclasses must:

    - call :meth:`_init_reconnect_state` from their ``__init__``
    - call :meth:`_register_callback` to add callbacks (so the lock and
      snapshot semantics are uniform)
    - call :meth:`_note_message_received` whenever a message of any kind
      is consumed (so ``_last_message_at`` and ``_message_count`` are
      correct and the health snapshot reports the truth)
    - drive their own thread loop but use :meth:`_backoff_sleep` for
      inter-reconnect delays and :meth:`_on_clean_disconnect` /
      :meth:`_on_reconnect_failure` to update the backoff correctly.
    """

    # ── State (subclass must call _init_reconnect_state) ────────────────────
    _stop_event: threading.Event
    _is_connected: bool
    _reconnect_count: int
    _last_message_at: datetime | None
    _message_count: int
    _callback_lock: threading.RLock

    # Backoff config (Plan §5.3 noted the original DhanMarketFeed backoff
    # only reset on certain exception types; the mixin always resets).
    INITIAL_BACKOFF = 1.0
    MAX_BACKOFF = 30.0

    def _init_reconnect_state(self) -> None:
        """Initialise the reconnect / message-tracking state."""
        self._stop_event = threading.Event()
        self._is_connected = False
        self._reconnect_count = 0
        self._last_message_at = None
        self._message_count = 0
        self._callback_lock = threading.RLock()

    # ── Callback registration (lock + snapshot discipline) ─────────────────

    def _register_callback(self, callback_list: list[_CallbackT], callback: _CallbackT) -> None:
        """Append *callback* to *callback_list* under the mixin's lock.

        Subclasses pass their own list — the mixin does not own the list,
        so each subclass can still type-annotate its callbacks. The lock
        guarantees that callbacks can be added concurrently from the
        thread that owns the WS connection.
        """
        with self._callback_lock:
            callback_list.append(callback)

    def _unregister_callback(self, callback_list: list[_CallbackT], callback: _CallbackT) -> None:
        """Remove *callback* from *callback_list* under the mixin's lock."""
        with self._callback_lock, contextlib.suppress(ValueError):
            callback_list.remove(callback)

    def _snapshot_callbacks(self, callback_list: list[_CallbackT]) -> list[_CallbackT]:
        """Return a snapshot of *callback_list* for safe iteration.

        Iteration is outside the lock so a slow callback cannot block
        other registrations. This was the discipline used in
        ``DhanDepth20Feed._dispatch_depth`` and is now centralised.
        """
        with self._callback_lock:
            return list(callback_list)

    # ── Message-tracking ───────────────────────────────────────────────────

    def _note_message_received(self) -> None:
        """Mark that a message of any kind was consumed.

        Should be called by subclasses on every successful receive,
        regardless of whether the message is a tick, depth packet, or
        order update. This is what ``health()`` reports as the freshness
        signal — and it must NOT be updated on heartbeats only
        (Plan §5.1 finding).
        """
        self._last_message_at = datetime.now(timezone.utc)
        self._message_count += 1

    # ── Backoff ────────────────────────────────────────────────────────────

    def _backoff_sleep(self, current: float) -> float:
        """Sleep for ``min(current, MAX_BACKOFF)`` and return the next value.

        Uses :meth:`threading.Event.wait` so a ``stop()`` interrupts the
        sleep immediately rather than blocking the thread for the full
        backoff window.

        Returns the next backoff value (``current * 2`` capped at
        ``MAX_BACKOFF``). The caller should call this in a loop:

            backoff = INITIAL_BACKOFF
            while not self._stop_event.is_set():
                try:
                    self._run_once()
                    backoff = self._on_clean_disconnect()
                except Exception:  # noqa: S110
                    backoff = self._on_reconnect_failure(backoff)
                if self._stop_event.is_set():
                    break
                backoff = self._backoff_sleep(backoff)
        """
        wait = min(current, self.MAX_BACKOFF)
        # Event.wait returns True if the event was set during the wait,
        # so a stop() interrupts immediately.
        self._stop_event.wait(timeout=wait)
        return min(current * 2, self.MAX_BACKOFF)

    def _on_clean_disconnect(self) -> float:
        """Reset state after a clean (expected) disconnect.

        The previous ``DhanMarketFeed`` bug was that backoff only
        reset on certain exception types. With the mixin the reset is
        unconditional: every clean exit starts the next reconnect at
        ``INITIAL_BACKOFF``.
        """
        self._reconnect_count += 1
        return self.INITIAL_BACKOFF

    def _on_reconnect_failure(self, current: float) -> float:
        """Note a reconnect failure and return the (already-incremented) backoff.

        Subclasses that want custom handling for specific exceptions
        (e.g. ``"429"`` rate-limit) can override this — the default
        simply increments the counter and returns the unchanged
        current backoff so the caller escalates on the next iteration.
        """
        self._reconnect_count += 1
        self._emit_reconnect_metric()
        return current

    def _emit_reconnect_metric(self) -> None:
        try:
            from brokers.dhan.metrics import dhan_ws_reconnect_total

            dhan_ws_reconnect_total.inc()
        except Exception:
            pass

    # ── Correlation-id generation ──────────────────────────────────────────

    _correlation_counter = itertools.count(1)

    @classmethod
    def next_correlation_id(cls, prefix: str = "ws") -> str:
        """Generate a monotonic correlation id.

        Used to stamp every published event so an event-bus subscriber
        can trace one logical operation (e.g. a single reconnect cycle)
        end-to-end (Plan §4 — invariant checklist flagged this as a
        gap).
        """
        n = next(cls._correlation_counter)
        return f"{prefix}-{int(time.time() * 1000)}-{n}"
