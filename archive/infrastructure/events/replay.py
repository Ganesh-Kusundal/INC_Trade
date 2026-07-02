"""Event replay store for recording and replaying domain events.

Provides in-memory (and optionally file-backed) storage of events
with timestamp-based range queries and event type filtering.
Integrates with EventMetrics for replay observability.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.event_bus.event_bus import DomainEvent
from infrastructure.observability.event_metrics import EventMetrics


@dataclass(frozen=True)
class StoredEvent:
    """An event with its wall-clock recording timestamp."""

    event: DomainEvent
    recorded_at: float  # time.time() when recorded


class EventReplayStore:
    """Thread-safe in-memory event store with optional file backing.

    Usage:
        store = EventReplayStore(metrics=metrics)
        store.record(event)

        for e in store.replay(from_timestamp=t1, to_timestamp=t2):
            bus.publish(e)

    Parameters:
        metrics: Optional EventMetrics for counting replayed events.
        file_path: Optional Path for file-backed persistence.
    """

    def __init__(
        self,
        metrics: EventMetrics | None = None,
        file_path: Path | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._events: list[StoredEvent] = []
        self._metrics = metrics
        self._file_path = file_path

        # Load from file if it exists
        if file_path is not None and file_path.exists():
            self._load_from_file()

    def record(self, event: DomainEvent) -> None:
        """Append an event with the current wall-clock timestamp."""
        stored = StoredEvent(event=event, recorded_at=time.time())
        with self._lock:
            self._events.append(stored)
        if self._file_path is not None:
            self._append_to_file(stored)

    def replay(
        self,
        from_timestamp: float | None = None,
        to_timestamp: float | None = None,
        event_type: str | None = None,
    ) -> Iterator[DomainEvent]:
        """Yield events within the given time range and optional type filter.

        Events are yielded in recording order (FIFO).

        Args:
            from_timestamp: Inclusive lower bound (time.time() epoch).
                            If None, no lower bound.
            to_timestamp: Inclusive upper bound (time.time() epoch).
                          If None, no upper bound.
            event_type: If provided, only yield events matching this type.
        """
        with self._lock:
            snapshot = list(self._events)

        count = 0
        for stored in snapshot:
            # Time range filter
            if from_timestamp is not None and stored.recorded_at < from_timestamp:
                continue
            if to_timestamp is not None and stored.recorded_at > to_timestamp:
                continue
            # Event type filter
            if event_type is not None and stored.event.event_type != event_type:
                continue

            count += 1
            yield stored.event

        # Count replayed events in metrics
        if self._metrics is not None and count > 0:
            self._metrics.add_timestamped_counter(
                "event_replay", "replayed", by=count
            )

    def clear(self) -> None:
        """Wipe all stored events."""
        with self._lock:
            self._events.clear()
        if self._file_path is not None and self._file_path.exists():
            self._file_path.unlink()

    def count(self, event_type: str | None = None) -> int:
        """Return the number of stored events, optionally filtered by type."""
        with self._lock:
            if event_type is not None:
                return sum(
                    1 for s in self._events if s.event.event_type == event_type
                )
            return len(self._events)

    # ── File persistence helpers ───────────────────────────────────────

    def _append_to_file(self, stored: StoredEvent) -> None:
        """Append a single event to the backing file."""
        record = {
            "recorded_at": stored.recorded_at,
            "event": {
                "event_type": stored.event.event_type,
                "timestamp": stored.event.timestamp.isoformat(),
                "payload": stored.event.payload,
                "symbol": stored.event.symbol,
                "source": stored.event.source,
                "event_id": stored.event.event_id,
                "correlation_id": stored.event.correlation_id,
                "sequence_number": stored.event.sequence_number,
            },
        }
        with self._file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _load_from_file(self) -> None:
        """Load events from the backing file into memory."""
        if self._file_path is None or not self._file_path.exists():
            return
        with self._file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                ev_data = record["event"]
                ts = datetime.fromisoformat(ev_data["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                event = DomainEvent(
                    event_type=ev_data["event_type"],
                    timestamp=ts,
                    payload=ev_data.get("payload", {}),
                    symbol=ev_data.get("symbol"),
                    source=ev_data.get("source"),
                    event_id=ev_data.get("event_id", ""),
                    correlation_id=ev_data.get("correlation_id"),
                    sequence_number=ev_data.get("sequence_number", 0),
                )
                self._events.append(
                    StoredEvent(event=event, recorded_at=record["recorded_at"])
                )
