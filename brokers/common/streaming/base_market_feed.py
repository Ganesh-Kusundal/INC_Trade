"""Base market feed — abstract template for broker market-data streams.

Both :class:`~brokers.dhan.streaming.market_feed.DhanMarketFeed` and
:class:`~brokers.upstox.streaming.market_feed.UpstoxMarketFeed` subclass
:class:`BaseMarketFeed`, supplying only:

- ``BROKER_ID`` class attribute — string identifier for logs/subsystems
- ``MAX_INSTRUMENTS`` class attribute — broker-specific cap
- ``_resolve_url_and_headers()`` — async hook returning (url, headers)
- ``_connect_ws()`` — async WS connection helper
- ``_track_subscribe()`` — subclass tracking primitive (dict, V3SubscriptionManager)
- ``_track_unsubscribe()`` — symmetric removal
- ``_build_plan()`` — synthesize a ``SubscriptionPlan`` from tracked instruments
- ``_send_subscription()`` — broker-specific payload encoding
- ``_decode_message()`` — broker-specific frame decoder

The base owns: orchestrator lifecycle (``start``/``stop``, ``is_running``,
``health``), public ``subscribe``/``unsubscribe`` API that delegates tracking
to subclasses and posts the synthesised plan to the orchestrator.

Usage::

    class MyBrokerMarketFeed(BaseMarketFeed):
        BROKER_ID = "mybroker"
        MAX_INSTRUMENTS = 100

        def _track_subscribe(self, key, mode):
            self._store[(key.security_id, mode)] = key

        def _build_plan(self) -> SubscriptionPlan:
            return SubscriptionPlan(
                instruments=frozenset(self._store.values()),
                mode=self._mode,
            )
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar

from brokers.infrastructure.logging import get_logger
from brokers.infrastructure.streaming.orchestrator import StreamOrchestrator
from brokers.infrastructure.streaming.stream_health import (
    MarketTickEvent,
    OrderUpdateEvent,
    StreamHealth,
    StreamHealthChangeEvent,
)
from brokers.infrastructure.streaming.subscription import (
    InstrumentKey,
    StreamMode,
    SubscriptionPlan,
)

logger = get_logger(__name__)

# Type aliases matching the orchestrator's contract
ConnectFn = Callable[..., Coroutine[Any, Any, Any]]
SubscribeFn = Callable[..., Coroutine[Any, Any, None]]
DecodeFn = Callable[[str | bytes], list[MarketTickEvent | OrderUpdateEvent]]


class BaseMarketFeed(ABC):
    """Template-method base for broker market-data feeds.

    Subclasses MUST define ``BROKER_ID`` and implement the hooks below.
    The base owns the orchestrator + public lifecycle (``start``, ``stop``,
    ``subscribe``, ``unsubscribe``, ``is_running``, ``health``) so each
    subclass is ~50 LOC of glue.
    """

    BROKER_ID: ClassVar[str] = ""
    MAX_INSTRUMENTS: ClassVar[int] = 100
    DEFAULT_FRESHNESS_SLA: ClassVar[float] = 30.0

    def __init__(
        self,
        *,
        on_tick: Callable[[MarketTickEvent], None] | None = None,
        on_health_change: Callable[[StreamHealthChangeEvent], None] | None = None,
    ) -> None:
        if not self.BROKER_ID:
            raise ValueError(
                f"{type(self).__name__} must define BROKER_ID class attribute"
            )
        self._on_tick = on_tick
        self._on_health_change = on_health_change
        self._orchestrator: StreamOrchestrator | None = None
        self._mode: StreamMode = StreamMode.QUOTE

    # ── Public read-only state ───────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._orchestrator is not None and self._orchestrator.is_running

    @property
    def health(self) -> StreamHealth:
        if self._orchestrator is not None:
            return self._orchestrator.health
        return StreamHealth()

    @property
    def mode(self) -> StreamMode:
        return self._mode

    # ── Subclass hooks ───────────────────────────────────────────────────────

    @abstractmethod
    async def _resolve_url_and_headers(self) -> tuple[str, dict[str, str] | None]:
        """Return the authorized WS URL and any extra headers."""

    @abstractmethod
    async def _connect_ws(
        self, url: str, extra_headers: dict[str, str] | None = None
    ) -> Any:
        """Subclass-specific WS connection helper."""

    @abstractmethod
    def _track_subscribe(
        self, instrument_key: InstrumentKey, mode: StreamMode
    ) -> None:
        """Subclass tracking primitive: register an instrument + enforce ``MAX_INSTRUMENTS`` cap.

        Implementations should raise ``ValueError`` when the limit is exceeded.
        """

    @abstractmethod
    def _track_unsubscribe(self, instrument_key: InstrumentKey) -> None:
        """Subclass tracking primitive: remove an instrument."""

    @abstractmethod
    def _build_plan(self) -> SubscriptionPlan:
        """Build a ``SubscriptionPlan`` from the subclass's tracked instruments."""

    @abstractmethod
    async def _send_subscription(
        self, transport: Any, plan: SubscriptionPlan
    ) -> None:
        """Post ``plan`` to ``transport`` using broker-specific encoding."""

    @abstractmethod
    def _decode_message(
        self, raw: str | bytes
    ) -> list[MarketTickEvent | OrderUpdateEvent]:
        """Broker-specific frame decoder."""

    # ── Public lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        url, extra_headers = await self._resolve_url_and_headers()

        self._orchestrator = StreamOrchestrator(
            broker_id=f"{self.BROKER_ID}",
            connect_fn=self._connect_ws,
            subscribe_fn=self._send_subscription,
            decode_fn=self._decode_message,
            url=url,
            extra_headers=extra_headers,
            freshness_sla=self.DEFAULT_FRESHNESS_SLA,
        )
        self._orchestrator.set_callbacks(
            on_tick=self._on_tick,
            on_health_change=self._on_health_change,
        )
        await self._orchestrator.start()

    async def stop(self) -> None:
        """Stop the orchestrator + release subclass state."""
        if self._orchestrator is not None:
            await self._orchestrator.stop()
            self._orchestrator = None
        await self._release_subscriptions()

    async def _release_subscriptions(self) -> None:
        """Default release hook. Subclasses can override to clear tracking state."""

    async def subscribe(
        self,
        instrument_key: InstrumentKey,
        mode: StreamMode = StreamMode.QUOTE,
    ) -> asyncio.Queue:
        """Subscribe to market data for an instrument and return a queue consumer."""
        if self._orchestrator is None:
            raise RuntimeError(
                f"{self.BROKER_ID} feed not started — call start() first"
            )
        self._track_subscribe(instrument_key, mode)
        self._mode = mode

        plan = self._build_plan()
        await self._orchestrator.update_plan(plan)
        return self._orchestrator.add_tick_queue()

    async def unsubscribe(self, instrument_key: InstrumentKey) -> None:
        """Unsubscribe from market data for an instrument."""
        if self._orchestrator is None:
            return
        self._track_unsubscribe(instrument_key)

        plan = self._build_plan()
        await self._orchestrator.update_plan(plan)


__all__ = ["BaseMarketFeed", "ConnectFn", "DecodeFn", "SubscribeFn"]
