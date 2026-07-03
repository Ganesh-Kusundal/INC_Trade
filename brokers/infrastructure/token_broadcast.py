"""Centralized token lifecycle management.

Provides thread-safe token broadcast to registered consumers,
health tracking, and state management. Replaces broker-specific
TokenBroadcast implementations.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class TokenConsumer(Protocol):
    """Protocol for components that need token updates."""

    def update_token(self, token: str) -> None:
        """Receive an updated access token."""
        ...


TokenCallback = Callable[[str], None]


class TokenManager:
    """Thread-safe token lifecycle manager.

    Manages token distribution to all registered consumers,
    tracks current token state, and provides health metrics.

    Usage::

        manager = TokenManager()
        manager.register_consumer(http_client)
        manager.register_consumer(streaming_client)
        manager.broadcast_token(new_token)
        assert manager.current_token() == new_token
    """

    def __init__(self, initial_token: str = "") -> None:
        self._consumers: list[TokenConsumer | TokenCallback] = []
        self._current_token: str = initial_token
        self._lock = threading.Lock()

    def register_consumer(
        self, consumer: TokenConsumer | TokenCallback
    ) -> TokenConsumer | TokenCallback:
        """Register a consumer to receive token updates.

        If a token is already available, the consumer is called immediately
        with the current token.

        Args:
            consumer: A TokenConsumer instance or a callable accepting a token string.

        Returns:
            The registered consumer (for chaining / backward compat).
        """
        with self._lock:
            if consumer not in self._consumers:
                self._consumers.append(consumer)
                if self._current_token:
                    self._notify_consumer(consumer)
        return consumer

    def unregister_consumer(self, consumer: TokenConsumer | TokenCallback) -> None:
        """Unregister a consumer from token updates."""
        with self._lock:
            self._consumers = [c for c in self._consumers if c is not consumer]

    def broadcast_token(self, token: str) -> None:
        """Deliver a new token to all registered consumers.

        This is a fire-and-forget broadcast: individual consumer failures
        are logged but do not prevent delivery to other consumers.
        """
        with self._lock:
            self._current_token = token
            consumers = list(self._consumers)
        for consumer in consumers:
            self._notify_consumer(consumer)

    def current_token(self) -> str:
        """Return the current access token."""
        with self._lock:
            return self._current_token

    def health(self) -> dict:
        """Return health snapshot for monitoring."""
        with self._lock:
            return {
                "consumer_count": len(self._consumers),
                "current_token_present": bool(self._current_token),
            }

    def consumer_count(self) -> int:
        """Return the number of registered consumers."""
        with self._lock:
            return len(self._consumers)

    def _notify_consumer(self, consumer: TokenConsumer | TokenCallback) -> None:
        """Notify a single consumer, logging but not propagating errors."""
        try:
            if isinstance(consumer, TokenConsumer):
                consumer.update_token(self._current_token)
            else:
                consumer(self._current_token)
        except Exception:
            logger.exception("token_broadcast_failed")
