"""Subscription Manager — centralized subscription tracking with deduplication.

Ensures one WebSocket subscription per instrument key, with reference
counting so multiple consumers share a single stream. Auto-unsubscribes
when the last consumer disconnects.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class SubscriptionState:
    """Tracks the lifecycle of a single subscription.

    States:
        INACTIVE → SUBSCRIBING → ACTIVE → UNSUBSCRIBING → INACTIVE
    """

    INACTIVE = "inactive"
    SUBSCRIBING = "subscribing"
    ACTIVE = "active"
    UNSUBSCRIBING = "unsubscribing"

    def __init__(self) -> None:
        self._state = self.INACTIVE

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state == self.ACTIVE

    def transition_to(self, new_state: str) -> None:
        valid = {
            (self.INACTIVE, self.SUBSCRIBING),
            (self.SUBSCRIBING, self.ACTIVE),
            (self.ACTIVE, self.UNSUBSCRIBING),
            (self.UNSUBSCRIBING, self.INACTIVE),
            (self.ACTIVE, self.INACTIVE),  # Fast path
            (self.SUBSCRIBING, self.INACTIVE),  # Failure path
        }
        if (self._state, new_state) not in valid:
            logger.warning(
                "Invalid subscription state transition: %s → %s",
                self._state,
                new_state,
            )
            return
        self._state = new_state


class SubscriptionManager:
    """Thread-safe subscription tracker with deduplication and reference counting.

    Ensures only one subscription per instrument key, regardless of how many
    consumers request it. Auto-unsubscribes when the last consumer leaves.

    Args:
        stream_adapter: The streaming adapter to delegate subscribe/unsubscribe to.
            Must support subscribe(key, exchange) and unsubscribe(key, exchange).
    """

    def __init__(self, stream_adapter: Any) -> None:
        self._stream = stream_adapter
        self._lock = threading.RLock()
        # key -> reference count
        self._ref_counts: dict[str, int] = {}
        # key -> SubscriptionState
        self._states: dict[str, SubscriptionState] = {}
        # key -> list of callbacks
        self._callbacks: dict[str, list[Callable[[Any], None]]] = {}

    # ── Public API ────────────────────────────────────────────────────

    def subscribe(
        self,
        key: str,
        exchange: str = "NSE",
        callback: Callable[[Any], None] | None = None,
    ) -> None:
        """Subscribe to an instrument stream.

        Increments reference count. If this is the first consumer,
        actually subscribes through the stream adapter.

        Args:
            key: Composite key ``{exchange}:{symbol}``.
            exchange: Exchange code.
            callback: Optional callback for tick data.
        """
        with self._lock:
            if key not in self._ref_counts:
                self._ref_counts[key] = 0
                self._states[key] = SubscriptionState()
                self._callbacks[key] = []

            was_first = self._ref_counts[key] == 0
            self._ref_counts[key] += 1

            if callback is not None and callback not in self._callbacks[key]:
                self._callbacks[key].append(callback)

            if was_first:
                logger.debug(
                    "SubscriptionManager: first subscribe for %s",
                    key,
                )
                self._states[key].transition_to(SubscriptionState.SUBSCRIBING)
                self._stream.subscribe(key, exchange)
                self._states[key].transition_to(SubscriptionState.ACTIVE)
            else:
                logger.debug(
                    "SubscriptionManager: ref count increased for %s → %d",
                    key,
                    self._ref_counts[key],
                )

            return None

    def unsubscribe(
        self,
        key: str,
        exchange: str = "NSE",
        callback: Callable[[Any], None] | None = None,
    ) -> None:
        """Unsubscribe from an instrument stream.

        Decrements reference count. If this was the last consumer,
        actually unsubscribes through the stream adapter.

        Args:
            key: Composite key ``{exchange}:{symbol}``.
            exchange: Exchange code.
            callback: If provided, removes this specific callback.
        """
        with self._lock:
            if key not in self._ref_counts:
                logger.warning(
                    "SubscriptionManager: unsubscribe for unknown key %s",
                    key,
                )
                return

            # Remove callback if provided
            if callback is not None and key in self._callbacks:
                if callback in self._callbacks[key]:
                    self._callbacks[key].remove(callback)

            self._ref_counts[key] -= 1

            if self._ref_counts[key] <= 0:
                # Last consumer — actually unsubscribe
                logger.debug(
                    "SubscriptionManager: last consumer for %s — unsubscribing",
                    key,
                )
                state = self._states.get(key)
                if state:
                    state.transition_to(SubscriptionState.UNSUBSCRIBING)
                self._stream.unsubscribe(key, exchange)
                if state:
                    state.transition_to(SubscriptionState.INACTIVE)
                # Clean up
                del self._ref_counts[key]
                if key in self._states:
                    del self._states[key]
                if key in self._callbacks:
                    del self._callbacks[key]
            else:
                logger.debug(
                    "SubscriptionManager: ref count decreased for %s → %d",
                    key,
                    self._ref_counts[key],
                )

    def dispatch_tick(self, key: str, data: Any) -> None:
        """Dispatch tick data to all registered callbacks for a key.

        Args:
            key: Composite key ``{exchange}:{symbol}``.
            data: Tick data to dispatch.
        """
        with self._lock:
            callbacks = list(self._callbacks.get(key, []))
        for cb in callbacks:
            try:
                cb(data)
            except Exception as exc:
                logger.warning(
                    "SubscriptionManager: callback error for %s: %s",
                    key,
                    exc,
                )

    # ── Query Methods ─────────────────────────────────────────────────

    @property
    def active_subscriptions(self) -> list[str]:
        """List of currently active subscription keys."""
        with self._lock:
            return [k for k, s in self._states.items() if s.is_active]

    @property
    def total_ref_counts(self) -> int:
        """Total reference count across all subscriptions."""
        with self._lock:
            return sum(self._ref_counts.values())

    def ref_count(self, key: str) -> int:
        """Reference count for a specific subscription.

        Args:
            key: Composite key.

        Returns:
            Reference count, or 0 if not subscribed.
        """
        with self._lock:
            return self._ref_counts.get(key, 0)

    def is_subscribed(self, key: str) -> bool:
        """Check if a key has active subscription.

        Args:
            key: Composite key.

        Returns:
            True if subscribed with active state.
        """
        with self._lock:
            state = self._states.get(key)
            return state is not None and state.is_active

    def clear(self) -> None:
        """Clear all subscriptions (for testing / cleanup)."""
        with self._lock:
            for key in list(self._ref_counts.keys()):
                exchange = key.split(":")[0] if ":" in key else "NSE"
                self._stream.unsubscribe(key, exchange)
            self._ref_counts.clear()
            self._states.clear()
            self._callbacks.clear()
