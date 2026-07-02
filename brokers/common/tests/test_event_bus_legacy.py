"""Tests for the lock-safe EventBus."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from infrastructure.event_bus import DomainEvent, EventBus


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def test_subscribe_and_publish(bus: EventBus) -> None:
    received = []
    bus.subscribe("TICK", lambda e: received.append(e))
    event = DomainEvent.now("TICK", {"ltp": 100.0}, symbol="RELIANCE")
    bus.publish(event)
    assert len(received) == 1
    assert received[0].event_type == "TICK"


def test_unsubscribe(bus: EventBus) -> None:
    received = []
    token = bus.subscribe("TICK", lambda e: received.append(e))
    bus.unsubscribe(token)
    bus.publish(DomainEvent.now("TICK", {"ltp": 100.0}))
    assert len(received) == 0


def test_publish_is_isolated(bus: EventBus) -> None:
    received = []
    bus.subscribe("TICK", lambda e: received.append(e))
    bus.publish(DomainEvent.now("DEPTH", {"bids": []}))
    assert len(received) == 0


def test_handler_error_does_not_stop_others(bus: EventBus) -> None:
    received = []
    bus.subscribe("TICK", lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.subscribe("TICK", lambda e: received.append(e))
    bus.publish(DomainEvent.now("TICK", {"ltp": 100.0}))
    assert len(received) == 1


def test_concurrent_publish_subscribe(bus: EventBus) -> None:
    received = []
    lock = threading.Lock()

    def handler(event: DomainEvent) -> None:
        with lock:
            received.append(event)

    bus.subscribe("TICK", handler)

    def publish(i: int) -> None:
        bus.publish(DomainEvent.now("TICK", {"i": i}))

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(publish, range(100)))

    assert len(received) == 100


def test_subscribe_during_publish_is_safe(bus: EventBus) -> None:
    received = []

    def handler(event: DomainEvent) -> None:
        received.append(event)
        if len(received) == 1:
            bus.subscribe("TICK", lambda e: received.append(e))

    bus.subscribe("TICK", handler)
    bus.publish(DomainEvent.now("TICK", {"ltp": 100.0}))
    bus.publish(DomainEvent.now("TICK", {"ltp": 101.0}))
    # Second publish should reach both subscribers.
    assert len(received) >= 3


def test_subscriber_count(bus: EventBus) -> None:
    assert bus.subscriber_count("TICK") == 0
    t1 = bus.subscribe("TICK", lambda e: None)
    t2 = bus.subscribe("TICK", lambda e: None)
    bus.subscribe("DEPTH", lambda e: None)
    assert bus.subscriber_count("TICK") == 2
    assert bus.subscriber_count() == 3
    bus.unsubscribe(t1)
    assert bus.subscriber_count("TICK") == 1
    bus.unsubscribe(t2)
    assert bus.subscriber_count("TICK") == 0
