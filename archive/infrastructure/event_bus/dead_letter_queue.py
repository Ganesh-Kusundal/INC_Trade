"""In-memory dead-letter queue for failed event handlers.

When a subscriber raises, the original event plus the exception are
captured here so operators can:

1. See *which* handler failed.
2. Replay the failed events once the bug is fixed.
3. Alert on dead-letter growth.

The queue is bounded to keep memory predictable; once full, the oldest
entry is dropped and ``dropped`` counter is incremented.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from domain.constants import DEAD_LETTER_QUEUE_MAX_SIZE
from infrastructure.event_bus.event_bus import DomainEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeadLetter:
    """A captured handler failure."""

    event: DomainEvent
    handler_id: str
    error_type: str
    error_message: str
    failed_at: datetime
    traceback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event.event_type,
            "event_id": self.event.event_id,
            "symbol": self.event.symbol,
            "source": self.event.source,
            "timestamp": self.event.timestamp.isoformat(),
            "handler_id": self.handler_id,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "failed_at": self.failed_at.isoformat(),
            "traceback": self.traceback,
        }


class DeadLetterQueue:
    """Bounded FIFO of handler failures.

    Parameters
    ----------
    max_size:
        Maximum number of dead letters to retain. Defaults to 10_000.
    on_drop:
        Optional callback invoked with the dropped entry when capacity is
        exceeded. Useful for shipping to a metrics pipeline.
    """

    def __init__(self, max_size: int = DEAD_LETTER_QUEUE_MAX_SIZE, on_drop=None) -> None:
        self._max_size = max_size
        self._lock = threading.RLock()
        self._items: deque[DeadLetter] = deque(maxlen=max_size)
        self._dropped = 0
        self._on_drop = on_drop

    def push(self, dead_letter: DeadLetter) -> bool:
        """Add a dead letter. Returns True if accepted, False if dropped due to capacity."""
        with self._lock:
            # deque(maxlen=...) handles eviction automatically; track drops
            pre_len = len(self._items)
            self._items.append(dead_letter)
            if len(self._items) < pre_len + 1:
                # deque evicted oldest entry because it was at capacity
                self._dropped += 1
                if self._on_drop is not None:
                    try:
                        self._on_drop(dead_letter)
                    except Exception as exc:
                        logger.debug("dead_letter_drop_callback_failed: %s", exc)
                return False
            return True

    def push_failure(
        self,
        event: DomainEvent,
        handler_id: str,
        exc: BaseException,
        traceback: str | None = None,
    ) -> None:
        """Convenience wrapper that builds and pushes a :class:`DeadLetter`."""
        self.push(
            DeadLetter(
                event=event,
                handler_id=handler_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
                failed_at=datetime.now(timezone.utc),
                traceback=traceback,
            )
        )

    def drain(self) -> list[DeadLetter]:
        """Atomically remove and return every dead letter."""
        with self._lock:
            items = list(self._items)
            self._items.clear()
            return items

    def peek(self, n: int = 20) -> list[DeadLetter]:
        with self._lock:
            return list(self._items)[-n:]

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def dropped(self) -> int:
        return self._dropped

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._items),
                "capacity": self._max_size,
                "dropped": self._dropped,
            }

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._dropped = 0
