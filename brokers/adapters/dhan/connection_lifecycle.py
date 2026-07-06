"""Connection lifecycle management for Dhan broker.

Manages the lifecycle of WebSocket services and background tasks.
Used by DhanConnection to coordinate market feed, order stream, and depth feeds.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from inc_trade.infrastructure.lifecycle import LifecycleManager

from brokers.adapters.dhan.depth20 import DhanDepth20Stream
from brokers.adapters.dhan.depth200 import Depth200ConnectionPool

logger = logging.getLogger(__name__)


class ConnectionLifecycle:
    """Manages lifecycle of Dhan WebSocket services.

    Owns creation, caching, and teardown of:
    - Market data feed
    - Order stream
    - Polling market feed
    - 20-level / 200-level depth feeds
    """

    def __init__(
        self,
        client_id: str,
        access_token: str | Callable[[], str] | None = None,
        event_bus: Any = None,
        lifecycle: LifecycleManager | None = None,
    ):
        self._client_id = client_id
        self._access_token = access_token
        self._event_bus = event_bus
        self._lifecycle = lifecycle

        # Lazily-created services
        self._market_feed: Any = None
        self._order_stream: Any = None
        self._polling_feed: Any = None
        self._depth_20_feed: DhanDepth20Stream | None = None
        self._depth_200_feed: Any = None
        self._depth_200_pool: Depth200ConnectionPool | None = None

    def create_depth_20_feed(
        self,
        access_token: str | None = None,
        instruments: list[tuple[str, str]] | None = None,
    ) -> DhanDepth20Stream:
        """Create and return a DhanDepth20Feed for 20-level depth.

        Enforces singleton pattern: returns existing feed if already created.
        """
        if self._depth_20_feed is not None:
            logger.debug(
                "depth_20_feed_singleton_reuse",
                extra={"existing_feed": id(self._depth_20_feed)},
            )
            return self._depth_20_feed

        feed = DhanDepth20Stream(
            client_id=self._client_id,
            access_token=access_token or self._access_token,
            instrument=instruments[0] if instruments else None,
            event_bus=self._event_bus,
        )
        self._depth_20_feed = feed
        self._register_with_lifecycle(feed, feed.name)

        logger.info(
            "depth_20_feed_singleton_created",
            extra={"feed_id": id(feed), "client_id": self._client_id},
        )
        return feed

    def create_depth_200_feed(
        self,
        access_token: str | None = None,
        instrument: tuple[str, str] | None = None,
    ) -> Any:
        """Create and return a DhanDepth200Feed.

        Uses Depth200ConnectionPool to manage multiple connections.
        """
        if self._depth_200_pool is None:
            self._depth_200_pool = Depth200ConnectionPool(
                client_id=self._client_id,
                access_token=access_token or self._access_token,
                event_bus=self._event_bus,
            )
            logger.info(
                "depth_200_connection_pool_created",
                extra={"client_id": self._client_id},
            )

        if instrument is None:
            if self._depth_200_feed is None:
                from brokers.adapters.dhan.depth200 import DhanDepth200Stream

                self._depth_200_feed = DhanDepth200Stream(
                    client_id=self._client_id,
                    access_token=access_token or self._access_token,
                    event_bus=self._event_bus,
                )
            return self._depth_200_feed

        feed = self._depth_200_pool.get_feed(instrument)

        if self._depth_200_feed is None:
            self._depth_200_feed = feed

        return feed

    # ── Service references for gateway access ─────────────────────────────

    @property
    def depth_20_feed(self) -> DhanDepth20Stream | None:
        return self._depth_20_feed

    @depth_20_feed.setter
    def depth_20_feed(self, value: DhanDepth20Stream) -> None:
        self._depth_20_feed = value

    @property
    def depth_200_feed(self) -> Any:
        return self._depth_200_feed

    @depth_200_feed.setter
    def depth_200_feed(self, value: Any) -> None:
        self._depth_200_feed = value

    @property
    def depth_200_pool(self) -> Depth200ConnectionPool | None:
        return self._depth_200_pool

    # ── Lifecycle registration ──────────────────────────────────────────────

    def _register_with_lifecycle(self, service: Any, name: str) -> None:
        """Register a ManagedService with the lifecycle manager if present."""
        if self._lifecycle is not None:
            try:
                self._lifecycle.register(service)
            except Exception as exc:
                logger.debug("lifecycle_register_failed for %s: %s", name, exc)

    # ── Shutdown ───────────────────────────────────────────────────────────

    def close(self, timeout_seconds: float = 5.0) -> None:
        """Stop all services deterministically within the given timeout."""
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
                    logger.warning(
                        "%s_stop_failed: %s", getattr(svc, "name", "unknown"), exc
                    )

        if self._depth_200_pool is not None:
            try:
                self._depth_200_pool.close_all()
            except Exception as exc:
                logger.warning("depth_200_pool_close_failed: %s", exc)
