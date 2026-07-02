"""Persistent append-only event log for crash recovery.

Every ORDER_UPDATED, TRADE, POSITION_UPDATE and other critical domain event
can be appended to a daily JSONL file. On startup the OMS can replay the log
to rebuild order/position state up to the point of the crash.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
import os
import threading
import warnings
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from infrastructure.event_bus import DomainEvent

logger = logging.getLogger(__name__)

DEFAULT_EVENTS_DIR = Path("market_data/events")


# Domain types that may appear in event payloads and can be round-tripped.
_DOMAIN_TYPES: dict[str, type] = {}


def _register_domain_type(cls: type) -> type:
    key = f"{cls.__module__}.{cls.__qualname__}"
    _DOMAIN_TYPES[key] = cls
    return cls


def _serialize_value(value: Any) -> Any:
    """Best-effort serialization of domain objects and primitives."""
    if value is None:
        return None
    if isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if dataclasses.is_dataclass(value):
        cls = type(value)
        key = f"{cls.__module__}.{cls.__qualname__}"
        _register_domain_type(cls)
        result: dict[str, Any] = {"__type__": key}
        for field in dataclasses.fields(value):
            result[field.name] = _serialize_value(getattr(value, field.name))
        return result
    if isinstance(value, list | tuple):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return str(value)


def _deserialize_value(value: Any, expected_type: type | None = None) -> Any:
    """Reconstruct domain objects serialized by ``_serialize_value``."""
    import enum
    import typing

    if expected_type is not None:
        origin = typing.get_origin(expected_type)
        if origin is not None:
            expected_type = origin
        if isinstance(expected_type, type) and issubclass(expected_type, enum.Enum):
            try:
                return expected_type(value)
            except Exception:
                logger.debug("enum_value_parse_failed: %s=%s", expected_type, value)

    if isinstance(value, dict):
        if "__type__" in value:
            t = value["__type__"]
            if t == "decimal":
                return Decimal(value["value"])
            if t == "datetime":
                return datetime.fromisoformat(value["value"])
            if t == "date":
                return date.fromisoformat(value["value"])
            cls = _DOMAIN_TYPES.get(t)
            if cls is not None and dataclasses.is_dataclass(cls):
                try:
                    type_hints = typing.get_type_hints(cls)
                except Exception:
                    type_hints = {}
                kwargs = {
                    f.name: _deserialize_value(value.get(f.name), type_hints.get(f.name))
                    for f in dataclasses.fields(cls)
                    if f.init
                }
                return cls(**kwargs)
        return {k: _deserialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deserialize_value(v) for v in value]
    return value


def _deserialize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Deserialize a payload dict, reconstructing any embedded domain objects."""
    return {k: _deserialize_value(v) for k, v in payload.items()}


class EventLog:
    """Append-only JSONL event log with day-based rotation.

    Thread-safe. Writes are line-buffered and fsynced so a crash loses at most
    the last event. Reads replay events in insertion order.

    Append failures are **never silent**: every failure is logged at ERROR
    level and recorded in :attr:`append_errors` so operators can alert on it.
    """

    def __init__(self, events_dir: str | Path | None = None) -> None:
        if type(self) is EventLog:
            warnings.warn(
                "EventLog is deprecated; use BufferedEventLog instead. "
                "EventLog will be removed in a future version.",
                DeprecationWarning,
                stacklevel=2,
            )
        self._events_dir = Path(events_dir) if events_dir else DEFAULT_EVENTS_DIR
        self._events_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._current_file: Path | None = None
        self._current_handle: Any = None
        self.append_errors: int = 0  # public counter, never reset mid-run
        self._seen_ids: set[str] = set()  # idempotency guard

    @property
    def errors(self) -> int:
        """Number of append errors since process start."""
        return self.append_errors

    def _file_for(self, dt: datetime) -> Path:
        return self._events_dir / f"{dt.date().isoformat()}.jsonl"

    def _ensure_handle(self, dt: datetime) -> Any:
        target = self._file_for(dt)
        if self._current_file != target:
            if self._current_handle is not None:
                try:
                    self._current_handle.flush()
                    self._current_handle.close()
                except Exception as exc:
                    logger.warning("Error closing old event log: %s", exc)
            self._current_handle = open(target, "a", encoding="utf-8")
            self._current_file = target
        return self._current_handle

    def append(self, event: DomainEvent) -> None:
        """Append a single event to the current day's log.

        Raises
        ------
        OSError
            If the log file cannot be written. The exception is **not**
            swallowed — the bus will catch it, log it, and dead-letter the
            event. Callers that need to swallow failures (none in
            production) must do so explicitly.
        """
        # Idempotency guard: skip duplicate event_ids within this session.
        if event.event_id and event.event_id in self._seen_ids:
            return
        if event.event_id:
            self._seen_ids.add(event.event_id)

        record = {
            "event_type": event.event_type,
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source,
            "symbol": event.symbol,
            "payload": self._serialize_payload(event.payload),
            "correlation_id": event.correlation_id,
            "sequence_number": event.sequence_number,
        }
        line = json.dumps(record, separators=(",", ":"), default=str)
        with self._lock:
            handle = self._ensure_handle(event.timestamp)
            try:
                handle.write(line + "\n")
                handle.flush()
                with contextlib.suppress(OSError, ValueError):
                    os.fsync(handle.fileno())
                    # Some filesystems don't support fsync. The flush above
                    # is the best we can do.
            except (OSError, ValueError) as exc:
                self.append_errors += 1
                logger.exception(
                    "EventLog: failed to append %s to %s: %s",
                    event.event_type,
                    self._current_file,
                    exc,
                )
                # Re-raise so the EventBus can dead-letter the event.
                raise

    def _serialize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Best-effort serialization of domain objects in the payload."""
        return {k: _serialize_value(v) for k, v in payload.items()}

    def replay(
        self,
        since: datetime | None = None,
        event_types: set[str] | None = None,
        handler: Callable[[DomainEvent], None] | None = None,
    ) -> list[DomainEvent]:
        """Replay events from the log.

        Args:
            since: Only replay events at or after this time. If None, replay all.
            event_types: If provided, only replay these event types.
            handler: Optional callback invoked for each replayed event.

        Returns:
            List of replayed DomainEvent objects.
        """
        events: list[DomainEvent] = []
        files = sorted(self._events_dir.glob("*.jsonl"))
        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    # Read all lines up front so newly appended events during
                    # replay are not recursively processed.
                    lines = [line.strip() for line in f if line.strip()]
            except Exception as exc:
                logger.warning("Failed to read event log %s: %s", path, exc)
                continue
            for line in lines:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = datetime.fromisoformat(record["timestamp"])
                if since is not None and ts < since:
                    continue
                etype = record.get("event_type", "")
                if event_types is not None and etype not in event_types:
                    continue
                event = DomainEvent(
                    event_type=etype,
                    timestamp=ts,
                    payload=_deserialize_payload(record.get("payload", {})),
                    symbol=record.get("symbol"),
                    source=record.get("source", ""),
                    correlation_id=record.get("correlation_id"),
                    sequence_number=record.get("sequence_number", 0),
                )
                events.append(event)
                if handler is not None:
                    handler(event)
        return events

    def close(self) -> None:
        """Close the current log handle."""
        with self._lock:
            if self._current_handle is not None:
                try:
                    self._current_handle.flush()
                    self._current_handle.close()
                except Exception as exc:
                    logger.warning("Error closing event log: %s", exc)
                self._current_handle = None
                self._current_file = None

    def __enter__(self) -> EventLog:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# BufferedEventLog
# ---------------------------------------------------------------------------


class BufferedEventLog(EventLog):
    """EventLog with buffered writes for improved performance.

    Instead of fsync on every append, this class buffers events and flushes:
    - When buffer size >= flush_threshold (default 100 events)
    - When flush_interval seconds have passed (default 1 second)
    - On explicit flush() call
    - On close() or process exit

    Critical events (TRADE, ORDER_*) can use sync_mode=True for immediate fsync.

    Usage:
        log = BufferedEventLog(
            events_dir=Path("market_data/events"),
            flush_threshold=100,
            flush_interval=1.0,
        )
        log.append(event)  # Buffered
        log.append(event)  # Buffered
        log.flush()  # Explicit flush

        # Critical event: immediate fsync
        log.append(critical_event, sync_mode=True)

    Parameters
    ----------
    events_dir:
        Directory to store event log files.
    flush_threshold:
        Number of events to buffer before auto-flush (default 100).
    flush_interval:
        Maximum time between flushes in seconds (default 1.0).
    """

    def __init__(
        self,
        events_dir: Path = DEFAULT_EVENTS_DIR,
        flush_threshold: int = 100,
        flush_interval: float = 1.0,
    ) -> None:
        super().__init__(events_dir=events_dir)
        self._flush_threshold = flush_threshold
        self._flush_interval = flush_interval
        self._buffer: list[tuple[str, DomainEvent]] = []
        self._last_flush: datetime = datetime.now(timezone.utc)
        self._flush_count = 0

        # Register atexit handler for flush on process exit
        import atexit

        atexit.register(self._flush_on_exit)

    def append(self, event: DomainEvent, sync_mode: bool = False) -> None:
        """Append an event to the log (buffered).

        Parameters
        ----------
        event:
            DomainEvent to append.
        sync_mode:
            If True, flush immediately (for critical events like TRADE, ORDER).
        """
        with self._lock:
            # Serialize event
            record = {
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "payload": _serialize_value(event.payload),
                "symbol": event.symbol,
                "source": event.source,
                "correlation_id": event.correlation_id,
                "sequence_number": event.sequence_number,
            }
            line = json.dumps(record, ensure_ascii=False) + "\n"

            # Add to buffer
            self._buffer.append((line, event))

            # Check if we should flush
            should_flush = (
                sync_mode
                or len(self._buffer) >= self._flush_threshold
                or (datetime.now(timezone.utc) - self._last_flush).total_seconds()
                >= self._flush_interval
            )

            if should_flush:
                self._flush_locked()

    def _flush_locked(self) -> None:
        """Flush buffer to disk. Must be called with lock held."""
        if not self._buffer:
            return

        try:
            # Open file if not already open
            if self._current_handle is None:
                # Use timestamp from first buffered event to determine file
                first_event = self._buffer[0][1]
                self._ensure_handle(first_event.timestamp)

            # Write all buffered events
            for line, _ in self._buffer:
                self._current_handle.write(line)

            # Flush and fsync
            self._current_handle.flush()
            if hasattr(self._current_handle, "fileno"):
                with contextlib.suppress(OSError):
                    os.fsync(self._current_handle.fileno())
                    # Some file-like objects don't support fileno

            self._flush_count += 1
            self._last_flush = datetime.now(timezone.utc)
            self._buffer.clear()

        except Exception as exc:
            logger.exception("BufferedEventLog flush failed: %s", exc)
            # Don't clear buffer on failure, retry next time

    def flush(self) -> None:
        """Explicitly flush the buffer to disk."""
        with self._lock:
            self._flush_locked()

    def _flush_on_exit(self) -> None:
        """Flush buffer on process exit."""
        with contextlib.suppress(Exception):
            self.flush()

    def close(self) -> None:
        """Flush buffer and close the log."""
        with self._lock:
            self._flush_locked()
            super().close()
            logger.info(
                "BufferedEventLog closed (flushes=%d, buffer_size=%d)",
                self._flush_count,
                len(self._buffer),
            )

    def get_stats(self) -> dict[str, Any]:
        """Get buffer statistics.

        Returns
        -------
        dict:
            Statistics including buffer size, flush count, etc.
        """
        return {
            "buffer_size": len(self._buffer),
            "flush_count": self._flush_count,
            "flush_threshold": self._flush_threshold,
            "flush_interval": self._flush_interval,
            "last_flush": self._last_flush.isoformat(),
        }
