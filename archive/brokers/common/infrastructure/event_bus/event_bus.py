"""Lock-safe event bus for distributing market-data and OMS events.

Design notes
------------
- Events are immutable value objects.
- Subscribers are snapshotted before iteration so a handler that mutates the
  subscription list cannot corrupt the dispatch loop.
- Sequence numbering uses a lock-free ``itertools.count(1)`` (atomic under CPython GIL).
- Subscriber mutations/snapshots use a dedicated ``threading.Lock`` (not RLock)
  to minimise contention on the publish hot-path.
- The bus is intentionally synchronous; asynchronous consumers should push
  events into their own queue from the handler.
- **Handler failures are NEVER silently swallowed.** Each failure is:

  1. Logged at WARNING level with the event type, handler id, and error.
  2. Counted in :class:`EventMetrics` under
     ``(event_type, handler_error:<exception_type>)``.
  3. Captured in the attached :class:`DeadLetterQueue` for later replay.

  A misbehaving handler does not stop other subscribers from running.
"""

from __future__ import annotations

import itertools
import logging
import threading
import traceback
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from domain.events import DomainEvent

if TYPE_CHECKING:
    from domain.ports.observability import AlertingEnginePort, EventMetricsPort
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue

logger = logging.getLogger(__name__)


EventHandler = Callable[[DomainEvent], None]


class EventBus:
    """Thread-safe in-memory event bus with mandatory failure observability.

    Added replay_mode for deterministic replay.
    When replay_mode=True:
    - Auto-persistence is disabled (no recursive writes to EventLog)
    - Events use original timestamps instead of datetime.now()
    - Sequence numbers are preserved for total ordering

    Alerting Integration
    --------------------
    When an ``alerting_engine`` is provided, the bus starts a background
    thread that periodically evaluates alert rules (default every 10 seconds).
    All metrics increments use timestamped counters to enable rate-based
    alerting.

    Example::

        metrics = EventMetrics()
        dlq = DeadLetterQueue()
        engine = AlertingEngine(metrics)
        bus = EventBus(metrics=metrics, dead_letter_queue=dlq, alerting_engine=engine)
        token = bus.subscribe("TICK", lambda e: print(e.payload))
        bus.publish(DomainEvent.now("TICK", {"ltp": 100.0}, symbol="RELIANCE"))
        bus.unsubscribe(token)
        bus.stop_alerting()  # Clean shutdown

    Parameters
    ----------
    event_log:
        Optional append-only :class:`EventLog` used for crash recovery.
    dead_letter_queue:
        Optional :class:`DeadLetterQueue` that receives failed handler
        invocations. **Required in production** — the bus will warn loudly
        if it is missing and a handler raises.
    metrics:
        Optional :class:`EventMetrics` that the bus increments for every
        publish / dispatch / failure. Required in production.
    logging_enabled:
        If True (default), the bus forwards every event to the attached
        ``event_log`` before dispatch. Used during crash-recovery replay
        to suppress recursive log writes.
    fail_fast:
        If True, the bus re-raises handler exceptions after capturing them.
        Defaults to False (the bus never stops the dispatch loop on a bad
        handler) but tests use True to assert on failures.
    replay_mode:
        If True, disables auto-persistence and preserves original
        event timestamps for deterministic replay.
    alerting_engine:
        Optional :class:`AlertingEngine` for threshold-based alerting.
        When provided, a background thread evaluates alert rules every
        ``alerting_interval_seconds`` seconds.
    alerting_interval_seconds:
        Interval between alert evaluations (default 10 seconds).
    """

    def __init__(
        self,
        event_log: Any | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
        metrics: EventMetricsPort | None = None,
        logging_enabled: bool = True,
        fail_fast: bool = False,
        replay_mode: bool = False,
        alerting_engine: AlertingEnginePort | None = None,
        alerting_interval_seconds: float = 10.0,
        max_processed_events: int = 10000,  # Idempotency cache size
    ) -> None:
        # Lock sharding — separate lightweight Lock for subscriber
        # management from the (now lock-free) sequence counter.
        # RLock -> Lock downgrade is safe: no call-site requires reentrancy.
        self._subscribers_lock = threading.Lock()
        self._sequence: itertools.count[int] = itertools.count(1)
        self._subscribers: dict[str, dict[str, EventHandler]] = {}
        self._event_log = event_log
        self._dead_letter_queue = dead_letter_queue
        self._metrics = metrics
        self._logging_enabled = logging_enabled
        self._fail_fast = fail_fast
        self._replay_mode = replay_mode
        # self._sequence_counter replaced by lock-free self._sequence
        self._alerting_engine = alerting_engine
        self._alerting_interval = alerting_interval_seconds
        self._alerting_thread: threading.Thread | None = None
        self._alerting_stop = threading.Event()

        # Idempotency - track processed event_ids to prevent duplicate processing
        self._processed_events: deque[str] = deque(maxlen=max_processed_events)
        self._processed_event_ids: set[str] = set()
        self._idempotency_lock = threading.Lock()

        # Start background alerting thread if engine is provided.
        if self._alerting_engine is not None:
            self._start_alerting()

    @property
    def replay_mode(self) -> bool:
        """True if bus is in replay mode."""
        return self._replay_mode

    def set_replay_mode(self, enabled: bool) -> None:
        """Enable or disable replay mode.

        This is the public API for mutating replay_mode.  All callers
        (including TradingContext._replay_log_into_oms) must use this
        method instead of touching ``_replay_mode`` directly.
        """
        self._replay_mode = enabled

    @property
    def logging_enabled(self) -> bool:
        """True if event persistence to the event log is enabled."""
        return self._logging_enabled

    def set_logging_enabled(self, enabled: bool) -> None:
        """Enable or disable event persistence to the event log.

        During crash-recovery replay this is used to suppress recursive
        log writes that would corrupt the event stream.  All callers
        (including TradingContext._replay_log_into_oms) must use this
        method instead of touching ``_logging_enabled`` directly.

        Args:
            enabled: True to persist events, False to suppress persistence.
        """
        self._logging_enabled = enabled

    @property
    def alerting_engine(self) -> AlertingEnginePort | None:
        """The alerting engine instance, if configured."""
        return self._alerting_engine

    def _start_alerting(self) -> None:
        """Start the background alerting evaluation thread."""
        if self._alerting_engine is None:
            return

        self._alerting_stop.clear()
        self._alerting_thread = threading.Thread(
            target=self._alerting_loop,
            name="EventBus-Alerting",
            daemon=True,
        )
        self._alerting_thread.start()
        logger.info(
            "EventBus alerting started (interval=%.1fs)",
            self._alerting_interval,
        )

    def _alerting_loop(self) -> None:
        """Background loop that periodically evaluates alert rules."""
        while not self._alerting_stop.is_set():
            try:
                if self._alerting_engine is not None:
                    alerts = self._alerting_engine.evaluate_all()
                    if alerts:
                        logger.info(
                            "EventBus alerting: %d alert(s) fired",
                            len(alerts),
                        )
            except Exception as exc:
                logger.exception(
                    "EventBus alerting evaluation failed: %s",
                    exc,
                )
            # Sleep in small increments to allow fast shutdown.
            self._alerting_stop.wait(self._alerting_interval)

    def stop_alerting(self) -> None:
        """Stop the background alerting thread.

        Call this during graceful shutdown to ensure the thread exits cleanly.
        """
        if self._alerting_thread is None:
            return

        self._alerting_stop.set()
        self._alerting_thread.join(timeout=5.0)
        if self._alerting_thread.is_alive():
            logger.warning("EventBus alerting thread did not stop within timeout")
        else:
            logger.info("EventBus alerting stopped")

    # ── Subscription management ────────────────────────────────────────────

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

    # ── Internal helpers ──────────────────────────────────────────────────

    def _prepare_event(self, event: DomainEvent) -> DomainEvent:
        """Create a new event with infrastructure fields injected immutably.

        This is the copy-on-publish pattern: instead of mutating the frozen
        DomainEvent via object.__setattr__, we use dataclasses.replace() to
        create a new instance with injected correlation_id and sequence_number.

        Returns the original event if no changes are needed (optimization).
        """
        replacements: dict[str, Any] = {}

        # Inject correlation_id from thread-local context if missing
        if event.correlation_id is None:
            from infrastructure.correlation import get_current_correlation_id
            cid = get_current_correlation_id()
            if cid is not None:
                replacements["correlation_id"] = cid

        # Assign sequence number in live mode only
        # Lock-free — ``next(itertools.count(1))`` is atomic under
        # the CPython GIL (single bytecode: CALL_FUNCTION on a C-level iterator).
        if not self._replay_mode:
            seq_num = next(self._sequence)
            if event.sequence_number == 0:
                replacements["sequence_number"] = seq_num
        # Replay mode: preserve original sequence_number (no assignment)

        # Optimization: return original if no replacements needed
        if not replacements:
            return event

        return replace(event, **replacements)

    # ── Idempotency ─────────────────────────────────────────────────────

    def _is_duplicate_event(self, event: DomainEvent) -> bool:
        """Check if event has already been processed (idempotency guard).

        Under at-least-once delivery (websockets, network retries),
        duplicate events can arrive. This method tracks processed event_ids
        in a bounded LRU cache (deque) to prevent double-processing.

        Returns True if duplicate (should be skipped), False if new.
        """
        event_id = event.event_id
        if not event_id:
            return False  # No ID, can't check - allow through

        with self._idempotency_lock:
            if event_id in self._processed_event_ids:
                return True  # Duplicate

            # Mark as processed
            self._processed_event_ids.add(event_id)
            self._processed_events.append(event_id)

            # Evict oldest if cache is full (handled by deque maxlen)
            if len(self._processed_events) == self._processed_events.maxlen:
                oldest = self._processed_events.popleft()
                self._processed_event_ids.discard(oldest)

            return False

    # ── Publishing ────────────────────────────────────────────────────────

    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all subscribers of ``event.event_type``.

        If the event has no ``correlation_id``, the current thread's
        active correlation ID (set via
        :func:`infrastructure.correlation.with_correlation`) is injected
        before dispatch.  This ensures every published event carries a
        traceable ID without requiring explicit propagation at every
        call site.

        In replay_mode, auto-persistence is disabled and
        sequence numbers are preserved for deterministic ordering.

        Handler failures are logged, counted, and dead-lettered — they
        never disappear silently.

        Idempotency - duplicate events (same event_id) are silently
        skipped to prevent double-processing under at-least-once delivery.
        """
        # Prepare event: inject infrastructure fields immutably
        event = self._prepare_event(event)

        # Idempotency check: skip if already processed
        if not self._is_duplicate_event(event):
            # Record published metric
            if self._metrics is not None:
                self._metrics.add_timestamped_counter(event.event_type, "published")

            # 1. Persist first (so a crash mid-dispatch can be recovered).
            # Skip persistence in replay mode (no recursive writes)
            if self._event_log is not None and self._logging_enabled and not self._replay_mode:
                try:
                    self._event_log.append(event)
                except Exception as exc:
                    # Surface, never swallow.
                    if self._metrics is not None:
                        self._metrics.add_timestamped_counter(
                            event.event_type, f"log_error:{type(exc).__name__}"
                        )
                    logger.exception(
                        "EventBus: failed to persist %s to log: %s",
                        event.event_type,
                        exc,
                    )
                    if self._dead_letter_queue is not None:
                        self._dead_letter_queue.push_failure(
                            event=event,
                            handler_id="<event_log>",
                            exc=exc,
                            traceback=traceback.format_exc(),
                        )
                    if self._fail_fast:
                        raise

            # 2. Dispatch (snapshot handlers to be lock-safe).
            # Skip handler dispatch during replay to prevent TRADE_APPLIED re-publishing
            # which causes PositionManager to double-count trades.
            if not self._replay_mode:
                with self._subscribers_lock:
                    handlers = list(self._subscribers.get(event.event_type, {}).items())

                for handler_id, handler in handlers:
                    if self._metrics is not None:
                        self._metrics.add_timestamped_counter(event.event_type, "dispatched")
                    try:
                        handler(event)
                    except Exception as exc:
                        self._handle_handler_failure(event, handler_id, exc)
                        if self._fail_fast:
                            raise
        else:
            # Duplicate event detected - log and skip
            if self._metrics is not None:
                self._metrics.add_timestamped_counter(event.event_type, "duplicate_skipped")
            logger.debug(
                "EventBus: skipping duplicate event_id=%s (type=%s, symbol=%s)",
                event.event_id,
                event.event_type,
                event.symbol,
            )

    def _handle_handler_failure(
        self, event: DomainEvent, handler_id: str, exc: BaseException
    ) -> None:
        """Mandatory failure-path: log, count, dead-letter."""
        error_type = type(exc).__name__

        if self._metrics is not None:
            self._metrics.add_timestamped_counter(event.event_type, f"handler_error:{error_type}")
            self._metrics.add_timestamped_counter(event.event_type, "dead_letter")

        logger.warning(
            "EventBus: handler %s failed on %s (event_id=%s, symbol=%s): %s: %s",
            handler_id,
            event.event_type,
            event.event_id,
            event.symbol,
            error_type,
            exc,
        )

        if self._dead_letter_queue is not None:
            self._dead_letter_queue.push_failure(
                event=event,
                handler_id=handler_id,
                exc=exc,
                traceback=traceback.format_exc(),
            )
        else:
            # Loud, visible warning so missing DLQ is impossible to miss.
            logger.error(
                "EventBus: handler %s failed on %s but no DeadLetterQueue is "
                "attached. The failure is only visible in logs. "
                "This is a configuration error in production.",
                handler_id,
                event.event_type,
            )
