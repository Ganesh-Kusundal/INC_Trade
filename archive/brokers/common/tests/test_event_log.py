"""Tests for the persistent EventLog.

Covers the Phase 1 hardening: append must raise on filesystem failure
(no silent swallow) and the error counter must increment so the
alerting layer can observe it.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from infrastructure.event_bus import DomainEvent, EventBus
from infrastructure.event_log import EventLog


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "events"


def test_append_and_replay(log_dir: Path) -> None:
    log = EventLog(events_dir=log_dir)
    event = DomainEvent.now("ORDER_PLACED", {"order_id": "O1"}, symbol="RELIANCE", source="test")
    log.append(event)
    log.close()

    replayed = log.replay()
    assert len(replayed) == 1
    assert replayed[0].event_type == "ORDER_PLACED"
    assert replayed[0].payload["order_id"] == "O1"


def test_event_log_filters_by_type(log_dir: Path) -> None:
    log = EventLog(events_dir=log_dir)
    log.append(DomainEvent.now("ORDER_PLACED", {"order_id": "O1"}))
    log.append(DomainEvent.now("TRADE", {"trade_id": "T1"}))
    log.close()

    replayed = log.replay(event_types={"TRADE"})
    assert len(replayed) == 1
    assert replayed[0].event_type == "TRADE"


def test_event_log_filters_by_since(log_dir: Path) -> None:
    log = EventLog(events_dir=log_dir)
    old = DomainEvent.now("ORDER_PLACED", {"order_id": "O1"})
    # Manually create an older event to test filtering
    older = DomainEvent(
        event_type="ORDER_PLACED",
        timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
        payload={"order_id": "O0"},
    )
    log.append(older)
    log.append(old)
    log.close()

    replayed = log.replay(since=datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert len(replayed) == 1
    assert replayed[0].payload["order_id"] == "O1"


def test_event_bus_persists_events(log_dir: Path) -> None:
    log = EventLog(events_dir=log_dir)
    bus = EventBus(event_log=log)
    bus.publish(DomainEvent.now("ORDER_PLACED", {"order_id": "O1"}, symbol="RELIANCE"))
    log.close()

    replayed = log.replay()
    assert len(replayed) == 1
    assert replayed[0].event_type == "ORDER_PLACED"


def test_event_log_rotation_by_day(log_dir: Path) -> None:
    log = EventLog(events_dir=log_dir)
    yesterday = DomainEvent(
        event_type="ORDER_PLACED",
        timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        payload={"order_id": "O1"},
    )
    today = DomainEvent(
        event_type="ORDER_PLACED",
        timestamp=datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc),
        payload={"order_id": "O2"},
    )
    log.append(yesterday)
    log.append(today)
    log.close()

    files = sorted(log_dir.glob("*.jsonl"))
    assert len(files) == 2


def test_replay_handler_invoked(log_dir: Path) -> None:
    log = EventLog(events_dir=log_dir)
    log.append(DomainEvent.now("TRADE", {"trade_id": "T1"}))
    log.close()

    handled = []
    log.replay(handler=lambda e: handled.append(e))
    assert len(handled) == 1
    assert handled[0].event_type == "TRADE"


# ── Phase 1 hardening ──────────────────────────────────────────────────────


def test_append_raises_on_filesystem_error(log_dir: Path) -> None:
    log = EventLog(events_dir=log_dir)
    with patch.object(log, "_ensure_handle") as m:
        m.return_value.write.side_effect = OSError("disk full")
        with pytest.raises(OSError):
            log.append(DomainEvent.now("TICK", {"ltp": 1.0}))
    assert log.append_errors == 1
    assert log.errors == 1


def test_append_error_counter_increments_on_repeated_failures(
    log_dir: Path,
) -> None:
    log = EventLog(events_dir=log_dir)
    with patch.object(log, "_ensure_handle") as m:
        m.return_value.write.side_effect = OSError("disk full")
        for _ in range(3):
            with pytest.raises(OSError):
                log.append(DomainEvent.now("TICK", {"ltp": 1.0}))
    assert log.append_errors == 3


def test_append_does_not_silently_swallow_errors(
    log_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    log = EventLog(events_dir=log_dir)
    with patch.object(log, "_ensure_handle") as m:
        m.return_value.write.side_effect = OSError("disk full")
        import logging as _logging

        with caplog.at_level(_logging.ERROR), pytest.raises(OSError):
            log.append(DomainEvent.now("TICK", {"ltp": 1.0}))
    assert any("disk full" in r.message for r in caplog.records)


def test_concurrent_appends_are_thread_safe(log_dir: Path) -> None:
    log = EventLog(events_dir=log_dir)

    def submit(i: int) -> None:
        log.append(DomainEvent.now("TICK", {"i": i}))

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(submit, range(100)))
    log.close()

    files = list(log_dir.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().splitlines()
    assert len(lines) == 100
    assert log.append_errors == 0
