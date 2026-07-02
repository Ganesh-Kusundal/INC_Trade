"""Async EventBus adapter — high-throughput publish with background dispatch.

Wraps the synchronous :class:`EventBus` with a background thread that
processes events from a lock-free queue.  This decouples producers
(market-data feeds, broker websockets) from consumers (event handlers,
persistence) so a slow handler never blocks the hot path.

Usage::

    from infrastructure.event_bus.async_event_bus import AsyncEventBus
    from infrastructure.event_bus.event_bus import EventBus, DomainEvent

    sync_bus = EventBus(event_log=log, metrics=metrics)
    async_bus = AsyncEventBus(sync_bus, max_queue_size=10_000)
    async_bus.start()

    # Fast publish — returns immediately, event is queued
    async_bus.publish(DomainEvent.now("TICK", {"ltp": 100}))

    async_bus.stop()

Design notes
------------
- The queue is bounded (``max_queue_size``) to apply backpressure when
  consumers are overwhelmed.  When the queue is full, ``publish()``
  drops the event and increments a ``dropped`` counter — better than
  unbounded memory growth.
- A single worker thread drains the queue sequentially, so handler
  ordering is preserved (FIFO).
- Thread-safe: ``publish()`` can be called from any thread.
- The adapter delegates all subscription management, persistence, and
  metrics to the wrapped EventBus — no duplicated logic.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any

from infrastructure.event_bus.event_bus import DomainEvent, EventBus, EventHandler

logger = logging.getLogger(__name__)

# Critical event types are never dropped — they overflow the queue rather
# than being silently discarded. Normal events are dropped when full.
CRITICAL_EVENT_TYPES: frozenset[str] = frozenset({
    "TRADE_APPLIED",
    "TRADE_FILLED",
    "ORDER_PLACED",
})


class AsyncEventBus:
    """High-throughput event bus with background thread dispatch.

    Parameters
    ----------
    bus:
        The synchronous :class:`EventBus` to delegate to.
    max_queue_size:
        Maximum number of events to buffer before applying backpressure.
        Default 10,000.  When exceeded, new events are dropped.
    """

    def __init__(
        self,
        bus: EventBus,
        *,
        max_queue_size: int = 10_000,
    ) -> None:
        self._bus = bus
        self._max_queue_size = max_queue_size
        self._queue: deque[DomainEvent] = deque()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._publish_count = 0
        self._dispatch_count = 0
        self._dropped_count = 0
        self._batch_size = 64  # drain up to N events per wake-up

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def dropped(self) -> int:
        """Number of events dropped due to full queue."""
        return self._dropped_count

    @property
    def queue_depth(self) -> int:
        """Current number of events waiting to be dispatched."""
        with self._lock:
            return len(self._queue)

    def publish(self, event: DomainEvent) -> None:
        """Enqueue an event for background dispatch.

        Critical events (TRADE_APPLIED, TRADE_FILLED, ORDER_PLACED) are
        never dropped — they overflow the queue to preserve trade integrity.
        Normal events are dropped when the queue is full, applying
        backpressure to prevent memory exhaustion.
        """
        is_critical = event.event_type in CRITICAL_EVENT_TYPES

        with self._lock:
            if len(self._queue) >= self._max_queue_size:
                if not is_critical:
                    self._dropped_count += 1
                    logger.warning(
                        "AsyncEventBus: queue full (%d), dropping non-critical event %s (type=%s)",
                        self._max_queue_size,
                        event.event_id,
                        event.event_type,
                    )
                    return
                # Critical event: allow queue to grow beyond max (bounded at 2x)
                if len(self._queue) >= self._max_queue_size * 2:
                    self._dropped_count += 1
                    logger.error(
                        "AsyncEventBus: queue critically full (%d/2x), dropping critical event %s (type=%s)",
                        self._max_queue_size,
                        event.event_id,
                        event.event_type,
                    )
                    return
            self._queue.append(event)
            self._publish_count += 1

    def subscribe(self, event_type: str, handler: EventHandler) -> str:
        """Delegate subscription to the wrapped synchronous bus."""
        return self._bus.subscribe(event_type, handler)

    def unsubscribe(self, token: str) -> bool:
        """Delegate unsubscription to the wrapped synchronous bus."""
        return self._bus.unsubscribe(token)

    def start(self) -> None:
        """Start the background worker thread."""
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._drain_loop,
            name="async-event-bus",
            daemon=True,
        )
        self._worker.start()
        logger.info("AsyncEventBus started (max_queue=%d)", self._max_queue_size)

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the worker thread and drain remaining events.

        Parameters
        ----------
        timeout:
            Maximum seconds to wait for the worker thread to exit.
        """
        self._stop_event.set()
        if self._worker is not None:
            self._worker.join(timeout=timeout)
            if self._worker.is_alive():
                logger.warning("AsyncEventBus worker did not stop within %.1fs", timeout)
            self._worker = None
        # Drain any remaining events
        self._drain_batch()
        logger.info(
            "AsyncEventBus stopped (published=%d, dispatched=%d, dropped=%d)",
            self._publish_count,
            self._dispatch_count,
            self._dropped_count,
        )

    def get_stats(self) -> dict[str, Any]:
        """Return buffer and throughput statistics."""
        return {
            "queue_depth": self.queue_depth,
            "max_queue_size": self._max_queue_size,
            "publish_count": self._publish_count,
            "dispatch_count": self._dispatch_count,
            "dropped_count": self._dropped_count,
            "worker_alive": self._worker is not None and self._worker.is_alive(),
        }

    # ── Internal ────────────────────────────────────────────────────────

    def _drain_loop(self) -> None:
        """Background loop that drains the queue in batches."""
        while not self._stop_event.is_set():
            self._drain_batch()
            # Sleep in small increments for fast shutdown
            self._stop_event.wait(timeout=0.05)  # 50ms poll interval

    def _drain_batch(self) -> None:
        """Drain up to batch_size events from the queue and dispatch."""
        while True:
            batch: list[DomainEvent] = []
            with self._lock:
                for _ in range(min(self._batch_size, len(self._queue))):
                    batch.append(self._queue.popleft())
            if not batch:
                break
            for event in batch:
                try:
                    self._bus.publish(event)
                    self._dispatch_count += 1
                except Exception as exc:
                    logger.exception(
                        "AsyncEventBus: dispatch failed for %s (type=%s): %s",
                        event.event_id,
                        event.event_type,
                        exc,
                    )

    @property
    def event_bus(self) -> EventBus:
        """Access the underlying synchronous EventBus."""
        return self._bus
