"""WebSocket Connection Manager — enforces single connection per stream type.

This module provides a centralized connection manager that ensures exactly one
WebSocket connection exists per stream type (market feed, order stream, depth feeds)
per broker instance, with proper lifecycle management and thread safety.

Key Features:
- Singleton enforcement for each WebSocket stream type
- Thread-safe connection creation and access
- Automatic lifecycle management (start/stop)
- Connection health monitoring
- Subscription management across connections
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from brokers.dhan.websocket.market_feed import DhanMarketFeed
from brokers.dhan.websocket.order_stream import DhanOrderStream

logger = logging.getLogger(__name__)


class WebSocketConnectionManager:
    """Centralized manager for WebSocket connections with singleton enforcement.
    
    This manager ensures that only one WebSocket connection exists for each
    stream type per broker instance, preventing rate limit violations and
    connection proliferation.
    
    Stream Types Managed:
    - market_feed: Real-time market data feed (DhanMarketFeed)
    - order_stream: Real-time order update stream (DhanOrderStream)
    
    Thread Safety:
    All methods are thread-safe and can be called concurrently from multiple threads.
    """
    
    def __init__(self, client_id: str, access_token: str | None = None, event_bus: Any = None):
        """Initialize the WebSocket connection manager.
        
        Args:
            client_id: Dhan client ID
            access_token: Optional access token
            event_bus: Optional event bus for domain events
        """
        self._client_id = client_id
        self._access_token = access_token
        self._event_bus = event_bus
        self._lock = threading.RLock()
        
        # Singleton instances for each stream type
        self._market_feed: DhanMarketFeed | None = None
        self._order_stream: DhanOrderStream | None = None
        
        # Connection health tracking
        self._connection_stats = {
            "market_feed": {"created": False, "connected": False, "start_count": 0},
            "order_stream": {"created": False, "connected": False, "start_count": 0},
        }
    
    @property
    def client_id(self) -> str:
        return self._client_id
    
    @property
    def access_token(self) -> str | None:
        return self._access_token
    
    @access_token.setter
    def access_token(self, value: str) -> None:
        """Update the access token and propagate to existing connections."""
        self._access_token = value
        with self._lock:
            if self._market_feed is not None:
                self._market_feed.update_token(value)
            if self._order_stream is not None:
                self._order_stream.update_token(value)
    
    def get_market_feed(
        self,
        instruments: list[tuple] | None = None,
        access_token_fn: Callable[[], str] | None = None,
        backfill_callback: Callable[[str, Any, Any], list[dict]] | None = None,
    ) -> DhanMarketFeed:
        """Get or create the singleton market feed connection.
        
        Returns the same DhanMarketFeed instance on every call, ensuring
        exactly one market data WebSocket connection per broker instance.
        
        Args:
            instruments: Optional initial instruments to subscribe to
            access_token_fn: Optional callable for token refresh
            backfill_callback: Optional callback for reconnection backfill
            
        Returns:
            The singleton DhanMarketFeed instance
        """
        with self._lock:
            if self._market_feed is not None:
                self._connection_stats["market_feed"]["connected"] = self._market_feed.is_connected
                return self._market_feed
            
            # Create new market feed
            self._market_feed = DhanMarketFeed(
                client_id=self._client_id,
                access_token=self._access_token,
                instruments=instruments or [],
                access_token_fn=access_token_fn,
                event_bus=self._event_bus,
                backfill_callback=backfill_callback,
            )
            
            self._connection_stats["market_feed"]["created"] = True
            self._connection_stats["market_feed"]["start_count"] += 1
            
            logger.info(
                "websocket_connection_manager.market_feed_created",
                extra={
                    "client_id": self._client_id,
                    "feed_id": id(self._market_feed),
                    "instruments_count": len(instruments or []),
                },
            )
            
            return self._market_feed
    
    def get_order_stream(
        self,
        access_token_fn: Callable[[], str] | None = None,
    ) -> DhanOrderStream:
        """Get or create the singleton order stream connection.
        
        Returns the same DhanOrderStream instance on every call, ensuring
        exactly one order stream WebSocket connection per broker instance.
        
        Args:
            access_token_fn: Optional callable for token refresh
            
        Returns:
            The singleton DhanOrderStream instance
        """
        with self._lock:
            if self._order_stream is not None:
                self._connection_stats["order_stream"]["connected"] = self._order_stream.is_connected
                return self._order_stream
            
            # Create new order stream
            self._order_stream = DhanOrderStream(
                client_id=self._client_id,
                access_token=self._access_token,
                access_token_fn=access_token_fn,
                event_bus=self._event_bus,
            )
            
            self._connection_stats["order_stream"]["created"] = True
            self._connection_stats["order_stream"]["start_count"] += 1
            
            logger.info(
                "websocket_connection_manager.order_stream_created",
                extra={
                    "client_id": self._client_id,
                    "stream_id": id(self._order_stream),
                },
            )
            
            return self._order_stream
    
    def start_all(self) -> None:
        """Start all WebSocket connections."""
        with self._lock:
            if self._market_feed is not None and not self._market_feed.is_connected:
                self._market_feed.start()
                self._connection_stats["market_feed"]["start_count"] += 1
            
            if self._order_stream is not None and not self._order_stream.is_connected:
                self._order_stream.start()
                self._connection_stats["order_stream"]["start_count"] += 1
    
    def stop_all(self, timeout_seconds: float = 5.0) -> None:
        """Stop all WebSocket connections."""
        with self._lock:
            if self._market_feed is not None:
                try:
                    self._market_feed.stop(timeout_seconds=timeout_seconds)
                except Exception as exc:
                    logger.warning("market_feed_stop_failed: %s", exc)
                self._connection_stats["market_feed"]["connected"] = False
            
            if self._order_stream is not None:
                try:
                    self._order_stream.stop(timeout_seconds=timeout_seconds)
                except Exception as exc:
                    logger.warning("order_stream_stop_failed: %s", exc)
                self._connection_stats["order_stream"]["connected"] = False
    
    def close_all(self) -> None:
        """Close all WebSocket connections."""
        self.stop_all()
        with self._lock:
            self._market_feed = None
            self._order_stream = None
    
    def get_connection_stats(self) -> dict[str, Any]:
        """Get connection statistics for monitoring and observability.
        
        Returns:
            Dictionary with connection creation and usage statistics
        """
        with self._lock:
            return {
                "market_feed": {
                    "exists": self._market_feed is not None,
                    "connected": getattr(self._market_feed, "is_connected", False) if self._market_feed else False,
                    **self._connection_stats["market_feed"],
                },
                "order_stream": {
                    "exists": self._order_stream is not None,
                    "connected": getattr(self._order_stream, "is_connected", False) if self._order_stream else False,
                    **self._connection_stats["order_stream"],
                },
                "total_connections": sum(
                    1 for conn in [self._market_feed, self._order_stream] if conn is not None
                ),
            }
    
    def ensure_single_connections(self) -> None:
        """Verify that only single connections exist for each stream type.
        
        This method can be used for testing and validation to ensure the
        singleton pattern is being enforced correctly.
        
        Raises:
            AssertionError: If multiple connections exist for any stream type
        """
        with self._lock:
            # For market feed, we should have at most one connection
            if self._market_feed is not None:
                # Check that the feed is not connected multiple times
                # This is a sanity check - the feed itself should manage its connection
                assert self._connection_stats["market_feed"]["start_count"] <= 1, \
                    f"Market feed started multiple times: {self._connection_stats['market_feed']['start_count']}"
            
            # For order stream, we should have at most one connection
            if self._order_stream is not None:
                assert self._connection_stats["order_stream"]["start_count"] <= 1, \
                    f"Order stream started multiple times: {self._connection_stats['order_stream']['start_count']}"
            
            logger.debug(
                "websocket_connection_manager.single_connections_verified",
                extra=self.get_connection_stats(),
            )