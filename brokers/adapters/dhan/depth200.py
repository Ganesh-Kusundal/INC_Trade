"""Dhan Depth 200 adapter — L3 Market Data via WebSocket.

Thin subclass of BinaryDepthFeed that preserves backward-compatible API for
depth-200 feeds. See archived brokers.dhan.depth_200.DhanDepth200Feed for reference.

Endpoint: wss://full-depth-api.dhan.co/twohundreddepth
Max instruments: 1 per connection (Dhan API limitation)
Header layout: num_rows at offset 8 (security_id is implicit per connection)

IMPORTANT LIMITATION: Dhan's depth-200 API only supports ONE instrument per connection.
Use Depth200ConnectionPool for managing multiple instruments.
"""

from __future__ import annotations

import logging
from threading import RLock
from typing import TYPE_CHECKING, Any

from inc_trade.config.endpoints import Dhan
from inc_trade.domain import MarketDepth

from brokers.adapters.dhan.depth_feed_base import BinaryDepthFeed
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.resilience.websocket_rate_limiter_simple import (
    get_dhan_ws_rate_limiter,
)
from brokers.adapters.dhan.segments import resolve_segment

if TYPE_CHECKING:
    from typing import TypeAlias

logger = logging.getLogger(__name__)

__all__ = ["Depth200ConnectionPool", "DhanDepth200Stream"]

InstrumentKey: TypeAlias = tuple[str, str]


class DhanDepth200Stream(BinaryDepthFeed):
    """200-level market depth via WebSocket.

    CRITICAL LIMITATION: Only 1 instrument per connection allowed.
    """

    name = "dhan.depth_200"
    REQUEST_CODE = 23
    DEPTH_TYPE = "DEPTH_200"
    EVENT_NAME = "DEPTH_200"

    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
        resolver: DhanInstrumentResolver | None = None,
        instrument: tuple[str, str] | None = None,
        event_bus: Any = None,
    ):
        super().__init__(
            client_id=client_id,
            access_token=access_token if not callable(access_token) else access_token(),
            endpoint=Dhan.WS_DEPTH_200,
            request_code=self.REQUEST_CODE,
            total_slots=200,
            subs_per_connection=1,
            depth_type="DEPTH_200",
            name=self.name,
            event_name="DEPTH_200",
            header_carries_security_id=False,
            event_bus=event_bus,
        )
        self._access_token_fn = access_token if callable(access_token) else None
        self._resolver = resolver

        if instrument:
            self.subscribe(instrument)

    # ── Backward-compatible subscribe (single instrument) ───────────────────

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Subscribe using symbol+exchange (backward compatible API)."""
        try:
            ref = self._resolver.resolve(symbol, exchange)
            if ref:
                key = (ref.exchange_segment, ref.security_id)
                super().subscribe([key])
                logger.info(f"Depth200 subscribed to {symbol} ({exchange})")
            else:
                segment = resolve_segment(exchange)
                super().subscribe([(segment, symbol)])
        except Exception as e:
            logger.error(
                f"Depth200 failed to resolve/subscribe {symbol} on {exchange}: {e}"
            )
            segment = resolve_segment(exchange)
            super().subscribe([(segment, symbol)])

    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Unsubscribe using symbol+exchange (backward compatible API)."""
        try:
            ref = self._resolver.resolve(symbol, exchange)
            if ref:
                key = (ref.exchange_segment, ref.security_id)
                super().unsubscribe([key])
                logger.info(f"Depth200 unsubscribed from {symbol} ({exchange})")
        except Exception as e:
            logger.error(
                f"Depth200 failed to resolve/unsubscribe {symbol} on {exchange}: {e}"
            )

    # ── Depth-200 specific lookup: single-instrument cache ─────────────────

    def latest_depth(self) -> MarketDepth | None:
        """Return the most-recent cached MarketDepth."""
        with self._depth_cache_lock:
            if not self._depth_cache:
                return None
            entry = next(iter(self._depth_cache.values()))
            bids = list(entry.get("bids", []))
            asks = list(entry.get("asks", []))
        if not bids and not asks:
            return None
        sec_id = next(iter(self._depth_cache))
        return MarketDepth(
            symbol=self._sec_id_to_symbol.get(sec_id, ""),
            bids=bids,
            asks=asks,
        )

    def update_token(self, new_token: str) -> None:
        """Update token and reconnect with fresh auth."""
        if self._access_token_fn:
            self._access_token = new_token
        super().update_token(new_token)


# =============================================================================
# Depth200ConnectionPool - Connection pooling for multiple instruments
# =============================================================================


class Depth200ConnectionPool:
    """Connection pool for managing multiple Dhan depth-200 WebSocket connections.

    Since Dhan's depth-200 API only supports 1 instrument per connection,
    this pool creates and manages separate connections for each instrument.
    """

    def __init__(
        self,
        client_id: str,
        access_token: str | Callable[[], str],
        event_bus: Any = None,
        resolver: DhanInstrumentResolver | None = None,
        max_connections: int | None = None,
    ):
        self._client_id = client_id
        self._access_token = access_token
        self._event_bus = event_bus
        self._resolver = resolver
        self._max_connections = max_connections
        self._feeds: dict[tuple[str, str], DhanDepth200Stream] = {}
        self._lock = RLock()

    def get_feed(self, instrument: InstrumentKey) -> DhanDepth200Stream:
        """Get or create a feed for the given instrument."""
        with self._lock:
            if instrument in self._feeds:
                return self._feeds[instrument]

            # Check rate limiting for new connections
            try:
                ws_rate_limiter = get_dhan_ws_rate_limiter()
                if not ws_rate_limiter.can_create_depth_200_connection():
                    import time as time_module

                    while not ws_rate_limiter.can_create_depth_200_connection():
                        time_module.sleep(0.1)
            except Exception:
                pass  # Rate limiter not available, proceed

            # Enforce max connections limit
            if self._max_connections and len(self._feeds) >= self._max_connections:
                oldest_key = next(iter(self._feeds))
                self._feeds[oldest_key].stop()
                del self._feeds[oldest_key]
                logger.warning(
                    "depth_200_pool_eviction",
                    extra={
                        "evicted_instrument": oldest_key,
                        "new_instrument": instrument,
                    },
                )

            feed = DhanDepth200Stream(
                client_id=self._client_id,
                access_token=self._access_token,
                resolver=self._resolver,
                instrument=instrument,
                event_bus=self._event_bus,
            )
            self._feeds[instrument] = feed
            logger.debug(
                "depth_200_pool_feed_created",
                extra={"instrument": instrument, "total_feeds": len(self._feeds)},
            )
            return feed

    def has_feed(self, instrument: InstrumentKey) -> bool:
        with self._lock:
            return instrument in self._feeds

    def remove_feed(self, instrument: InstrumentKey) -> bool:
        with self._lock:
            if instrument in self._feeds:
                self._feeds[instrument].stop()
                del self._feeds[instrument]
                return True
            return False

    def get_all_feeds(self) -> list[DhanDepth200Stream]:
        with self._lock:
            return list(self._feeds.values())

    def get_instruments(self) -> list[InstrumentKey]:
        with self._lock:
            return list(self._feeds.keys())

    def close_all(self) -> None:
        with self._lock:
            for instrument, feed in list(self._feeds.items()):
                try:
                    feed.stop()
                except Exception as e:
                    logger.error(
                        "depth_200_pool_feed_close_error",
                        extra={"instrument": instrument, "error": str(e)},
                    )
            self._feeds.clear()
        logger.info("depth_200_pool_all_closed")

    def __len__(self) -> int:
        with self._lock:
            return len(self._feeds)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_all()
        return False
