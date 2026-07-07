"""In-process event bus for distributing market-data and OMS events.

Thread-safe, lock-sharded event bus with handler failure isolation.
Handler failures are logged and never silently swallowed.

Usage::

    from brokers.infrastructure.event_bus import EventBus, DomainEvent

    bus = EventBus()
    token = bus.subscribe("TICK", lambda e: print(e.payload))
    bus.publish(DomainEvent.now("TICK", {"ltp": 100.0}, symbol="RELIANCE"))
    bus.unsubscribe(token)
"""

from __future__ import annotations

import itertools
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import replace

from brokers.domain.events import DomainEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], None]


class EventBus:
    """Thread-safe in-memory event bus with handler failure isolation.

    Design:
    - Events are immutable value objects.
    - Subscribers are snapshotted before iteration so a handler that mutates
      the subscription list cannot corrupt the dispatch loop.
    - Sequence numbering uses a lock-free ``itertools.count(1)`` (atomic
      under CPython GIL).
    - Handler failures are logged, never silently swallowed.
    """

    def __init__(self, fail_fast: bool = False) -> None:
        self._subscribers_lock = threading.Lock()
        self._sequence: itertools.count[int] = itertools.count(1)
        self._subscribers: dict[str, dict[str, EventHandler]] = {}
        self._fail_fast = fail_fast

    def subscribe(self, event_type: str, handler: EventHandler) -> str:
        """Subscribe to ``event_type``. Returns a token for unsubscribe."""
        token = uuid.uuid4().hex
        with self._subscribers_lock:
            self._subscribers.setdefault(event_type, {})[token] = handler
        return token

    def unsubscribe(self, token: str) -> bool:
        """Unsubscribe using the token returned by ``subscribe``."""
        with self._subscribers_lock:
            for handlers in self._subscribers.values():
                if token in handlers:
                    del handlers[token]
                    return True
        return False

    def subscriber_count(self, event_type: str | None = None) -> int:
        """Return the number of subscribers (for tests / diagnostics)."""
        with self._subscribers_lock:
            if event_type is not None:
                return len(self._subscribers.get(event_type, {}))
            return sum(len(h) for h in self._subscribers.values())

    def clear(self) -> None:
        """Remove all subscribers. Useful in tests."""
        with self._subscribers_lock:
            self._subscribers.clear()

    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all subscribers of ``event.event_type``.

        Assigns a sequence number if not already set.
        Handler failures are logged but do not stop other handlers.
        """
        # Assign sequence number (lock-free — atomic under GIL)
        if event.sequence_number == 0:
            seq_num = next(self._sequence)
            event = replace(event, sequence_number=seq_num)

        # Snapshot handlers to be lock-safe
        with self._subscribers_lock:
            handlers = list(self._subscribers.get(event.event_type, {}).items())

        for handler_id, handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                self._handle_failure(event, handler_id, exc)
                if self._fail_fast:
                    raise

    def _handle_failure(
        self, event: DomainEvent, handler_id: str, exc: BaseException
    ) -> None:
        """Log handler failure."""
        logger.warning(
            "EventBus: handler %s failed on %s (event_id=%s, symbol=%s): %s: %s",
            handler_id,
            event.event_type,
            event.event_id,
            event.symbol,
            type(exc).__name__,
            exc,
        )


__all__ = ["EventBus", "EventHandler"]
