"""Market data feed — subscription management and tick processing."""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable, Coroutine, Optional

from tradex.core.events import EventBus
from tradex.core.logging_config import get_logger
from tradex.domain.events import QuoteReceived
from tradex.streaming.engine import StreamEngine

logger = get_logger("streaming.feed")

TickHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class MarketFeed:
    """Market data feed manager.

    Manages subscriptions, processes incoming ticks,
    and publishes domain events.
    """

    def __init__(
        self,
        engine: StreamEngine,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._engine = engine
        self._event_bus = event_bus
        self._subscriptions: set[tuple[str, str, int]] = set()
        self._tick_handlers: list[TickHandler] = []
        self._dedup_cache: dict[str, float] = {}
        self._dedup_window = 0.5  # seconds

    @property
    def is_connected(self) -> bool:
        return self._engine.is_connected

    def on_tick(self, handler: TickHandler) -> None:
        """Register a tick handler."""
        self._tick_handlers.append(handler)

    async def subscribe(self, instruments: list[tuple[str, str, int]]) -> None:
        """Subscribe to market data for instruments.

        Each tuple is (exchange, security_id, subscription_type).
        """
        new = [i for i in instruments if i not in self._subscriptions]
        if not new:
            return

        self._subscriptions.update(new)

        # Build subscribe message — provider-specific
        # This is a template; actual message format depends on the broker
        subscribe_msg = {
            "type": "subscribe",
            "instruments": [
                {"exchange": exch, "security_id": sid, "type": stype} for exch, sid, stype in new
            ],
        }

        try:
            await self._engine.send(subscribe_msg)
            logger.info("subscribed", count=len(new))
        except Exception as e:
            logger.error("subscribe_failed", error=str(e))
            raise

    async def unsubscribe(self, instruments: list[tuple[str, str, int]]) -> None:
        """Unsubscribe from instruments."""
        to_remove = [i for i in instruments if i in self._subscriptions]
        if not to_remove:
            return

        self._subscriptions -= set(to_remove)

        unsubscribe_msg = {
            "type": "unsubscribe",
            "instruments": [
                {"exchange": exch, "security_id": sid, "type": stype}
                for exch, sid, stype in to_remove
            ],
        }

        try:
            await self._engine.send(unsubscribe_msg)
        except Exception as e:
            logger.error("unsubscribe_failed", error=str(e))

    async def ticks(self, timeout: float = 1.0) -> AsyncIterator[dict[str, Any]]:
        """Async iterator yielding raw tick data."""
        while self._engine.is_connected:
            msg = await self._engine.get_messages(timeout=timeout)
            if msg is not None:
                yield msg

    async def process_tick(self, data: dict[str, Any]) -> None:
        """Process an incoming tick message."""
        # Dedup check
        tick_key = self._make_dedup_key(data)
        if tick_key and self._is_duplicate(tick_key):
            return

        # Dispatch to handlers
        for handler in self._tick_handlers:
            try:
                await handler(data)
            except Exception as e:
                logger.error("tick_handler_error", error=str(e))

        # Publish domain event
        if self._event_bus:
            event = self._parse_tick_event(data)
            if event:
                await self._event_bus.publish(event)

    def _make_dedup_key(self, data: dict[str, Any]) -> Optional[str]:
        """Create a deduplication key from tick data."""
        sec_id = data.get("security_id", "")
        ts = data.get("LTT", data.get("last_trade_time", ""))
        if sec_id:
            return f"{sec_id}:{ts}"
        return None

    def _is_duplicate(self, key: str) -> bool:
        """Check if a tick is a duplicate within the dedup window."""
        import time

        now = time.time()
        last_seen = self._dedup_cache.get(key, 0)
        if now - last_seen < self._dedup_window:
            return True
        self._dedup_cache[key] = now

        # Cleanup old entries periodically
        if len(self._dedup_cache) > 10000:
            cutoff = now - self._dedup_window * 2
            self._dedup_cache = {k: v for k, v in self._dedup_cache.items() if v > cutoff}

        return False

    def _parse_tick_event(self, data: dict[str, Any]) -> Optional[QuoteReceived]:
        """Parse a raw tick into a QuoteReceived event."""
        try:
            security_id = str(data.get("security_id", ""))
            if not security_id:
                return None
            ltp = data.get("LTP", data.get("last_price", 0))
            if isinstance(ltp, str):
                ltp = float(ltp)
            return QuoteReceived(
                security_id=str(data.get("security_id", "")),
                exchange=str(data.get("exchange_segment", "")),
                last_price=float(ltp),
                volume=int(data.get("volume", 0)),
                bid=float(data.get("bid_price", 0)),
                ask=float(data.get("ask_price", 0)),
                source="streaming",
            )
        except Exception:
            return None
