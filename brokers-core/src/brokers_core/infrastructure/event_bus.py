"""Thread-safe synchronous in-process event bus."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable

from brokers_core.domain.events import DomainEvent, resolve_event_type
from brokers_core.ports.event_publisher import EventPublisherPort

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], None]


class EventBus(EventPublisherPort):
    """Minimal event bus for broker adapter → application notifications."""

    def __init__(self) -> None:
        self._handlers: dict[str, dict[str, EventHandler]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, handler: EventHandler) -> str:
        token = str(uuid.uuid4())
        with self._lock:
            self._handlers.setdefault(event_type, {})[token] = handler
        return token

    def unsubscribe(self, token: str) -> None:
        with self._lock:
            for handlers in self._handlers.values():
                handlers.pop(token, None)

    def publish(self, event: DomainEvent) -> None:
        with self._lock:
            handlers = list(self._handlers.get(resolve_event_type(event), {}).values())
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.warning(
                    "event_handler_failed",
                    extra={
                        "event_type": resolve_event_type(event),
                        "error": str(exc),
                        "source": event.source,
                    },
                )
