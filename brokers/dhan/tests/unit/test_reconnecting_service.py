"""Unit tests for the ReconnectingServiceMixin.

Plan §7.2: the mixin centralises reconnect / message-tracking / callback
discipline. These tests assert the invariants that the mixin promises, so
a regression that reverts to a per-class bespoke implementation is caught
immediately.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from brokers.dhan.reconnecting_service import ReconnectingServiceMixin


class _StubMixin(ReconnectingServiceMixin):
    """Minimal concrete subclass used to exercise the mixin in isolation."""

    def __init__(self) -> None:
        self._init_reconnect_state()
        self._callbacks: list = []


# ── State initialisation ────────────────────────────────────────────────────


class TestReconnectStateInit:
    def test_init_sets_all_required_attributes(self):
        stub = _StubMixin()
        assert isinstance(stub._stop_event, threading.Event)
        assert stub._is_connected is False
        assert stub._reconnect_count == 0
        assert stub._last_message_at is None
        assert stub._message_count == 0
        assert isinstance(stub._callback_lock, type(stub._stop_event)) or hasattr(
            stub._callback_lock, "acquire"
        )

    def test_initialize_is_idempotent(self):
        """A second _init_reconnect_state resets state cleanly."""
        stub = _StubMixin()
        stub._is_connected = True
        stub._reconnect_count = 7
        stub._message_count = 100
        stub._init_reconnect_state()
        assert stub._is_connected is False
        assert stub._reconnect_count == 0
        assert stub._message_count == 0


# ── Callback registration ───────────────────────────────────────────────────


class TestCallbackRegistration:
    def test_register_appends_under_lock(self):
        stub = _StubMixin()
        seen: list = []

        def cb() -> None:
            seen.append(1)

        stub._register_callback(stub._callbacks, cb)
        assert stub._callbacks == [cb]

    def test_snapshot_returns_independent_copy(self):
        stub = _StubMixin()
        seen: list = []

        def cb() -> None:
            seen.append(1)

        stub._register_callback(stub._callbacks, cb)
        snap = stub._snapshot_callbacks(stub._callbacks)
        snap.clear()
        # The original list must be unaffected.
        assert stub._callbacks == [cb]

    def test_register_is_thread_safe(self):
        """100 threads each registering 50 callbacks must all land in the list."""
        stub = _StubMixin()

        def cb() -> None:
            return None

        threads = [
            threading.Thread(
                target=lambda: [stub._register_callback(stub._callbacks, cb) for _ in range(50)]
            )
            for _ in range(100)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(stub._callbacks) == 5000


# ── Message tracking ────────────────────────────────────────────────────────


class TestMessageTracking:
    def test_note_message_received_updates_timestamp(self):
        stub = _StubMixin()
        before = datetime.now(timezone.utc)
        stub._note_message_received()
        after = datetime.now(timezone.utc)
        assert stub._last_message_at is not None
        assert before <= stub._last_message_at <= after
        assert stub._message_count == 1

    def test_note_message_received_increments_counter(self):
        stub = _StubMixin()
        for _ in range(5):
            stub._note_message_received()
        assert stub._message_count == 5


# ── Backoff discipline ──────────────────────────────────────────────────────


class TestBackoffDiscipline:
    def test_initial_backoff_value(self):
        assert ReconnectingServiceMixin.INITIAL_BACKOFF == 1.0
        assert ReconnectingServiceMixin.MAX_BACKOFF == 30.0

    def test_backoff_sleep_returns_doubled_value(self):
        stub = _StubMixin()
        next_backoff = stub._backoff_sleep(2.0)
        assert next_backoff == 4.0

    def test_backoff_sleep_caps_at_max(self):
        stub = _StubMixin()
        next_backoff = stub._backoff_sleep(20.0)
        assert next_backoff == ReconnectingServiceMixin.MAX_BACKOFF

    def test_backoff_sleep_interrupted_by_stop_event(self):
        stub = _StubMixin()
        stub._stop_event.set()
        started = time.time()
        stub._backoff_sleep(5.0)  # would otherwise sleep 5s
        elapsed = time.time() - started
        # Event.wait returns True when the event is already set; we should
        # return near-instantly rather than blocking for the full backoff.
        assert elapsed < 1.0

    def test_clean_disconnect_resets_to_initial(self):
        stub = _StubMixin()
        # Simulate that we had escalated to max.
        next_backoff = stub._on_clean_disconnect()
        assert next_backoff == ReconnectingServiceMixin.INITIAL_BACKOFF
        assert stub._reconnect_count == 1

    def test_reconnect_failure_increments_counter(self):
        stub = _StubMixin()
        next_backoff = stub._on_reconnect_failure(4.0)
        # On failure the mixin does NOT escalate — the caller does that.
        assert next_backoff == 4.0
        assert stub._reconnect_count == 1


# ── Correlation-id generation ───────────────────────────────────────────────


class TestCorrelationId:
    def test_correlation_id_has_prefix(self):
        cid = _StubMixin.next_correlation_id(prefix="ws")
        assert cid.startswith("ws-")

    def test_correlation_ids_are_unique(self):
        ids = {_StubMixin.next_correlation_id() for _ in range(100)}
        assert len(ids) == 100

    def test_correlation_id_carries_timestamp(self):
        cid = _StubMixin.next_correlation_id()
        # Format: "{prefix}-{millis}-{counter}"
        parts = cid.split("-")
        assert len(parts) >= 3
        # The timestamp portion must parse as int (milliseconds since epoch).
        assert int(parts[-2]) > 0
