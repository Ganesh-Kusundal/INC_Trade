"""Event publisher port — domain services depend on this instead of concrete EventBus.

This protocol captures the publish/subscribe contract that every event bus
implementation (synchronous EventBus, AsyncEventBus, or test doubles) must
satisfy.  Domain-adjacent services (OrderManager, PositionManager, broker
adapters, analytics engines) depend on this protocol rather than importing
the concrete :class:`~infrastructure.event_bus.EventBus`.

Usage::

    from domain.ports import EventPublisher
    from domain.events import DomainEvent

    class MyService:
        def __init__(self, event_bus: EventPublisher | None = None):
            self._event_bus = event_bus

        def notify(self, order: Order) -> None:
            if self._event_bus is not None:
                self._event_bus.publish(
                    DomainEvent.now("ORDER_PLACED", {"order": order})
                )
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventPublisher(Protocol):
    """Minimal publish/subscribe port for domain events."""

    def publish(self, event: Any) -> None:
        """Publish a domain event to all subscribers.

        The *event* parameter is a :class:`~infrastructure.event_bus.DomainEvent`
        (or any duck-typed equivalent).  Using ``Any`` avoids a concrete import
        from the infrastructure layer.
        """
        ...

    def subscribe(self, event_type: str, handler: Any) -> None:
        """Register an event handler."""
        ...


__all__ = ["EventPublisher"]
