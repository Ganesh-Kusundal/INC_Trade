"""Unit tests for ReconnectingServiceMixin in reconnecting_service.py."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from brokers.adapters.dhan.reconnecting_service import ReconnectingServiceMixin


class _StubService(ReconnectingServiceMixin):
    """Minimal concrete class to test the mixin in isolation."""

    def __init__(self) -> None:
        self._init_reconnect_state()


@pytest.fixture
def service() -> _StubService:
    return _StubService()


class TestInitReconnectState:
    """Tests for _init_reconnect_state."""

    def test_stop_event_is_set_false(self, service: _StubService) -> None:
        assert service._stop_event.is_set() is False

    def test_is_connected_false(self, service: _StubService) -> None:
        assert service._is_connected is False

    def test_reconnect_count_zero(self, service: _StubService) -> None:
        assert service._reconnect_count == 0

    def test_last_message_at_none(self, service: _StubService) -> None:
        assert service._last_message_at is None

    def test_message_count_zero(self, service: _StubService) -> None:
        assert service._message_count == 0

    def test_callback_lock_exists(self, service: _StubService) -> None:
        assert isinstance(service._callback_lock, type(threading.RLock()))


class TestRegisterCallback:
    """Tests for _register_callback and _unregister_callback."""

    def test_register_adds_callback(self, service: _StubService) -> None:
        cb = MagicMock()
        callback_list: list[MagicMock] = []

        service._register_callback(callback_list, cb)

        assert cb in callback_list

    def test_register_multiple_callbacks(self, service: _StubService) -> None:
        cb1 = MagicMock()
        cb2 = MagicMock()
        callback_list: list[MagicMock] = []

        service._register_callback(callback_list, cb1)
        service._register_callback(callback_list, cb2)

        assert callback_list == [cb1, cb2]

    def test_unregister_removes_callback(self, service: _StubService) -> None:
        cb = MagicMock()
        callback_list = [cb]

        service._unregister_callback(callback_list, cb)

        assert cb not in callback_list

    def test_unregister_nonexistent_no_error(self, service: _StubService) -> None:
        cb = MagicMock()
        callback_list: list[MagicMock] = []

        service._unregister_callback(callback_list, cb)

        assert callback_list == []


class TestSnapshotCallbacks:
    """Tests for _snapshot_callbacks."""

    def test_returns_copy(self, service: _StubService) -> None:
        cb = MagicMock()
        callback_list = [cb]

        snapshot = service._snapshot_callbacks(callback_list)

        assert snapshot == [cb]
        assert snapshot is not callback_list

    def test_mutation_does_not_affect_original(
        self, service: _StubService
    ) -> None:
        cb = MagicMock()
        callback_list = [cb]

        snapshot = service._snapshot_callbacks(callback_list)
        snapshot.clear()

        assert cb in callback_list

    def test_empty_list(self, service: _StubService) -> None:
        assert service._snapshot_callbacks([]) == []


class TestBackoffSleep:
    """Tests for _backoff_sleep."""

    def test_returns_doubled_value(self, service: _StubService) -> None:
        result = service._backoff_sleep(2.0)

        assert 3.0 <= result <= 5.0

    def test_caps_at_max_backoff(self, service: _StubService) -> None:
        result = service._backoff_sleep(20.0)

        assert 22.5 <= result <= 37.5

    def test_initial_backoff(self, service: _StubService) -> None:
        result = service._backoff_sleep(1.0)

        assert 1.5 <= result <= 2.5

    def test_sleep_capped_at_max(self, service: _StubService) -> None:
        with patch.object(service._stop_event, "wait") as mock_wait:
            service._backoff_sleep(50.0)

            mock_wait.assert_called_once_with(timeout=30.0)

    def test_stop_event_interrupts(self, service: _StubService) -> None:
        service._stop_event.set()

        result = service._backoff_sleep(10.0)

        assert 15.0 <= result <= 25.0


class TestOnCleanDisconnect:
    """Tests for _on_clean_disconnect."""

    def test_resets_to_initial_backoff(self, service: _StubService) -> None:
        result = service._on_clean_disconnect()

        assert result == 1.0

    def test_increments_reconnect_count(self, service: _StubService) -> None:
        service._on_clean_disconnect()

        assert service._reconnect_count == 1

    def test_multiple_calls_increment(self, service: _StubService) -> None:
        service._on_clean_disconnect()
        service._on_clean_disconnect()

        assert service._reconnect_count == 2


class TestOnReconnectFailure:
    """Tests for _on_reconnect_failure."""

    def test_returns_current_backoff(self, service: _StubService) -> None:
        result = service._on_reconnect_failure(5.0)

        assert result == 5.0

    def test_increments_reconnect_count(self, service: _StubService) -> None:
        service._on_reconnect_failure(2.0)

        assert service._reconnect_count == 1

    def test_multiple_calls_increment(self, service: _StubService) -> None:
        service._on_reconnect_failure(2.0)
        service._on_reconnect_failure(4.0)

        assert service._reconnect_count == 2


class TestNextCorrelationId:
    """Tests for next_correlation_id."""

    def test_returns_string(self) -> None:
        result = ReconnectingServiceMixin.next_correlation_id()

        assert isinstance(result, str)

    def test_contains_prefix(self) -> None:
        result = ReconnectingServiceMixin.next_correlation_id(prefix="depth")

        assert result.startswith("depth-")

    def test_default_prefix(self) -> None:
        result = ReconnectingServiceMixin.next_correlation_id()

        assert result.startswith("ws-")

    def test_unique_ids(self) -> None:
        ids = {ReconnectingServiceMixin.next_correlation_id() for _ in range(100)}

        assert len(ids) == 100

    def test_format_has_timestamp_and_counter(self) -> None:
        result = ReconnectingServiceMixin.next_correlation_id(prefix="test")

        parts = result.split("-")
        assert len(parts) == 3
        assert parts[0] == "test"
        assert parts[1].isdigit()
        assert parts[2].isdigit()


class TestNoteMessageReceived:
    """Tests for _note_message_received."""

    def test_updates_last_message_at(self, service: _StubService) -> None:
        service._note_message_received()

        assert service._last_message_at is not None

    def test_increments_message_count(self, service: _StubService) -> None:
        service._note_message_received()

        assert service._message_count == 1

    def test_multiple_calls(self, service: _StubService) -> None:
        service._note_message_received()
        service._note_message_received()

        assert service._message_count == 2
