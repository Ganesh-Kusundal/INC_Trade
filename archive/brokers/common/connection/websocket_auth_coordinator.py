"""Coordinate WebSocket re-authentication after token refresh."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WebSocketAuthCoordinator:
    """Apply token updates to long-lived WebSocket sessions."""

    @staticmethod
    def request_reconnect_on_token_change(feed: Any, new_token: str) -> None:
        """Close an active depth-feed socket so the loop reconnects with the new token."""
        update = getattr(feed, "update_token", None)
        if callable(update):
            update(new_token)
        reconnect = getattr(feed, "request_auth_reconnect", None)
        if callable(reconnect):
            reconnect()
            logger.debug(
                "ws_auth_reconnect_requested",
                extra={"feed": getattr(feed, "name", type(feed).__name__)},
            )

    @staticmethod
    def notify_depth_feeds(connection: Any, new_token: str) -> int:
        """Force reconnect on depth feeds that embed tokens in the URL."""
        count = 0
        for attr in ("depth_20_feed", "depth_200_feed", "_depth_20_feed", "_depth_200_feed"):
            feed = getattr(connection, attr, None)
            if feed is None:
                continue
            WebSocketAuthCoordinator.request_reconnect_on_token_change(feed, new_token)
            count += 1
        return count
