"""Dhan depth feeds — 20-level and 200-level market depth streaming.

Provides:
- ``DhanDepthFeed``: 20-level depth (up to 50 instruments per connection)
- ``DhanDepth200Feed``: 200-level depth (1 instrument per connection)
- ``Depth200ConnectionPool``: manages multiple depth-200 connections

Dhan depth feeds use a binary protocol with ``struct.unpack`` for parsing.
Both depth types share the same base logic with configurable parameters.
"""

from __future__ import annotations

import asyncio
import struct
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import websockets

from brokers.domain.enums import Exchange
from brokers.infrastructure.logging import get_logger
from brokers.infrastructure.streaming.stream_health import MarketTickEvent
from brokers.infrastructure.streaming.subscription import InstrumentKey

logger = get_logger(__name__)


# ── Depth level parsing ────────────────────────────────────────────────────


def _parse_depth_levels(
    data: bytes,
    offset: int,
    count: int,
    bytes_per_level: int,
) -> list[tuple[float, int]]:
    """Parse depth levels from binary data.

    Each level is ``bytes_per_level`` bytes containing price (float32 or float64)
    and quantity (int32 or int64).
    """
    levels: list[tuple[float, int]] = []
    for i in range(count):
        pos = offset + i * bytes_per_level
        if pos + bytes_per_level > len(data):
            break
        try:
            if bytes_per_level == 8:
                # 4 bytes price (float32) + 4 bytes qty (int32)
                price = struct.unpack_from(">f", data, pos)[0]
                qty = struct.unpack_from(">I", data, pos + 4)[0]
            elif bytes_per_level == 16:
                # 8 bytes price (float64) + 8 bytes qty (int64)
                price = struct.unpack_from(">d", data, pos)[0]
                qty = struct.unpack_from(">Q", data, pos + 8)[0]
            else:
                break
            if price > 0 and qty > 0:
                levels.append((price, qty))
        except struct.error:
            break
    return levels


# ── Base depth feed ────────────────────────────────────────────────────────


class _BaseDepthFeed:
    """Base class for Dhan depth WebSocket feeds."""

    def __init__(
        self,
        *,
        client_id: str,
        access_token: str,
        url: str,
        depth_type: str,
        max_instruments: int,
        header_size: int,
        bytes_per_level: int,
        num_levels: int,
        on_depth: Callable[[MarketTickEvent], None] | None = None,
    ) -> None:
        self._client_id = client_id
        self._access_token = access_token
        self._url = url
        self._depth_type = depth_type
        self._max_instruments = max_instruments
        self._header_size = header_size
        self._bytes_per_level = bytes_per_level
        self._num_levels = num_levels
        self._on_depth = on_depth

        self._ws: Any = None
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._instruments: dict[str, InstrumentKey] = {}
        self._queues: list[asyncio.Queue] = []

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def instrument_count(self) -> int:
        return len(self._instruments)

    async def start(self) -> None:
        """Start the depth feed connection."""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._connection_loop())
        logger.info("dhan_depth_feed_started", depth_type=self._depth_type)

    async def stop(self) -> None:
        """Stop the depth feed connection."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._close_ws()
        logger.info("dhan_depth_feed_stopped", depth_type=self._depth_type)

    async def subscribe(self, key: InstrumentKey) -> asyncio.Queue:
        """Subscribe to depth data for an instrument."""
        if len(self._instruments) >= self._max_instruments:
            raise ValueError(
                f"Max {self._max_instruments} instruments for {self._depth_type}"
            )

        self._instruments[key.security_id] = key

        # Send subscribe if connected
        if self._ws is not None:
            await self._send_subscribe([key])

        # Register consumer queue
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._queues.append(q)
        return q

    async def unsubscribe(self, key: InstrumentKey) -> None:
        """Unsubscribe from depth data for an instrument."""
        self._instruments.pop(key.security_id, None)
        if self._ws is not None:
            await self._send_unsubscribe([key])

    def add_consumer(self) -> asyncio.Queue:
        """Register a consumer queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._queues.append(q)
        return q

    def remove_consumer(self, q: asyncio.Queue) -> None:
        """Unregister a consumer queue."""
        self._queues = [x for x in self._queues if x is not q]

    # ── Connection loop ─────────────────────────────────────────────────

    async def _connection_loop(self) -> None:
        """Main connection loop with reconnection."""
        while not self._stop_event.is_set():
            try:
                await self._connect_and_read()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "dhan_depth_reconnecting",
                    depth_type=self._depth_type,
                    error=str(exc)[:200],
                )
                await self._close_ws()
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass

    async def _connect_and_read(self) -> None:
        """Connect, subscribe all instruments, and read binary packets."""
        headers = {
            "client-id": self._client_id,
            "access-token": self._access_token,
        }
        self._ws = await websockets.connect(
            self._url,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=10,
        )
        logger.info("dhan_depth_ws_connected", depth_type=self._depth_type)

        # Subscribe all instruments
        if self._instruments:
            await self._send_subscribe(list(self._instruments.values()))

        # Read loop — binary packets
        async for message in self._ws:
            if self._stop_event.is_set():
                break
            if isinstance(message, bytes):
                self._process_binary_packet(message)

    async def _close_ws(self) -> None:
        """Close the WebSocket connection."""
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ── Subscription management ─────────────────────────────────────────

    async def _send_subscribe(self, keys: list[InstrumentKey]) -> None:
        """Send subscribe message for depth instruments."""
        # Dhan depth uses the same JSON subscribe format but with feedType=depth
        import json
        from .payloads import format_instrument_key

        instruments = [
            format_instrument_key(
                Exchange(k.exchange) if k.exchange in Exchange.__members__ else Exchange.NSE,
                k.security_id,
            )
            for k in keys
        ]
        payload = json.dumps({
            "action": "subscribe",
            "instruments": instruments,
            "feedType": "depth",
        })
        await self._ws.send(payload)
        logger.info("dhan_depth_subscribed", count=len(keys), depth_type=self._depth_type)

    async def _send_unsubscribe(self, keys: list[InstrumentKey]) -> None:
        """Send unsubscribe message for depth instruments."""
        import json
        from .payloads import format_instrument_key

        instruments = [
            format_instrument_key(
                Exchange(k.exchange) if k.exchange in Exchange.__members__ else Exchange.NSE,
                k.security_id,
            )
            for k in keys
        ]
        payload = json.dumps({
            "action": "unsubscribe",
            "instruments": instruments,
            "feedType": "depth",
        })
        await self._ws.send(payload)

    # ── Binary packet processing ────────────────────────────────────────

    def _process_binary_packet(self, data: bytes) -> None:
        """Parse a binary depth packet and emit MarketTickEvent."""
        if len(data) < self._header_size:
            return

        try:
            # Extract security_id from header
            security_id = str(struct.unpack_from(">I", data, 0)[0])

            # Parse depth levels
            bids = _parse_depth_levels(
                data,
                offset=self._header_size,
                count=self._num_levels,
                bytes_per_level=self._bytes_per_level,
            )
            asks_start = self._header_size + self._num_levels * self._bytes_per_level
            asks = _parse_depth_levels(
                data,
                offset=asks_start,
                count=self._num_levels,
                bytes_per_level=self._bytes_per_level,
            )

            # Find matching instrument key
            key = self._instruments.get(security_id)
            if key is None:
                return

            event = MarketTickEvent(
                symbol=key.symbol,
                ltp=bids[0][0] if bids else 0.0,
                depth_bids=tuple(bids),
                depth_asks=tuple(asks),
                broker_id="dhan",
                timestamp=datetime.now(timezone.utc),
            )

            self._fan_out(event)

        except (struct.error, IndexError) as exc:
            logger.debug("dhan_depth_parse_error", error=str(exc)[:100])

    def _fan_out(self, event: MarketTickEvent) -> None:
        """Deliver depth event to all consumer queues."""
        if self._on_depth is not None:
            try:
                self._on_depth(event)
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


# ── 20-level depth feed ────────────────────────────────────────────────────


class DhanDepth20Feed(_BaseDepthFeed):
    """20-level market depth feed (up to 50 instruments per connection)."""

    def __init__(
        self,
        *,
        client_id: str,
        access_token: str,
        on_depth: Callable[[MarketTickEvent], None] | None = None,
    ) -> None:
        super().__init__(
            client_id=client_id,
            access_token=access_token,
            url="wss://api.dhan.co/marketfeed/v3/",
            depth_type="DEPTH_20",
            max_instruments=50,
            header_size=8,
            bytes_per_level=8,
            num_levels=20,
            on_depth=on_depth,
        )


# ── 200-level depth feed ───────────────────────────────────────────────────


class DhanDepth200Feed(_BaseDepthFeed):
    """200-level market depth feed (1 instrument per connection).

    Dhan restricts depth-200 to a single instrument per WebSocket connection.
    Use ``Depth200ConnectionPool`` to manage multiple instruments.
    """

    def __init__(
        self,
        *,
        client_id: str,
        access_token: str,
        on_depth: Callable[[MarketTickEvent], None] | None = None,
    ) -> None:
        super().__init__(
            client_id=client_id,
            access_token=access_token,
            url="wss://full-depth-api.dhan.co/twohundreddepth",
            depth_type="DEPTH_200",
            max_instruments=1,
            header_size=12,
            bytes_per_level=16,
            num_levels=200,
            on_depth=on_depth,
        )

    async def subscribe(self, key: InstrumentKey) -> asyncio.Queue:
        """Subscribe to 200-level depth (1 instrument max)."""
        if len(self._instruments) >= 1:
            raise ValueError("DhanDepth200Feed supports only 1 instrument per connection")
        return await super().subscribe(key)


# ── Connection pool for depth-200 ──────────────────────────────────────────


class Depth200ConnectionPool:
    """Connection pool for Dhan 200-level depth feeds.

    Since each depth-200 connection supports only 1 instrument, this pool
    manages multiple connections and maps instruments to feeds.

    Usage::

        pool = Depth200ConnectionPool(client_id="...", access_token="...")
        queue = await pool.subscribe(InstrumentKey(...))
        async for depth in queue:
            print(depth.depth_bids)
        await pool.close_all()
    """

    def __init__(
        self,
        *,
        client_id: str,
        access_token: str,
        max_connections: int = 20,
        on_depth: Callable[[MarketTickEvent], None] | None = None,
    ) -> None:
        self._client_id = client_id
        self._access_token = access_token
        self._max_connections = max_connections
        self._on_depth = on_depth
        self._feeds: dict[str, DhanDepth200Feed] = {}  # security_id -> feed
        self._queues: dict[str, asyncio.Queue] = {}  # security_id -> queue

    @property
    def active_connections(self) -> int:
        return len(self._feeds)

    async def subscribe(self, key: InstrumentKey) -> asyncio.Queue:
        """Subscribe to 200-level depth for an instrument.

        Returns an asyncio.Queue for depth events. Creates a new connection
        if needed, reuses existing if already subscribed.
        """
        if key.security_id in self._feeds:
            return self._queues[key.security_id]

        if len(self._feeds) >= self._max_connections:
            # Evict oldest unused connection
            await self._evict_oldest()

        feed = DhanDepth200Feed(
            client_id=self._client_id,
            access_token=self._access_token,
            on_depth=self._on_depth,
        )
        await feed.start()
        queue = await feed.subscribe(key)

        self._feeds[key.security_id] = feed
        self._queues[key.security_id] = queue

        logger.info(
            "depth200_connected",
            symbol=key.symbol,
            active_connections=self.active_connections,
        )

        return queue

    async def unsubscribe(self, key: InstrumentKey) -> None:
        """Unsubscribe and close the connection for an instrument."""
        feed = self._feeds.pop(key.security_id, None)
        if feed is not None:
            await feed.stop()
        self._queues.pop(key.security_id, None)

    async def close_all(self) -> None:
        """Close all depth-200 connections."""
        for feed in self._feeds.values():
            await feed.stop()
        self._feeds.clear()
        self._queues.clear()

    async def _evict_oldest(self) -> None:
        """Evict the oldest connection to make room."""
        if not self._feeds:
            return
        oldest_key = next(iter(self._feeds))
        feed = self._feeds.pop(oldest_key)
        await feed.stop()
        self._queues.pop(oldest_key, None)


__all__ = [
    "DhanDepth20Feed",
    "DhanDepth200Feed",
    "Depth200ConnectionPool",
]
