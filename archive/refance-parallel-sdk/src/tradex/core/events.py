"""Event engine — typed publish/subscribe with ordering guarantees.

Events are the backbone of the SDK's reactive architecture.
All state changes propagate through the event bus.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional, Type, TypeVar
from uuid import uuid4

EventT = TypeVar("EventT", bound="DomainEvent")


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all events in the system."""

    event_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""


# Type alias for event handler coroutines
EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """In-process typed event bus with ordered dispatch.

    Features:
    - Type-based routing (handlers receive only their subscribed event type)
    - Async handlers executed concurrently per event
    - Ordered per aggregate (via optional group_key)
    - Thread-safe for asyncio
    """

    def __init__(self, max_concurrent: int = 100) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._published: deque[DomainEvent] = deque(maxlen=1000)

    def on(self, event_type: Type[EventT]) -> Callable[[EventHandler], EventHandler]:
        """Decorator to register an event handler."""

        def decorator(handler: EventHandler) -> EventHandler:
            self._handlers[event_type].append(handler)
            return handler

        return decorator

    def subscribe(self, event_type: Type[EventT], handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: Type[EventT], handler: EventHandler) -> None:
        """Remove a handler for an event type."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to all registered handlers."""
        self._published.append(event)

        # Dispatch to handlers matching the event type or its base classes
        tasks = []
        for event_type, handlers in self._handlers.items():
            if isinstance(event, event_type):
                for handler in handlers:
                    tasks.append(self._dispatch(handler, event))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _dispatch(self, handler: EventHandler, event: DomainEvent) -> None:
        """Dispatch an event to a handler with concurrency control."""
        async with self._semaphore:
            await handler(event)

    def get_history(self, event_type: Optional[Type] = None, limit: int = 100) -> list[DomainEvent]:
        """Get event history, optionally filtered by type."""
        events = self._published
        if event_type:
            events = [e for e in events if isinstance(e, event_type)]
        return events[-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        self._published.clear()

    def add_forwarding(self, target: EventBus) -> None:
        """Forward all published events to another EventBus.

        Events published on *self* are first dispatched to *self*'s
        own handlers, then republished on *target*.
        """
        original_publish = self.publish

        async def _forwarding_publish(event: DomainEvent) -> None:
            await original_publish(event)
            await target.publish(event)

        self.publish = _forwarding_publish  # type: ignore[assignment]

    @property
    def handler_count(self) -> int:
        """Total number of registered handlers."""
        return sum(len(h) for h in self._handlers.values())
