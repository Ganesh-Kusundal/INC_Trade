"""ConnectionLifecycle — extracted lifecycle management for DhanConnection.

Previously inlined in :class:`~brokers.dhan.connection.DhanConnection`, this
helper owns the lifecycle of WebSocket services and the resolver refresher.

Responsibilities
----------------
* Creating and caching market feed, order stream, depth feeds, and polling feed
* Registering services with the :class:`LifecycleManager` (when present)
* Token-receiver self-registration for every service that needs token updates
* Deterministic shutdown via ``close()``

Usage
-----
Created by ``DhanConnection`` at init time::

    self._lifecycle_helper = ConnectionLifecycle(
        client=self._client,
        instruments=self.instruments,
        event_bus=self._event_bus,
        token_manager=self._token_manager,
        lifecycle=self._lifecycle,
        backfill_callback=backfill_callback,
        allow_live_orders=allow_live_orders,
    )
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from brokers.dhan.depth_20 import DhanDepth20Feed
from brokers.dhan.depth_200 import DhanDepth200Feed, Depth200ConnectionPool
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.resolver_refresher import ResolverRefresher
from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream, PollingMarketFeed
from infrastructure.event_bus import EventBus
from infrastructure.lifecycle import LifecycleManager

logger = logging.getLogger(__name__)


class ConnectionLifecycle:
    """Manages the lifecycle of Dhan WebSocket services and background tasks.

    Owns the creation, caching, and teardown of:
    - Market data feed (``DhanMarketFeed``)
    - Order stream (``DhanOrderStream``)
    - Polling market feed (``PollingMarketFeed``)
    - 20-level / 200-level depth feeds (``DhanDepth20Feed``, ``DhanDepth200Feed``)
    - Resolver refresher (``ResolverRefresher``)

    Thread safety: thread-safe via the caller's lock — external callers MUST
    hold the connection's mutex when calling factory methods.
    """

    def __init__(
        self,
        client: DhanHttpClient,
        instruments: SymbolResolver,
        *,
        register_token_receiver: Callable[[Callable[[str], None]], None],
        connection_owner: Any,
        event_bus: EventBus | None = None,
        lifecycle: LifecycleManager | None = None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None = None,
    ) -> None:
        self._client = client
        self._instruments = instruments
        self._register_token_receiver = register_token_receiver
        self._connection_owner = connection_owner
        self._event_bus = event_bus
        self._lifecycle = lifecycle
        self._backfill_callback = backfill_callback

        # Lazily-created services — None until first access
        self._market_feed: DhanMarketFeed | None = None
        self._order_stream: DhanOrderStream | None = None
        self._polling_feed: PollingMarketFeed | None = None
        self._depth_20_feed: DhanDepth20Feed | None = None
        self._depth_200_feed: DhanDepth200Feed | None = None
        self._depth_200_pool: Depth200ConnectionPool | None = None
        self._resolver_refresher: ResolverRefresher | None = None

    # ── Factory methods ─────────────────────────────────────────────────

    def create_market_feed(
        self,
        access_token: str | None = None,
        instruments: list[tuple] | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ) -> DhanMarketFeed:
        """Create and return a DhanMarketFeed.

        If an existing feed exists, returns it (singleton per connection).
        Registers with lifecycle manager and token receiver on creation.
        """
        if self._market_feed is not None:
            return self._market_feed

        feed = DhanMarketFeed(
            client_id=self._client.client_id,
            access_token=access_token,
            instruments=instruments or [],
            resolver=self._instruments,
            access_token_fn=access_token_fn,
            event_bus=self._event_bus,
            backfill_callback=self._backfill_callback,
        )
        self._market_feed = feed
        self._register_token_receiver(feed.update_token)
        self._register_with_lifecycle(feed, feed.name)
        return feed

    def create_order_stream(
        self,
        access_token: str | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ) -> DhanOrderStream:
        """Create and return a DhanOrderStream.

        If an existing stream exists, returns it (singleton per connection).
        Registers with lifecycle manager and token receiver on creation.
        """
        if self._order_stream is not None:
            return self._order_stream

        stream = DhanOrderStream(
            client_id=self._client.client_id,
            access_token=access_token,
            access_token_fn=access_token_fn,
            event_bus=self._event_bus,
        )
        self._order_stream = stream
        self._register_token_receiver(stream.update_token)
        self._register_with_lifecycle(stream, stream.name)
        return stream

    def create_depth_20_feed(
        self,
        access_token: str | None = None,
        instrument: tuple[str, str] | None = None,
    ) -> DhanDepth20Feed:
        """Create and return a DhanDepth20Feed for 20-level depth.
        
        Enforces singleton pattern: returns existing feed if already created.
        This ensures exactly one Market Depth WebSocket connection per broker
        instance, preventing rate limit violations.
        
        Args:
            access_token: Optional access token override
            instrument: Optional instrument tuple (segment, security_id)
            
        Returns:
            The singleton DhanDepth20Feed instance
        """
        if self._depth_20_feed is not None:
            # P0 Fix: Enforce singleton - return existing feed
            logger.debug(
                "depth_20_feed_singleton_reuse",
                extra={"existing_feed": id(self._depth_20_feed)},
            )
            return self._depth_20_feed
        
        feed = DhanDepth20Feed(
            client_id=self._client.client_id,
            access_token=access_token or self._client.access_token,
            instruments=[instrument] if instrument else [],
            event_bus=self._event_bus,
        )
        self._depth_20_feed = feed
        if hasattr(feed, "update_token"):
            self._register_token_receiver(feed.update_token)
        self._register_with_lifecycle(feed, feed.name)
        
        logger.info(
            "depth_20_feed_singleton_created",
            extra={"feed_id": id(feed), "client_id": self._client.client_id},
        )
        return feed

    def create_depth_200_feed(
        self,
        access_token: str | None = None,
        instrument: tuple[str, str] | None = None,
    ) -> DhanDepth200Feed:
        """Create and return a DhanDepth200Feed for 200-level depth.
        
        Uses Depth200ConnectionPool to manage multiple connections since Dhan's
        depth-200 API only supports 1 instrument per connection. This allows
        multiple instruments to be subscribed to depth-200 data without
        violating broker rate limits.
        
        Args:
            access_token: Optional access token override
            instrument: Optional instrument tuple (segment, security_id)
            
        Returns:
            DhanDepth200Feed instance from the connection pool
        """
        # Initialize the connection pool if it doesn't exist
        if self._depth_200_pool is None:
            self._depth_200_pool = Depth200ConnectionPool(
                client_id=self._client.client_id,
                access_token=access_token or self._client.access_token,
                event_bus=self._event_bus,
            )
            logger.info(
                "depth_200_connection_pool_created",
                extra={"client_id": self._client.client_id},
            )
        
        # If no instrument specified, return a placeholder feed
        # (this maintains backward compatibility with existing code)
        if instrument is None:
            # For backward compatibility, we still need a default feed
            # This will be used when instrument is specified later
            if self._depth_200_feed is None:
                # Create a temporary feed that will be replaced when instrument is provided
                self._depth_200_feed = DhanDepth200Feed(
                    client_id=self._client.client_id,
                    access_token=access_token or self._client.access_token,
                    instrument=None,
                    event_bus=self._event_bus,
                )
                if hasattr(self._depth_200_feed, "update_token"):
                    self._register_token_receiver(self._depth_200_feed.update_token)
                self._register_with_lifecycle(self._depth_200_feed, self._depth_200_feed.name)
            return self._depth_200_feed
        
        # Get or create a feed for the specific instrument from the pool
        feed = self._depth_200_pool.get_feed(instrument)
        
        # For backward compatibility, also store as the "current" feed
        # This ensures existing code that accesses conn.depth_200_feed still works
        if self._depth_200_feed is None:
            self._depth_200_feed = feed
        
        return feed

    def create_polling_feed(
        self,
        instruments: list[tuple],
        interval_seconds: float = 2.0,
    ) -> PollingMarketFeed:
        """Create and return a PollingMarketFeed."""
        feed = PollingMarketFeed(
            http_client=self._client,
            resolver=self._instruments,
            instruments=instruments,
            interval_seconds=interval_seconds,
        )
        self._polling_feed = feed
        self._register_with_lifecycle(feed, feed.name)
        return feed

    def get_or_create_resolver_refresher(
        self,
        interval_seconds: int = 24 * 3600,
        on_success: Any = None,
        on_error: Any = None,
    ) -> ResolverRefresher:
        """Return the singleton ResolverRefresher for this connection."""
        if self._resolver_refresher is None:
            self._resolver_refresher = ResolverRefresher(
                connection=self._connection_owner,
                interval_seconds=interval_seconds,
                on_success=on_success,
                on_error=on_error,
            )
        return self._resolver_refresher

    def register_resolver_refresher_with_lifecycle(
        self,
        interval_seconds: int = 24 * 3600,
    ) -> ResolverRefresher | None:
        """Create the refresher and register it with the lifecycle manager.

        Returns None if the connection was constructed without a LifecycleManager.
        """
        if self._lifecycle is None:
            logger.debug("resolver_refresher_not_registered: connection has no lifecycle manager")
            return None
        refresher = self.get_or_create_resolver_refresher(interval_seconds=interval_seconds)
        self._register_with_lifecycle(refresher, refresher.name)
        return refresher

    # ── Service references for gateway access ───────────────────────────

    @property
    def market_feed(self) -> DhanMarketFeed | None:
        return self._market_feed

    @market_feed.setter
    def market_feed(self, value: DhanMarketFeed) -> None:
        self._market_feed = value

    @property
    def order_stream(self) -> DhanOrderStream | None:
        return self._order_stream

    @order_stream.setter
    def order_stream(self, value: DhanOrderStream) -> None:
        self._order_stream = value

    @property
    def depth_20_feed(self) -> DhanDepth20Feed | None:
        return self._depth_20_feed

    @depth_20_feed.setter
    def depth_20_feed(self, value: DhanDepth20Feed) -> None:
        self._depth_20_feed = value

    @property
    def depth_200_feed(self) -> DhanDepth200Feed | None:
        return self._depth_200_feed

    @depth_200_feed.setter
    def depth_200_feed(self, value: DhanDepth200Feed) -> None:
        self._depth_200_feed = value

    @property
    def depth_200_pool(self) -> Depth200ConnectionPool | None:
        return self._depth_200_pool

    @property
    def polling_feed(self) -> PollingMarketFeed | None:
        return self._polling_feed

    @polling_feed.setter
    def polling_feed(self, value: PollingMarketFeed) -> None:
        self._polling_feed = value

    @property
    def resolver_refresher(self) -> ResolverRefresher | None:
        return self._resolver_refresher

    # ── Lifecycle registration ──────────────────────────────────────────

    def _register_with_lifecycle(self, service: Any, name: str) -> None:
        """Register a ManagedService with the lifecycle manager if present."""
        if self._lifecycle is not None and name not in self._lifecycle.service_names():
            try:
                self._lifecycle.register(service)
            except Exception as exc:
                logger.debug("lifecycle_register_failed for %s: %s", name, exc)

    # ── Shutdown ─────────────────────────────────────────────────────────

    def close(self, timeout_seconds: float = 5.0) -> None:
        """Stop all services deterministically within the given timeout."""
        # Stop the resolver refresher
        if self._resolver_refresher is not None:
            try:
                self._resolver_refresher.stop(timeout_seconds=timeout_seconds)
            except Exception as exc:
                logger.warning("resolver_refresher_stop_failed: %s", exc)

        # Stop WebSocket services via their ManagedService.stop()
        for svc in (
            self._market_feed,
            self._order_stream,
            self._polling_feed,
            self._depth_20_feed,
            self._depth_200_feed,
        ):
            if svc is not None:
                try:
                    svc.stop(timeout_seconds=timeout_seconds)
                except Exception as exc:
                    logger.warning("%s_stop_failed: %s", getattr(svc, "name", svc), exc)

        # Close the depth-200 connection pool
        if self._depth_200_pool is not None:
            try:
                self._depth_200_pool.close_all()
            except Exception as exc:
                logger.warning("depth_200_pool_close_failed: %s", exc)
