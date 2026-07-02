"""Tests for infrastructure.async_event_bus — priority-based event dropping (Fix #14)."""

from __future__ import annotations

from infrastructure.event_bus.async_event_bus import CRITICAL_EVENT_TYPES, AsyncEventBus
from infrastructure.event_bus.event_bus import DomainEvent, EventBus


def _make_bus(max_queue_size: int = 5) -> AsyncEventBus:
    sync_bus = EventBus()
    return AsyncEventBus(sync_bus, max_queue_size=max_queue_size)


class TestPriorityEventDropping:
    """Fix #14: critical events must not be dropped when queue is full."""

    def test_critical_event_types_defined(self):
        assert "TRADE_APPLIED" in CRITICAL_EVENT_TYPES
        assert "TRADE_FILLED" in CRITICAL_EVENT_TYPES
        assert "ORDER_PLACED" in CRITICAL_EVENT_TYPES

    def test_normal_event_dropped_when_queue_full(self):
        """Normal events are dropped when queue exceeds max size."""
        bus = _make_bus(max_queue_size=2)
        bus.publish(DomainEvent.now("TICK", {"a": 1}))
        bus.publish(DomainEvent.now("TICK", {"b": 2}))
        bus.publish(DomainEvent.now("TICK", {"c": 3}))
        assert bus.dropped == 1
        assert bus.queue_depth == 2

    def test_critical_event_not_dropped_when_queue_full(self):
        """Critical events overflow the queue instead of being dropped."""
        bus = _make_bus(max_queue_size=2)
        bus.publish(DomainEvent.now("TICK", {"a": 1}))
        bus.publish(DomainEvent.now("TICK", {"b": 2}))
        bus.publish(DomainEvent.now("TRADE_APPLIED", {"order_id": "O1"}))
        assert bus.dropped == 0
        assert bus.queue_depth == 3

    def test_critical_event_dropped_at_2x_limit(self):
        """Critical events are dropped when queue reaches 2x max."""
        bus = _make_bus(max_queue_size=2)
        bus.publish(DomainEvent.now("TICK", {"a": 1}))   # len=1
        bus.publish(DomainEvent.now("TICK", {"b": 2}))   # len=2
        bus.publish(DomainEvent.now("TRADE_APPLIED", {"c": 3}))  # overflow len=3
        bus.publish(DomainEvent.now("TRADE_FILLED", {"d": 4}))   # overflow len=4
        bus.publish(DomainEvent.now("ORDER_PLACED", {"e": 5}))   # dropped at 2x=4
        assert bus.dropped == 1
        assert bus.queue_depth == 4

    def test_non_critical_dropped_critical_kept(self):
        """Mix of normal and critical: normal dropped, critical kept."""
        bus = _make_bus(max_queue_size=1)
        bus.publish(DomainEvent.now("TICK", {"a": 1}))
        bus.publish(DomainEvent.now("TICK", {"b": 2}))
        bus.publish(DomainEvent.now("ORDER_PLACED", {"c": 3}))
        assert bus.dropped == 1
        assert bus.queue_depth == 2
