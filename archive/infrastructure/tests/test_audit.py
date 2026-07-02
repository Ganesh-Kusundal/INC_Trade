"""Tests for infrastructure.audit — audit trail system."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from application.audit import (
    AuditEvent,
    AuditLogger,
    FileAuditStore,
    MemoryAuditStore,
    audit_logger,
)
from infrastructure.correlation import with_correlation

# ---------------------------------------------------------------------------
# AuditEvent creation
# ---------------------------------------------------------------------------


def test_audit_event_creation() -> None:
    event = AuditEvent(
        event_id="evt-1",
        timestamp="2025-01-01T00:00:00+00:00",
        event_type="test.event",
        actor="user:1",
        action="create",
        resource_type="order",
        resource_id="ORD-1",
        details={"key": "val"},
        correlation_id="corr-1",
    )
    assert event.event_id == "evt-1"
    assert event.event_type == "test.event"
    assert event.actor == "user:1"
    assert event.details == {"key": "val"}
    assert event.ip_address is None


def test_audit_event_to_dict_roundtrip() -> None:
    event = AuditEvent(
        event_id="evt-rt",
        timestamp="2025-06-15T12:00:00+00:00",
        event_type="roundtrip",
        actor="svc",
        action="read",
        resource_type="portfolio",
        resource_id="P-1",
        details={"nested": {"a": 1}},
        correlation_id="c-1",
        ip_address="127.0.0.1",
    )
    d = event.to_dict()
    restored = AuditEvent.from_dict(d)
    assert restored == event


# ---------------------------------------------------------------------------
# MemoryAuditStore
# ---------------------------------------------------------------------------


def test_memory_store_append_and_count() -> None:
    store = MemoryAuditStore()
    assert store.count() == 0

    evt = AuditEvent(
        event_id="m1", timestamp="t", event_type="t1",
        actor="a", action="act", resource_type="r",
        resource_id="r1", details={}, correlation_id="c",
    )
    store.append(evt)
    assert store.count() == 1
    assert store.count("t1") == 1
    assert store.count("nonexistent") == 0


def test_memory_store_get() -> None:
    store = MemoryAuditStore()
    evt = AuditEvent(
        event_id="m2", timestamp="t", event_type="t1",
        actor="a", action="act", resource_type="r",
        resource_id="r1", details={}, correlation_id="c",
    )
    store.append(evt)
    assert store.get("m2") == evt
    assert store.get("missing") is None


def test_memory_store_query_filters() -> None:
    store = MemoryAuditStore()
    for i in range(5):
        store.append(AuditEvent(
            event_id=f"q{i}", timestamp=f"2025-01-0{i+1}T00:00:00+00:00",
            event_type="type_a" if i % 2 == 0 else "type_b",
            actor="alice" if i < 3 else "bob",
            action="act", resource_type="r", resource_id=f"r{i}",
            details={}, correlation_id="c",
        ))

    # Filter by event_type
    a_events = store.query(event_type="type_a")
    assert len(a_events) == 3
    assert all(e.event_type == "type_a" for e in a_events)

    # Filter by actor
    bob_events = store.query(actor="bob")
    assert len(bob_events) == 2
    assert all(e.actor == "bob" for e in bob_events)

    # Filter by time range
    time_filtered = store.query(
        from_time="2025-01-02T00:00:00+00:00",
        to_time="2025-01-04T00:00:00+00:00",
    )
    assert len(time_filtered) == 3

    # Limit
    limited = store.query(limit=2)
    assert len(limited) == 2


def test_memory_store_clear() -> None:
    store = MemoryAuditStore()
    for i in range(3):
        store.append(AuditEvent(
            event_id=f"c{i}", timestamp="t", event_type="t",
            actor="a", action="a", resource_type="r",
            resource_id="r", details={}, correlation_id="c",
        ))
    assert store.count() == 3
    store.clear()
    assert store.count() == 0


# ---------------------------------------------------------------------------
# FileAuditStore persistence
# ---------------------------------------------------------------------------


def test_file_store_persistence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        # Write events with first store instance
        store1 = FileAuditStore(path)
        for i in range(3):
            store1.append(AuditEvent(
                event_id=f"f{i}", timestamp=f"2025-01-0{i+1}T00:00:00+00:00",
                event_type="persist", actor="svc", action="write",
                resource_type="file", resource_id=f"f{i}",
                details={"seq": i}, correlation_id="c",
            ))

        # Read events with a fresh store instance
        store2 = FileAuditStore(path)
        assert store2.count() == 3
        evt = store2.get("f1")
        assert evt is not None
        assert evt.details == {"seq": 1}


def test_file_store_query() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit_query.jsonl"
        store = FileAuditStore(path)
        for i in range(4):
            store.append(AuditEvent(
                event_id=f"fq{i}", timestamp=f"2025-01-0{i+1}T00:00:00+00:00",
                event_type="e" if i % 2 == 0 else "o",
                actor="alice" if i < 2 else "bob",
                action="q", resource_type="r", resource_id="r",
                details={}, correlation_id="c",
            ))

        assert len(store.query(event_type="e")) == 2
        assert len(store.query(actor="alice")) == 2
        assert len(store.query(limit=1)) == 1


def test_file_store_clear() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit_clear.jsonl"
        store = FileAuditStore(path)
        store.append(AuditEvent(
            event_id="fc", timestamp="t", event_type="t",
            actor="a", action="a", resource_type="r",
            resource_id="r", details={}, correlation_id="c",
        ))
        assert store.count() == 1
        store.clear()
        assert store.count() == 0
        assert not path.exists()


# ---------------------------------------------------------------------------
# AuditLogger
# ---------------------------------------------------------------------------


def test_audit_logger_auto_fills_fields() -> None:
    store = MemoryAuditStore()
    logger = AuditLogger(store=store)

    event = logger.log(
        event_type="order.placed",
        actor="user:42",
        action="create",
        resource_type="order",
        resource_id="ORD-100",
        details={"symbol": "RELIANCE"},
    )

    assert event.event_id  # non-empty uuid
    assert "T" in event.timestamp  # ISO format
    assert event.event_type == "order.placed"
    assert event.actor == "user:42"
    assert event.action == "create"
    assert event.resource_type == "order"
    assert event.resource_id == "ORD-100"
    assert event.details == {"symbol": "RELIANCE"}
    assert store.count() == 1


def test_audit_logger_ip_address() -> None:
    store = MemoryAuditStore()
    logger = AuditLogger(store=store)

    event = logger.log(
        event_type="auth.login",
        actor="user:1",
        action="login",
        resource_type="session",
        resource_id="S-1",
        ip_address="10.0.0.1",
    )
    assert event.ip_address == "10.0.0.1"


# ---------------------------------------------------------------------------
# Correlation ID auto-injection
# ---------------------------------------------------------------------------


def test_correlation_id_auto_injection() -> None:
    store = MemoryAuditStore()
    logger = AuditLogger(store=store)

    with with_correlation("test-corr-123"):
        event = logger.log(
            event_type="test.corr",
            actor="svc",
            action="act",
            resource_type="r",
            resource_id="r1",
        )

    assert event.correlation_id == "test-corr-123"
    # Stored event should have the correlation ID
    stored = store.get(event.event_id)
    assert stored is not None
    assert stored.correlation_id == "test-corr-123"


def test_correlation_id_empty_when_no_context() -> None:
    store = MemoryAuditStore()
    logger = AuditLogger(store=store)

    event = logger.log(
        event_type="test.no.corr",
        actor="svc",
        action="act",
        resource_type="r",
        resource_id="r1",
    )
    # Without a correlation context, it falls back to empty string
    assert event.correlation_id == ""


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


def test_memory_store_thread_safety() -> None:
    store = MemoryAuditStore()
    errors: list[Exception] = []

    def writer(n: int) -> None:
        try:
            for i in range(50):
                store.append(AuditEvent(
                    event_id=f"t-{n}-{i}",
                    timestamp="t",
                    event_type="thread_test",
                    actor=f"actor-{n}",
                    action="write",
                    resource_type="r",
                    resource_id=f"r-{n}-{i}",
                    details={},
                    correlation_id="c",
                ))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert store.count() == 200
    assert store.count("thread_test") == 200


def test_file_store_thread_safety() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "thread_audit.jsonl"
        store = FileAuditStore(path)
        errors: list[Exception] = []

        def writer(n: int) -> None:
            try:
                for i in range(20):
                    store.append(AuditEvent(
                        event_id=f"ft-{n}-{i}",
                        timestamp="t",
                        event_type="ft",
                        actor=f"a{n}",
                        action="w",
                        resource_type="r",
                        resource_id="r",
                        details={},
                        correlation_id="c",
                    ))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert store.count() == 80


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------


def test_module_singleton_exists() -> None:
    assert isinstance(audit_logger, AuditLogger)
    assert isinstance(audit_logger.store, MemoryAuditStore)
