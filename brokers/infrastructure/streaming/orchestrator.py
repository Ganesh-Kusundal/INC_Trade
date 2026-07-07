"""Stream orchestrator — async lifecycle manager for WebSocket connections.

Manages a single stream's lifecycle: connect → subscribe → read → fan-out,
with automatic reconnection, health monitoring, and backpressure.

The orchestrator is broker-agnostic: it delegates protocol-specific work
(connect/auth, encode subscribe, decode message) to callbacks provided
at construction time.

Usage::

    orchestrator = StreamOrchestrator(
        broker_id="dhan",
        connect_fn=my_connect_coroutine,
        subscribe_fn=my_subscribe_coroutine,
        decode_fn=my_decode_function,
        auth_url="wss://...",
        on_tick=my_tick_callback,
        on_order=my_order_callback,
        on_health_change=my_health_callback,
    )
    await orchestrator.start()
    orchestrator.update_plan(plan.with_added(key1, key2))
    await orchestrator.stop()
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from brokers.infrastructure.logging import get_logger
from brokers.infrastructure.streaming.stream_health import (
    FreshnessState,
    MarketTickEvent,
    OrderUpdateEvent,
    StreamHealth,
    StreamHealthChangeEvent,
    SubscriptionState,
    TransportState,
)
from brokers.infrastructure.streaming.subscription import (
    SubscriptionPlan,
)

logger = get_logger(__name__)

# ── Reconnect defaults ─────────────────────────────────────────────────────

_RECONNECT_BASE_DELAY_S = 1.0
_RECONNECT_MAX_DELAY_S = 60.0
_MAX_RECONNECT_ATTEMPTS = 10
_HEARTBEAT_INTERVAL_S = 5.0
_FRESHNESS_SLA_S = 30.0
_MAX_CONSUMER_QUEUE = 1000
_JITTER_FACTOR = 0.3


# ── Callback types ─────────────────────────────────────────────────────────

# connect_fn(url, headers) -> transport-like object with send/recv/close
ConnectFn = Callable[..., Coroutine[Any, Any, Any]]
# subscribe_fn(transport, plan) -> None
SubscribeFn = Callable[..., Coroutine[Any, Any, None]]
# decode_fn(raw_message) -> list[MarketTickEvent | OrderUpdateEvent]
DecodeFn = Callable[[str | bytes], list[MarketTickEvent | OrderUpdateEvent]]


class StreamOrchestrator:
    """Async lifecycle manager for a single WebSocket stream.

    Manages: connect → subscribe → read loop → fan-out to consumers,
    with automatic reconnection and health monitoring.
    """

    def __init__(
        self,
        *,
        broker_id: str,
        connect_fn: ConnectFn,
        subscribe_fn: SubscribeFn,
        decode_fn: DecodeFn,
        url: str,
        extra_headers: dict[str, str] | None = None,
        reconnect_base_delay: float = _RECONNECT_BASE_DELAY_S,
        reconnect_max_delay: float = _RECONNECT_MAX_DELAY_S,
        max_reconnect_attempts: int = _MAX_RECONNECT_ATTEMPTS,
        heartbeat_interval: float = _HEARTBEAT_INTERVAL_S,
        freshness_sla: float = _FRESHNESS_SLA_S,
        max_consumer_queue: int = _MAX_CONSUMER_QUEUE,
    ) -> None:
        self._broker_id = broker_id
        self._connect_fn = connect_fn
        self._subscribe_fn = subscribe_fn
        self._decode_fn = decode_fn
        self._url = url
        self._extra_headers = extra_headers or {}
        self._reconnect_base_delay = reconnect_base_delay
        self._reconnect_max_delay = reconnect_max_delay
        self._max_reconnect_attempts = max_reconnect_attempts
        self._heartbeat_interval = heartbeat_interval
        self._freshness_sla = freshness_sla
        self._max_consumer_queue = max_consumer_queue

        # State
        self._plan = SubscriptionPlan()
        self._health = StreamHealth()
        self._transport: Any = None
        self._reconnect_attempts = 0
        self._last_tick_at: datetime | None = None

        # Tasks
        self._read_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

        # Consumer fan-out
        self._tick_queues: list[asyncio.Queue] = []
        self._order_queues: list[asyncio.Queue] = []

        # Callbacks
        self._on_tick: Callable[[MarketTickEvent], None] | None = None
        self._on_order: Callable[[OrderUpdateEvent], None] | None = None
        self._on_health_change: Callable[[StreamHealthChangeEvent], None] | None = None

        # Lock for plan updates
        self._plan_lock = asyncio.Lock()

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def broker_id(self) -> str:
        return self._broker_id

    @property
    def health(self) -> StreamHealth:
        return self._health

    @property
    def plan(self) -> SubscriptionPlan:
        return self._plan

    @property
    def is_running(self) -> bool:
        return self._read_task is not None and not self._read_task.done()

    def set_callbacks(
        self,
        *,
        on_tick: Callable[[MarketTickEvent], None] | None = None,
        on_order: Callable[[OrderUpdateEvent], None] | None = None,
        on_health_change: Callable[[StreamHealthChangeEvent], None] | None = None,
    ) -> None:
        """Register callbacks for tick/order/health events."""
        self._on_tick = on_tick
        self._on_order = on_order
        self._on_health_change = on_health_change

    def add_tick_queue(self) -> asyncio.Queue:
        """Register a consumer queue for market tick fan-out."""
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_consumer_queue)
        self._tick_queues.append(q)
        return q

    def add_order_queue(self) -> asyncio.Queue:
        """Register a consumer queue for order update fan-out."""
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_consumer_queue)
        self._order_queues.append(q)
        return q

    def remove_tick_queue(self, q: asyncio.Queue) -> None:
        """Unregister a consumer tick queue."""
        self._tick_queues = [x for x in self._tick_queues if x is not q]

    def remove_order_queue(self, q: asyncio.Queue) -> None:
        """Unregister a consumer order queue."""
        self._order_queues = [x for x in self._order_queues if x is not q]

    async def start(self, plan: SubscriptionPlan | None = None) -> None:
        """Start the orchestrator with an optional initial plan."""
        if plan is not None:
            self._plan = plan

        self._stop_event.clear()
        self._reconnect_attempts = 0

        self._read_task = asyncio.create_task(
            self._connection_loop(), name=f"{self._broker_id}_stream"
        )
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name=f"{self._broker_id}_heartbeat"
        )

        logger.info(
            "stream_orchestrator_started",
            broker_id=self._broker_id,
            instrument_count=len(self._plan),
        )

    async def stop(self) -> None:
        """Stop the orchestrator and close the connection."""
        self._stop_event.set()

        if self._read_task is not None:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        await self._disconnect()
        self._update_health(TransportState.CLOSED, SubscriptionState.NONE, FreshnessState.UNKNOWN)

        logger.info("stream_orchestrator_stopped", broker_id=self._broker_id)

    async def update_plan(self, new_plan: SubscriptionPlan) -> None:
        """Update the subscription plan and send changes to the server."""
        async with self._plan_lock:
            self._plan = new_plan

        if self._transport is not None and getattr(self._transport, "is_connected", False):
            try:
                await self._subscribe_fn(self._transport, new_plan)
                self._update_subscription_state()
                logger.info(
                    "stream_plan_updated",
                    broker_id=self._broker_id,
                    instrument_count=len(new_plan),
                )
            except Exception as exc:
                logger.warning(
                    "stream_plan_update_failed",
                    broker_id=self._broker_id,
                    error=str(exc)[:200],
                )

    # ── Connection loop ─────────────────────────────────────────────────────

    async def _connection_loop(self) -> None:
        """Main connection loop with automatic reconnection."""
        while not self._stop_event.is_set():
            try:
                await self._connect_and_read()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._reconnect_attempts += 1

                if self._reconnect_attempts > self._max_reconnect_attempts:
                    self._update_health(
                        TransportState.CLOSED,
                        SubscriptionState.NONE,
                        FreshnessState.UNKNOWN,
                        detail=f"Max reconnect attempts ({self._max_reconnect_attempts}) exceeded: {exc}",
                    )
                    logger.error(
                        "stream_max_reconnect_exceeded",
                        broker_id=self._broker_id,
                        attempts=self._reconnect_attempts,
                        error=str(exc)[:200],
                    )
                    break

                delay = self._backoff_delay(self._reconnect_attempts)
                self._update_health(
                    TransportState.RECONNECTING,
                    SubscriptionState.NONE,
                    self._health.freshness,
                    detail=f"Reconnecting (attempt {self._reconnect_attempts}): {exc}",
                )
                logger.warning(
                    "stream_reconnecting",
                    broker_id=self._broker_id,
                    attempt=self._reconnect_attempts,
                    delay_s=round(delay, 1),
                    error=str(exc)[:200],
                )
                await self._interruptible_sleep(delay)

    async def _connect_and_read(self) -> None:
        """Connect, subscribe, and run the read loop."""
        # Connect
        self._transport = await self._connect_fn(self._url, extra_headers=self._extra_headers)
        self._reconnect_attempts = 0
        self._update_health(TransportState.OPEN, SubscriptionState.NONE, self._health.freshness)

        logger.info("stream_connected", broker_id=self._broker_id)

        # Subscribe
        try:
            await self._subscribe_fn(self._transport, self._plan)
            self._update_subscription_state()
        except Exception as exc:
            logger.warning(
                "stream_subscribe_failed",
                broker_id=self._broker_id,
                error=str(exc)[:200],
            )
            # Continue reading — some subscriptions may have succeeded

        # Read loop
        try:
            while not self._stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(
                        self._transport.recv(), timeout=self._heartbeat_interval
                    )
                except asyncio.TimeoutError:
                    # No message within heartbeat interval — check freshness
                    self._check_freshness()
                    continue

                self._last_tick_at = datetime.now(timezone.utc)
                if self._health.freshness != FreshnessState.ACTIVE:
                    self._update_health(
                        self._health.transport,
                        self._health.subscription,
                        FreshnessState.ACTIVE,
                    )

                # Decode and fan-out
                events = self._decode_fn(raw)
                for event in events:
                    if isinstance(event, MarketTickEvent):
                        self._fan_out_tick(event)
                    elif isinstance(event, OrderUpdateEvent):
                        self._fan_out_order(event)

        finally:
            await self._disconnect()

    async def _disconnect(self) -> None:
        """Close the transport connection."""
        if self._transport is not None:
            try:
                await self._transport.close()
            except Exception:
                pass
            self._transport = None

    # ── Heartbeat ───────────────────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Periodic health check loop."""
        while not self._stop_event.is_set():
            await self._interruptible_sleep(self._heartbeat_interval)
            if self._stop_event.is_set():
                break
            self._check_freshness()

    def _check_freshness(self) -> None:
        """Check if we've received data within the freshness SLA."""
        if self._last_tick_at is None:
            return

        elapsed = (datetime.now(timezone.utc) - self._last_tick_at).total_seconds()
        if elapsed > self._freshness_sla:
            self._update_health(
                self._health.transport,
                self._health.subscription,
                FreshnessState.STALE,
                detail=f"No data for {elapsed:.0f}s (SLA: {self._freshness_sla:.0f}s)",
            )

    # ── Fan-out ─────────────────────────────────────────────────────────────

    def _fan_out_tick(self, event: MarketTickEvent) -> None:
        """Deliver tick to all registered consumer queues and callback."""
        if self._on_tick is not None:
            try:
                self._on_tick(event)
            except Exception as exc:
                logger.warning("tick_callback_error", broker_id=self._broker_id, error=str(exc)[:100])

        for q in self._tick_queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Backpressure: drop oldest and insert new
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    def _fan_out_order(self, event: OrderUpdateEvent) -> None:
        """Deliver order update to all registered consumer queues and callback."""
        if self._on_order is not None:
            try:
                self._on_order(event)
            except Exception as exc:
                logger.warning("order_callback_error", broker_id=self._broker_id, error=str(exc)[:100])

        for q in self._order_queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    # ── Health management ───────────────────────────────────────────────────

    def _update_health(
        self,
        transport: TransportState | None = None,
        subscription: SubscriptionState | None = None,
        freshness: FreshnessState | None = None,
        detail: str = "",
    ) -> None:
        """Update health state and emit change event if changed."""
        previous = self._health
        self._health = StreamHealth(
            transport=transport or previous.transport,
            subscription=subscription or previous.subscription,
            freshness=freshness or previous.freshness,
            last_tick_at=self._last_tick_at,
            reconnect_attempts=self._reconnect_attempts,
            subscribed_count=previous.subscribed_count,
            requested_count=len(self._plan),
            detail=detail or previous.detail,
        )

        # Emit change event if state actually changed
        if (
            previous.transport != self._health.transport
            or previous.subscription != self._health.subscription
            or previous.freshness != self._health.freshness
        ):
            event = StreamHealthChangeEvent(
                previous=previous,
                current=self._health,
                broker_id=self._broker_id,
            )
            if self._on_health_change is not None:
                try:
                    self._on_health_change(event)
                except Exception as exc:
                    logger.warning("health_callback_error", error=str(exc)[:100])

    def _update_subscription_state(self) -> None:
        """Update subscription state based on plan vs actual."""
        count = len(self._plan)
        if count == 0:
            state = SubscriptionState.NONE
        else:
            # Optimistic: assume all subscribed if we got here without error
            state = SubscriptionState.SYNCED

        self._health = StreamHealth(
            transport=self._health.transport,
            subscription=state,
            freshness=self._health.freshness,
            last_tick_at=self._last_tick_at,
            reconnect_attempts=self._reconnect_attempts,
            subscribed_count=count,
            requested_count=count,
            detail=self._health.detail,
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter."""
        base = min(
            self._reconnect_base_delay * (2 ** (attempt - 1)),
            self._reconnect_max_delay,
        )
        jitter = base * _JITTER_FACTOR * (2 * random.random() - 1)
        return max(0.1, base + jitter)  # type: ignore[no-any-return]

    async def _interruptible_sleep(self, duration: float) -> None:
        """Sleep that can be interrupted by the stop event."""
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=duration)
        except asyncio.TimeoutError:
            pass  # Normal — sleep completed


__all__ = ["StreamOrchestrator"]
