"""Dhan polling market feed — REST-based fallback for when WebSocket is unavailable.

Polls the Dhan batch ``/marketfeed/ltp`` endpoint at a configurable interval,
delivering the same ``MarketTickEvent`` interface as the WebSocket feed.

Useful as a fallback when WebSocket connections are blocked or unreliable.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from brokers.domain.enums import Exchange
from brokers.infrastructure.logging import get_logger
from brokers.infrastructure.streaming.stream_health import MarketTickEvent
from brokers.infrastructure.streaming.subscription import InstrumentKey

logger = get_logger(__name__)

_DEFAULT_POLL_INTERVAL_S = 2.0
_BATCH_SIZE = 1000


class DhanPollingFeed:
    """REST polling fallback for Dhan market data.

    Polls the Dhan LTP endpoint at a fixed interval and delivers
    ``MarketTickEvent`` objects via registered consumer queues.

    Usage::

        feed = DhanPollingFeed(
            http_client=dhan_client,
            poll_interval=2.0,
        )
        await feed.start()
        queue = feed.add_consumer(InstrumentKey(...))

        async for tick in queue:
            print(tick.ltp)

        await feed.stop()
    """

    def __init__(
        self,
        *,
        http_client: Any,  # DhanHttpClient with post() method
        poll_interval: float = _DEFAULT_POLL_INTERVAL_S,
        on_tick: Callable[[MarketTickEvent], None] | None = None,
    ) -> None:
        self._http_client = http_client
        self._poll_interval = poll_interval
        self._on_tick = on_tick

        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._instruments: dict[str, InstrumentKey] = {}  # security_id -> key
        self._queues: list[asyncio.Queue] = []

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start the polling loop."""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("dhan_polling_feed_started", poll_interval=self._poll_interval)

    async def stop(self) -> None:
        """Stop the polling loop."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("dhan_polling_feed_stopped")

    def add_instrument(self, key: InstrumentKey) -> None:
        """Add an instrument to the polling set."""
        self._instruments[key.security_id] = key

    def remove_instrument(self, key: InstrumentKey) -> None:
        """Remove an instrument from the polling set."""
        self._instruments.pop(key.security_id, None)

    def add_consumer(self) -> asyncio.Queue:
        """Register a consumer queue for tick events."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._queues.append(q)
        return q

    def remove_consumer(self, q: asyncio.Queue) -> None:
        """Unregister a consumer queue."""
        self._queues = [x for x in self._queues if x is not q]

    async def _poll_loop(self) -> None:
        """Main polling loop — fetches LTP in batches."""
        while not self._stop_event.is_set():
            try:
                await self._poll_once()
            except Exception as exc:
                logger.warning("dhan_poll_error", error=str(exc)[:200])

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
            except asyncio.TimeoutError:
                pass  # Normal — time to poll again

    async def _poll_once(self) -> None:
        """Fetch LTP for all subscribed instruments in a single batch."""
        if not self._instruments:
            return

        # Group by exchange segment
        segments: dict[str, list[str]] = {}
        for key in self._instruments.values():
            segment = _exchange_to_segment(Exchange(key.exchange))
            segments.setdefault(segment, []).append(key.security_id)

        # Poll each segment
        for segment, ids in segments.items():
            for i in range(0, len(ids), _BATCH_SIZE):
                batch = ids[i:i + _BATCH_SIZE]
                await self._fetch_ltp_batch(segment, batch)

    async def _fetch_ltp_batch(self, segment: str, security_ids: list[str]) -> None:
        """Fetch LTP for a batch of instruments via REST."""
        try:
            # Run sync HTTP in thread pool
            loop = asyncio.get_event_loop()
            payload = {segment: security_ids}
            response = await loop.run_in_executor(
                None, lambda: self._http_client.post("/marketfeed/ltp", json=payload)
            )

            if not isinstance(response, dict):
                return

            # Parse response and emit ticks
            now = datetime.now(timezone.utc)
            for instrument_key_str, tick_data in response.items():
                if not isinstance(tick_data, dict):
                    continue

                ltp = float(tick_data.get("ltp", 0))
                if ltp <= 0:
                    continue

                # Find the matching InstrumentKey
                security_id = instrument_key_str.split("|")[-1] if "|" in instrument_key_str else instrument_key_str
                key = self._instruments.get(security_id)
                if key is None:
                    continue

                event = MarketTickEvent(
                    symbol=key.symbol,
                    ltp=ltp,
                    open=float(tick_data.get("open", 0)),
                    high=float(tick_data.get("high", 0)),
                    low=float(tick_data.get("low", 0)),
                    close=float(tick_data.get("close", 0)),
                    volume=int(tick_data.get("volume", 0)),
                    broker_id="dhan",
                    timestamp=now,
                )

                self._fan_out(event)

        except Exception as exc:
            logger.warning("dhan_poll_batch_error", error=str(exc)[:200])

    def _fan_out(self, event: MarketTickEvent) -> None:
        """Deliver tick to all consumer queues and callback."""
        if self._on_tick is not None:
            try:
                self._on_tick(event)
            except Exception:
                pass

        for q in self._queues:
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


def _exchange_to_segment(exchange: Exchange) -> str:
    """Map Exchange enum to Dhan segment string."""
    mapping = {
        Exchange.NSE: "NSE_EQ",
        Exchange.BSE: "BSE_EQ",
        Exchange.NFO: "NSE_FNO",
        Exchange.MCX: "MCX_COMM",
        Exchange.INDEX: "IDX_I",
    }
    return mapping.get(exchange, "NSE_EQ")


__all__ = ["DhanPollingFeed"]
