"""Base order stream — abstract template for broker-specific order update feeds.

Both :class:`~brokers.dhan.streaming.order_feed.DhanOrderFeed` and
:class:`~brokers.upstox.streaming.portfolio_feed.UpstoxPortfolioStream`
subclass :class:`BaseOrderStream`, supplying only:

- ``BROKER_ID`` class attribute — string identifier for logs/subsystems
- ``_resolve_url_and_headers()`` — async hook returning (url, headers)
- ``_decode_message()`` — broker-specific JSON-to-domain-event decoder
- ``_connect_ws()`` — async WS connection helper (with broker-specific ping params)
- ``_subscribe()`` — async hook (most order streams have no subscribe payload)

The base owns the :class:`StreamOrchestrator` lifecycle, callback wiring,
and consumer-queue registration.

Usage::

    class MyBrokerOrderFeed(BaseOrderStream):
        BROKER_ID = "mybroker"

        async def _resolve_url_and_headers(self):
            return ("wss://...", {"X-Token": "..."})

        def _decode_message(self, raw):
            ...
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
    StreamHealthChangeEvent,
)

logger = get_logger(__name__)

# Type aliases matching the orchestrator's contract
ConnectFn = Callable[..., Coroutine[Any, Any, Any]]
SubscribeFn = Callable[..., Coroutine[Any, Any, None]]
DecodeFn = Callable[[str | bytes], list[MarketTickEvent | OrderUpdateEvent]]


class BaseOrderStream(ABC):
    """Template-method base for broker order-update streams.

    Subclasses MUST define ``BROKER_ID`` and implement the four async hooks.
    The base owns the orchestrator + public lifecycle (``start``, ``stop``,
    ``add_consumer``, ``is_running``) so each subclass is ~30 LOC of glue.
    """

    BROKER_ID: ClassVar[str] = ""

    def __init__(
        self,
        *,
        on_order: Callable[[OrderUpdateEvent], None] | None = None,
        on_health_change: Callable[[StreamHealthChangeEvent], None] | None = None,
    ) -> None:
        if not self.BROKER_ID:
            raise ValueError(
                f"{type(self).__name__} must define BROKER_ID class attribute"
            )
        self._on_order = on_order
        self._on_health_change = on_health_change
        self._orchestrator: StreamOrchestrator | None = None

    @property
    def is_running(self) -> bool:
        return self._orchestrator is not None and self._orchestrator.is_running

    @abstractmethod
    async def _resolve_url_and_headers(self) -> tuple[str, dict[str, str] | None]:
        """Return the authorized WS URL and any extra headers.

        Subclass hook — Dhan returns the static URL + client headers;
        Upstox invokes its authorizer to obtain a one-time URL.
        """

    @abstractmethod
    def _decode_message(self, raw: str | bytes) -> list[MarketTickEvent | OrderUpdateEvent]:
        """Broker-specific message decoder."""

    @abstractmethod
    async def _connect_ws(
        self, url: str, extra_headers: dict[str, str] | None = None
    ) -> Any:
        """Broker-specific WS connection helper."""

    @abstractmethod
    async def _subscribe(self, transport: Any, plan: Any) -> None:
        """Broker-specific subscribe hook.

        Order streams typically don't need explicit subscription (server pushes
        all updates) — most subclasses can use :meth:`_no_op_subscribe`.
        """

    async def _no_op_subscribe(self, transport: Any, plan: Any) -> None:
        """Default subscribe helper: log and return."""
        logger.info(f"{self.BROKER_ID}_order_ws_subscribed")

    async def start(self) -> None:
        """Start the stream.

        Acquires the URL/headers, builds the orchestrator with subclass
        hooks, registers callbacks, then starts the orchestrator.
        """
        url, extra_headers = await self._resolve_url_and_headers()

        self._orchestrator = StreamOrchestrator(
            broker_id=f"{self.BROKER_ID}_orders",
            connect_fn=self._connect_ws,
            subscribe_fn=self._subscribe,
            decode_fn=self._decode_message,
            url=url,
            extra_headers=extra_headers,
        )
        self._orchestrator.set_callbacks(
            on_order=self._on_order,
            on_health_change=self._on_health_change,
        )
        await self._orchestrator.start()

    async def stop(self) -> None:
        """Stop the stream and tear down the orchestrator."""
        if self._orchestrator is not None:
            await self._orchestrator.stop()
            self._orchestrator = None

    def add_consumer(self) -> asyncio.Queue:
        """Register a consumer queue for order updates.

        Raises RuntimeError if the stream is not yet started.
        """
        if self._orchestrator is None:
            raise RuntimeError(
                f"{self.BROKER_ID} order stream not started — call start() first"
            )
        return self._orchestrator.add_order_queue()


__all__ = ["BaseOrderStream", "ConnectFn", "DecodeFn", "SubscribeFn"]
