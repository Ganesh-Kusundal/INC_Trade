"""Shared stream health mixin — aggregates health across multiple feeds.

Both DhanProvider and UpstoxProvider had identical ~30-line stream_health
properties that iterate feeds, check running state, and aggregate
subscription counts.  This mixin eliminates that duplication.

Usage::

    class DhanProvider(ResolutionMixin, AsyncHttpMixin, StreamHealthMixin):
        _feeds = property returning list of active feeds
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from brokers.infrastructure.streaming.stream_health import (
    FreshnessState,
    StreamHealth,
    SubscriptionState,
    TransportState,
)

if TYPE_CHECKING:
    pass


@runtime_checkable
class FeedLike(Protocol):
    """Minimal protocol for a feed object that has is_running and health."""

    @property
    def is_running(self) -> bool: ...

    @property
    def health(self) -> StreamHealth: ...


class StreamHealthMixin:
    """Mixin that provides a shared stream_health property.

    Subclasses must define a ``_get_feeds`` method that returns a list
    of active feed objects (each having ``is_running`` and ``health``).
    """

    def _get_feeds(self) -> list[FeedLike]:
        """Return the list of active streaming feeds.

        MUST be overridden by each provider subclass.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement _get_feeds")

    @property
    def stream_health(self) -> StreamHealth:
        """Aggregate health of all streaming feeds."""
        feeds = self._get_feeds()
        if not feeds:
            return StreamHealth(
                transport=TransportState.CLOSED,
                subscription=SubscriptionState.NONE,
                freshness=FreshnessState.UNKNOWN,
                detail="No feeds created",
            )

        running = [f.is_running for f in feeds]
        if all(running):
            transport = TransportState.OPEN
        elif any(running):
            transport = TransportState.RECONNECTING
        else:
            transport = TransportState.CLOSED

        any_synced = False
        any_partial = False
        total_requested = 0
        total_subscribed = 0
        for f in feeds:
            if hasattr(f, "health"):
                h = f.health
                total_requested += h.requested_count
                total_subscribed += h.subscribed_count
                if h.subscribed_count > 0 and h.subscribed_count == h.requested_count and h.requested_count > 0:
                    any_synced = True
                elif h.subscribed_count > 0 and h.subscribed_count < h.requested_count:
                    any_partial = True

        if any_partial:
            sub_state = SubscriptionState.PARTIAL
        elif any_synced:
            sub_state = SubscriptionState.SYNCED
        else:
            sub_state = SubscriptionState.NONE

        return StreamHealth(
            transport=transport,
            subscription=sub_state,
            freshness=FreshnessState.UNKNOWN,
            subscribed_count=total_subscribed,
            requested_count=total_requested,
        )


__all__ = ["StreamHealthMixin"]
