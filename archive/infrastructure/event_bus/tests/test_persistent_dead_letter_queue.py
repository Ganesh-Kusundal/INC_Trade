"""Tests for persistent dead-letter queue."""

from __future__ import annotations

from datetime import datetime, timezone

from infrastructure.event_bus.dead_letter_queue import DeadLetter
from infrastructure.event_bus.event_bus import DomainEvent
from infrastructure.event_bus.persistent_dead_letter_queue import (
    PersistentDeadLetterQueue,
    create_default_dead_letter_queue,
)


def _sample_letter(handler_id: str = "h1") -> DeadLetter:
    event = DomainEvent(
        event_type="TEST",
        timestamp=datetime.now(timezone.utc),
        payload={"k": "v"},
        symbol="RELIANCE",
        source="test",
    )
    return DeadLetter(
        event=event,
        handler_id=handler_id,
        error_type="RuntimeError",
        error_message="boom",
        failed_at=datetime.now(timezone.utc),
    )


def test_persistent_dlq_writes_sqlite(tmp_path):
    db = tmp_path / "dlq.sqlite"
    dlq = PersistentDeadLetterQueue(max_size=10, db_path=db)
    dlq.push(_sample_letter())
    assert db.exists()
    loaded = dlq.load_recent(limit=5)
    assert len(loaded) == 1
    assert loaded[0].handler_id == "h1"


def test_create_default_uses_memory_when_env_set(monkeypatch):
    monkeypatch.setenv("TRADEX_DLQ_MEMORY", "1")
    dlq = create_default_dead_letter_queue()
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue

    assert type(dlq) is DeadLetterQueue
