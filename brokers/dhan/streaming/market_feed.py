"""Dhan market data WebSocket feed — subclass of :class:`BaseMarketFeed`.

Connects to Dhan's market feed (``wss://api.dhan.co/marketfeed/v3/``)
and streams LTP / quote / depth data via JSON frames.

Tracking: dict keyed by ``security_id`` (Dhan's batch subscribe protocol
natively chunks sets of up to 1000 instruments per WS message).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

import websockets
import websockets.exceptions

from brokers.common.streaming.base_market_feed import BaseMarketFeed
from brokers.domain.enums import Exchange
from brokers.infrastructure.logging import get_logger
from brokers.infrastructure.streaming.stream_health import (
    MarketTickEvent,
    OrderUpdateEvent,
)
from brokers.infrastructure.streaming.subscription import (
    InstrumentKey,
    StreamMode,
    SubscriptionPlan,
)

from .decoder import decode_market_message
from .payloads import (
    build_subscribe_payload,
    mode_to_feed_type,
)

logger = get_logger(__name__)

_DHAN_MARKET_WS_URL = "wss://api.dhan.co/marketfeed/v3/"
_MAX_INSTRUMENTS = 1000


class DhanMarketFeed(BaseMarketFeed):
    """Async market data feed for Dhan — subclass :class:`BaseMarketFeed`."""

    BROKER_ID: ClassVar[str] = "dhan"
    MAX_INSTRUMENTS: ClassVar[int] = _MAX_INSTRUMENTS

    def __init__(
        self,
        *,
        client_id: str,
        access_token: str,
        on_tick: Callable[[MarketTickEvent], None] | None = None,
        on_health_change: Callable | None = None,
    ) -> None:
        super().__init__(on_tick=self._dispatch_tick, on_health_change=on_health_change)
        self._client_id = client_id
        self._access_token = access_token
        self._subscribed_keys: dict[str, InstrumentKey] = {}  # security_id -> key
        # List of tick callbacks so concurrent subscribers don't clobber
        # each other (set_tick_callback appends rather than overwrites).
        self._tick_callbacks: list[Callable[[MarketTickEvent], None]] = []
        if on_tick is not None:
            self._tick_callbacks.append(on_tick)

    async def _resolve_url_and_headers(self) -> tuple[str, dict[str, str] | None]:
        return (
            _DHAN_MARKET_WS_URL,
            {"client-id": self._client_id, "access-token": self._access_token},
        )

    async def _connect_ws(self, url: str, extra_headers: dict[str, str] | None = None) -> Any:
        ws = await websockets.connect(
            url,
            additional_headers=extra_headers or {},
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        )
        logger.info("dhan_ws_connected", url=url)
        return ws

    def _track_subscribe(
        self, instrument_key: InstrumentKey, mode: StreamMode
    ) -> None:
        if len(self._subscribed_keys) >= self.MAX_INSTRUMENTS:
            raise ValueError(
                f"Max {self.MAX_INSTRUMENTS} instruments per connection"
            )
        self._subscribed_keys[instrument_key.security_id] = instrument_key

    def _track_unsubscribe(self, instrument_key: InstrumentKey) -> None:
        self._subscribed_keys.pop(instrument_key.security_id, None)

    def _build_plan(self) -> SubscriptionPlan:
        return SubscriptionPlan(
            instruments=frozenset(self._subscribed_keys.values()),
            mode=self._mode,
        )

    async def _send_subscription(
        self, transport: Any, plan: SubscriptionPlan
    ) -> None:
        if not plan.instruments:
            return
        feed_type = mode_to_feed_type(plan.mode.value)

        instruments: list[tuple[Exchange, str]] = []
        for key in plan.instruments:
            exchange = (
                Exchange(key.exchange)
                if key.exchange in Exchange.__members__
                else Exchange.NSE
            )
            instruments.append((exchange, key.security_id))

        # Dhan batches 1000 instruments per WS message.
        batch_size = 1000
        for i in range(0, len(instruments), batch_size):
            batch = instruments[i : i + batch_size]
            payload = build_subscribe_payload(batch, feed_type=feed_type)
            await transport.send(payload)
            logger.info(
                "dhan_ws_subscribed",
                count=len(batch),
                feed_type=feed_type,
                batch=i // batch_size + 1,
            )

    def _decode_message(
        self, raw: str | bytes
    ) -> list[MarketTickEvent | OrderUpdateEvent]:
        # Map Dhan's numeric security_id back to the user-facing symbol so
        # emitted ticks are keyed by symbol, not by numeric id.
        def _lookup(security_id: str) -> str:
            key = self._subscribed_keys.get(security_id)
            return key.symbol if key is not None else security_id

        return decode_market_message(raw, symbol_lookup=_lookup)

    async def change_mode(self, mode: StreamMode) -> None:
        """Change the data mode — affects all subscribed instruments."""
        if self._orchestrator is None:
            return
        self._mode = mode
        plan = self._build_plan()
        await self._orchestrator.update_plan(plan)

    def _dispatch_tick(self, event: MarketTickEvent) -> None:
        """Fan a tick out to all registered tick callbacks."""
        for cb in self._tick_callbacks:
            try:
                cb(event)
            except Exception as exc:  # noqa: BLE001
                logger.warning("dhan_tick_callback_error", error=str(exc)[:200])

    def set_tick_callback(self, callback: Callable[[MarketTickEvent], None] | None) -> None:
        """Register a tick callback. Appends rather than overwriting so
        multiple concurrent subscribers each receive ticks.
        """
        if callback is not None and callback not in self._tick_callbacks:
            self._tick_callbacks.append(callback)
        if self._orchestrator is not None:
            self._orchestrator.set_callbacks(on_tick=self._dispatch_tick)

    def update_token(self, access_token: str) -> None:
        """Hot-swap the access token."""
        self._access_token = access_token


__all__ = ["DhanMarketFeed"]
