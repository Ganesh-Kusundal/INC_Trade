"""Dhan streaming provider — WebSocket market data and order updates."""

from __future__ import annotations

from typing import Any, AsyncIterator, Optional

import websockets

from tradex.broker.auth import AuthManager
from tradex.broker.provider import StreamingProvider
from tradex.providers.dhan.config import DhanConfig
from tradex.core.events import EventBus
from tradex.core.logging_config import get_logger
from tradex.streaming.engine import StreamConfig, StreamEngine
from tradex.streaming.feed import MarketFeed
from tradex.streaming.order_feed import OrderFeed

logger = get_logger("providers.dhan.streaming")


class DhanStreamingProvider(StreamingProvider):
    """Dhan-specific streaming provider.

    Manages WebSocket connections for market data and order updates.
    """

    def __init__(
        self,
        config: DhanConfig,
        auth_manager: AuthManager,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._config = config
        self._auth = auth_manager
        self._event_bus = event_bus

        # Market feed engine
        self._market_config = StreamConfig(
            url=config.ws_url,
            reconnect=True,
            max_reconnect_attempts=10,
            heartbeat_interval=30.0,
        )
        self._market_engine = StreamEngine(self._market_config)
        self._market_feed = MarketFeed(self._market_engine, event_bus)

        # Order update engine
        self._order_config = StreamConfig(
            url=config.ws_url,
            reconnect=True,
            max_reconnect_attempts=10,
            heartbeat_interval=30.0,
        )
        self._order_engine = StreamEngine(self._order_config)
        self._order_feed = OrderFeed(event_bus)

        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Connect to Dhan WebSocket streams."""
        if not self._auth.is_authenticated:
            from tradex.core.errors import AuthenticationError

            raise AuthenticationError("Not authenticated", code="DH-901")

        # Wire engine message handlers to feed processors
        self._market_engine.on_message(self._market_feed.process_tick)
        self._order_engine.on_message(self._order_feed.process_update)

        # Connect market feed
        await self._market_engine.connect(self._create_market_ws)

        # Connect order updates
        await self._order_engine.connect(self._create_order_ws)

        self._connected = True
        logger.info("dhan_streaming_connected")

    async def disconnect(self) -> None:
        """Disconnect all streams."""
        await self._market_engine.disconnect()
        await self._order_engine.disconnect()
        self._connected = False
        logger.info("dhan_streaming_disconnected")

    async def subscribe(self, instruments: list[tuple[str, str, int]]) -> None:
        """Subscribe to market data instruments."""
        await self._market_feed.subscribe(instruments)

    async def unsubscribe(self, instruments: list[tuple[str, str, int]]) -> None:
        """Unsubscribe from instruments."""
        await self._market_feed.unsubscribe(instruments)

    async def ticks(self) -> AsyncIterator[dict[str, Any]]:
        """Async iterator yielding raw tick data."""
        async for tick in self._market_feed.ticks():
            yield tick

    async def _create_market_ws(self) -> Any:
        """Create a market data WebSocket connection."""
        ws_url = f"{self._config.ws_url}/feed/v2/market"
        return await websockets.connect(
            ws_url,
            extra_headers={
                "access-token": self._auth.access_token,
                "client-id": self._config.client_id,
            },
        )

    async def _create_order_ws(self) -> Any:
        """Create an order update WebSocket connection."""
        ws_url = f"{self._config.ws_url}/feed/v2/orders"
        return await websockets.connect(
            ws_url,
            extra_headers={
                "access-token": self._auth.access_token,
                "client-id": self._config.client_id,
            },
        )

    @property
    def market_feed(self) -> MarketFeed:
        return self._market_feed

    @property
    def order_feed(self) -> OrderFeed:
        return self._order_feed
