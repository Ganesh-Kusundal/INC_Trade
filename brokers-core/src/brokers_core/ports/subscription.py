"""Subscription port — unified contract for streaming subscriptions.

This protocol replaces the 6+ different ``subscribe()`` signatures scattered
across adapters, routers, and managers. All streaming backends implement this
single interface for consistent subscription management.

Usage::

    class DhanStreamingManager(SubscriptionPort):
        def subscribe(self, key, exchange, callback):
            ...
        def unsubscribe(self, key, exchange):
            ...

The ``key`` parameter is always the composite key ``"{exchange}:{symbol}"``
(e.g., ``"NSE:RELIANCE"``). This ensures a single subscription identity
across all backends.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SubscriptionPort(Protocol):
    """Unified subscription contract for all streaming backends.

    This protocol standardizes the subscribe/unsubscribe interface that
    was previously scattered across 6+ different signatures:

    - ``StreamingDataProvider.subscribe(instrument, callback)``
    - ``StreamingPort.subscribe_quotes(symbols, exchange, callback)``
    - ``StreamingRouter.subscribe(key, exchange, callback)``
    - ``SubscriptionManager.subscribe(key, exchange, callback)``
    - ``EventBus.subscribe(channel, handler)``
    - ``Instrument.subscribe(callback)``

    All implementations now use the same ``subscribe(key, exchange, callback)``
    signature with composite key identity.
    """

    def subscribe(
        self,
        key: str,
        exchange: str = "",
        callback: Callable[[Any], None] | None = None,
    ) -> Any:
        """Subscribe to live market data for an instrument.

        Args:
            key: Composite key ``"{exchange}:{symbol}"`` (e.g., ``"NSE:RELIANCE"``).
            exchange: Exchange code (e.g., ``"NSE"``, ``"NFO"``).
            callback: Optional callable invoked with each new tick/quote.

        Returns:
            A handle for controlling the subscription (optional).
        """
        ...

    def unsubscribe(
        self,
        key: str,
        exchange: str,
    ) -> None:
        """Unsubscribe from live market data for an instrument.

        Args:
            key: Composite key ``"{exchange}:{symbol}"``.
            exchange: Exchange code.
        """
        ...

    def is_subscribed(self, key: str, exchange: str = "") -> bool:
        """Check if a key has an active subscription.

        Args:
            key: Composite key ``"{exchange}:{symbol}"``.
            exchange: Exchange code (unused, for interface compliance).

        Returns:
            True if subscribed, False otherwise.
        """
        ...

    def active_count(self) -> int:
        """Number of currently active subscriptions."""
        ...


__all__ = [
    "SubscriptionPort",
]
