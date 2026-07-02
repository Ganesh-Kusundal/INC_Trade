"""200-level market depth WebSocket feed for Dhan.

Plan §7.1 refactor: the binary-packet / reconnect / lifecycle machinery is
shared with ``DhanDepth20Feed`` via :class:`BinaryDepthFeed` (in
``brokers.dhan.depth_feed_base``). This module keeps ``DhanDepth200Feed``
as a thin subclass so callers and tests that import
``brokers.dhan.depth_200.DhanDepth200Feed`` keep working unchanged.

Endpoint: wss://full-depth-api.dhan.co/twohundreddepth
Max instruments: 1 per connection (Dhan API limitation)
Header layout: num_rows at offset 8 (security_id is implicit per connection)

IMPORTANT LIMITATION:
    Dhan's depth-200 API only supports ONE instrument per WebSocket connection.
    To subscribe to multiple instruments, you MUST create multiple DhanDepth200Feed
    instances, each with its own connection. Use Depth200ConnectionPool for
    managing multiple connections efficiently.

    Example:
        # Single instrument (direct)
        feed = DhanDepth200Feed(client_id, access_token, ("NSE", "12345"))
        
        # Multiple instruments (use connection pool)
        pool = Depth200ConnectionPool(client_id, access_token)
        feed1 = pool.get_feed(("NSE", "12345"))  # Instrument 1
        feed2 = pool.get_feed(("NSE", "67890"))  # Instrument 2
"""

from __future__ import annotations

import logging
from threading import RLock
from typing import TYPE_CHECKING, Dict, Tuple

from brokers.dhan.depth_feed_base import BinaryDepthFeed
from domain import MarketDepth
from infrastructure.event_bus import EventBus

__all__ = ["DhanDepth200Feed", "Depth200ConnectionPool"]

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from typing import TypeAlias


class DhanDepth200Feed(BinaryDepthFeed):
    """200-level market depth via WebSocket.

    CRITICAL LIMITATION: Only 1 instrument per connection allowed. The
    security_id is implicit (carried in the subscription, not in the wire
    format); see ``BinaryDepthFeed.header_carries_security_id=False``.
    """

    name = "dhan.depth_200"
    MAX_INSTRUMENTS = 1
    TOTAL_DEPTH_PACKETS = 200
    REQUEST_CODE = 23
    HEADER_SIZE = 12
    DEPTH_LEVEL_SIZE = 16
    BID_RESPONSE_CODE = 41
    ASK_RESPONSE_CODE = 51

    def __init__(
        self,
        client_id: str,
        access_token: str,
        instrument: tuple[str, str] | None = None,
        event_bus: EventBus | None = None,
    ):
        from config.endpoints import Dhan as _DhanEndpoints

        super().__init__(
            client_id=client_id,
            access_token=access_token,
            endpoint=_DhanEndpoints.WS_DEPTH_200,
            request_code=self.REQUEST_CODE,
            total_slots=200,
            subs_per_connection=1,
            depth_type="DEPTH_200",
            name=self.name,
            event_name="DEPTH_200",
            header_carries_security_id=False,
            event_bus=event_bus,
        )

        self._instrument = instrument
        if instrument:
            self.subscribe(instrument)

    # ── Depth-200: only one instrument ever, with a legacy error message ──
    def subscribe(self, instrument: tuple[str, str] | list[tuple[str, str]]) -> None:  # type: ignore[override]
        """Subscribe to a single instrument.

        Raises:
            ValueError: If already subscribed to an instrument (legacy
                error message ``"Only 1 instrument allowed for 200-level depth"``
                is preserved for backwards-compatible test assertions).
        """
        instruments = instrument if isinstance(instrument, list) else [instrument]

        # Legacy: depth-200 raises "Only 1 instrument allowed..." even when
        # the unified limit check would accept a single new instrument.
        [i for i in instruments if i in self._subscriptions]
        new_instruments = [i for i in instruments if i not in self._subscriptions]
        if not new_instruments:
            return
        if len(self._subscriptions) + len(new_instruments) > self.subs_per_connection:
            raise ValueError(
                f"Only {self.subs_per_connection} instrument allowed for "
                f"200-level depth. Already subscribed to "
                f"{self._subscriptions[0] if self._subscriptions else 'none'}"
            )

        self._subscriptions.extend(new_instruments)
        self._instrument = new_instruments[0]
        logger.info(
            "depth_200_subscribe",
            extra={"instrument": self._instrument},
        )

        if self._is_connected and self._ws:
            self._send_subscription(new_instruments)

    # ── Depth-200 specific lookup: single-instrument cache ─────────────────
    def latest_depth(self) -> MarketDepth | None:
        """Return the most-recent cached :class:`MarketDepth`."""
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
            depth_type="DEPTH_200",
        )


# =============================================================================
# Depth200ConnectionPool - Connection pooling for multiple instruments
# =============================================================================


class Depth200ConnectionPool:
    """Connection pool for managing multiple Dhan depth-200 WebSocket connections.
    
    Since Dhan's depth-200 API only supports 1 instrument per connection,
    this pool creates and manages separate connections for each instrument.
    
    Usage:
        pool = Depth200ConnectionPool(client_id, access_token)
        
        # Get or create a feed for an instrument
        feed1 = pool.get_feed(("NSE", "12345"))
        feed2 = pool.get_feed(("NSE", "67890"))
        
        # Access depth data
        depth1 = feed1.latest_depth()
        depth2 = feed2.latest_depth()
        
        # Cleanup
        pool.close_all()
    
    Thread Safety:
        All methods are thread-safe. Multiple threads can safely call get_feed()
        and access feeds concurrently.
    """
    
    InstrumentKey: TypeAlias = Tuple[str, str]  # (segment, security_id)
    
    def __init__(
        self,
        client_id: str,
        access_token: str,
        event_bus: EventBus | None = None,
        max_connections: int | None = None,
    ):
        """Initialize the connection pool.
        
        Args:
            client_id: Dhan client ID
            access_token: Dhan access token
            event_bus: Optional event bus for domain events
            max_connections: Maximum number of connections to maintain.
                           If None, no limit. If set and exceeded, oldest
                           unused connections may be closed.
        """
        self._client_id = client_id
        self._access_token = access_token
        self._event_bus = event_bus
        self._max_connections = max_connections
        self._feeds: Dict[Self.InstrumentKey, DhanDepth200Feed] = {}
        self._lock = RLock()
        
    def get_feed(self, instrument: InstrumentKey) -> DhanDepth200Feed:
        """Get or create a depth-200 feed for the given instrument.
        
        Uses WebSocket rate limiting to prevent exceeding broker connection limits.
        
        Args:
            instrument: Tuple of (segment, security_id) e.g. ("NSE", "12345")
            
        Returns:
            DhanDepth200Feed instance for the instrument
        """
        with self._lock:
            # Check if feed already exists
            if instrument in self._feeds:
                return self._feeds[instrument]
            
            # Check WebSocket rate limiting for new connections
            try:
                from brokers.dhan.resilience.websocket_rate_limiter_simple import get_dhan_ws_rate_limiter
                ws_rate_limiter = get_dhan_ws_rate_limiter()
                
                # Check if we can create a new connection
                if not ws_rate_limiter.can_create_depth_200_connection():
                    logger.warning(
                        "depth_200_pool_connection_rate_limited",
                        extra={"instrument": instrument},
                    )
                    # Wait for connection to become available
                    import time
                    while not ws_rate_limiter.can_create_depth_200_connection():
                        time.sleep(0.1)  # Wait 100ms and retry
                
            except ImportError:
                # WebSocket rate limiter not available, use local limit
                pass
            
            # Enforce max connections limit
            if self._max_connections and len(self._feeds) >= self._max_connections:
                # Close the oldest connection to make room
                oldest_key = next(iter(self._feeds))
                self._feeds[oldest_key].close()
                del self._feeds[oldest_key]
                logger.warning(
                    "depth_200_pool_eviction",
                    extra={"evicted_instrument": oldest_key, "new_instrument": instrument},
                )
            
            feed = DhanDepth200Feed(
                client_id=self._client_id,
                access_token=self._access_token,
                instrument=instrument,
                event_bus=self._event_bus,
            )
            self._feeds[instrument] = feed
            logger.debug(
                "depth_200_pool_feed_created",
                extra={"instrument": instrument, "total_feeds": len(self._feeds)},
            )
            
            return self._feeds[instrument]
    
    def has_feed(self, instrument: InstrumentKey) -> bool:
        """Check if a feed exists for the given instrument."""
        with self._lock:
            return instrument in self._feeds
    
    def remove_feed(self, instrument: InstrumentKey) -> bool:
        """Remove and close a feed for the given instrument.
        
        Returns:
            True if feed was found and removed, False otherwise
        """
        with self._lock:
            if instrument in self._feeds:
                self._feeds[instrument].close()
                del self._feeds[instrument]
                logger.info(
                    "depth_200_pool_feed_removed",
                    extra={"instrument": instrument, "remaining_feeds": len(self._feeds)},
                )
                return True
            return False
    
    def get_all_feeds(self) -> list[DhanDepth200Feed]:
        """Get all active feeds in the pool."""
        with self._lock:
            return list(self._feeds.values())
    
    def get_instruments(self) -> list[InstrumentKey]:
        """Get all instrument keys that have active feeds."""
        with self._lock:
            return list(self._feeds.keys())
    
    def close_all(self) -> None:
        """Close all feeds in the pool."""
        with self._lock:
            for instrument, feed in list(self._feeds.items()):
                try:
                    feed.close()
                except Exception as e:
                    logger.error(
                        "depth_200_pool_feed_close_error",
                        extra={"instrument": instrument, "error": str(e)},
                    )
            self._feeds.clear()
            logger.info("depth_200_pool_all_closed")
    
    def __len__(self) -> int:
        """Return the number of active feeds in the pool."""
        with self._lock:
            return len(self._feeds)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes all feeds."""
        self.close_all()
        return False
