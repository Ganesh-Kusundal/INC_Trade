"""Tests for AsyncEventBusFactory — minimal coverage for startup fix."""

from domain.events.types import DomainEvent
from infrastructure.event_bus.event_bus import EventBus
from infrastructure.event_bus.factory import AsyncEventBusFactory


def test_factory_returns_event_bus():
    """Factory must return EventBus instance."""
    event_bus, config = AsyncEventBusFactory.create_from_config()
    assert isinstance(event_bus, EventBus)
    assert isinstance(config, dict)


def test_factory_respects_parameters():
    """Factory must accept and record parameters."""
    _event_bus, config = AsyncEventBusFactory.create_from_config(
        force_async=True, maxsize=5000,
    )
    assert config["force_async"] is True
    assert config["maxsize"] == 5000


def test_factory_creates_functional_bus():
    """Factory must create a working EventBus."""
    event_bus, _ = AsyncEventBusFactory.create_from_config()

    received = []
    token = event_bus.subscribe("TEST", lambda e: received.append(e))

    event = DomainEvent.now("TEST", {"data": "value"})
    event_bus.publish(event)

    assert len(received) == 1
    # EventBus assigns sequence_number, so compare type and payload
    assert received[0].event_type == "TEST"
    assert received[0].payload == {"data": "value"}

    event_bus.unsubscribe(token)


def test_factory_returns_tuple():
    """Factory must return 2-tuple (bus, config)."""
    result = AsyncEventBusFactory.create_from_config()
    assert isinstance(result, tuple)
    assert len(result) == 2
    event_bus, config = result
    assert isinstance(event_bus, EventBus)
    assert isinstance(config, dict)


def test_factory_config_contains_metadata():
    """Factory config must contain useful metadata."""
    _event_bus, config = AsyncEventBusFactory.create_from_config(
        force_async=True, maxsize=3000,
    )
    assert "created_by" in config
    assert config["created_by"] == "AsyncEventBusFactory"
    assert "bus_type" in config
    assert config["bus_type"] == "synchronous"
    assert "note" in config
    assert "force_async" in config
    assert "maxsize" in config
