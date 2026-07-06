"""Streaming Router — routes subscribe/unsubscribe to the correct streaming backend.

Architecture::

    MarketDataContext
        │
        ▼
    StreamingRouter
        │
        ├── WebSocket backend (primary)
        │       └── subscribe/unsubscribe delegated to streaming adapter
        │
        └── Polling fallback (when WebSocket unavailable)
                └── Periodic polling via MarketDataPort

The router supports multiple backends with priority-based selection.
It handles reconnection strategy delegation and heartbeat management.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from brokers.ports.subscription import SubscriptionPort

logger = logging.getLogger(__name__)


class StreamingBackend:
    """Represents a single streaming backend (WebSocket, polling, etc.).

    Attributes:
        name: Backend identifier (e.g., ``"websocket"``, ``"polling"``).
        priority: Selection priority (lower = higher priority).
        adapter: The underlying streaming adapter object.
        is_available: Whether this backend is currently usable.
    """

    def __init__(
        self,
        name: str,
        priority: int,
        adapter: Any,
        is_available: bool = True,
    ) -> None:
        self.name = name
        self.priority = priority
        self.adapter = adapter
        self.is_available = is_available


class StreamingRouter(SubscriptionPort):
    """Routes subscribe/unsubscribe requests to the best available backend.

    Implements :class:`SubscriptionPort` for a unified streaming interface.
    Supports composite-key subscriptions (``{exchange}:{symbol}``) with
    priority-based backend selection and automatic fallback.

    Supports two calling conventions:
    - SubscriptionPort: ``subscribe(key, exchange, callback)``
    - Legacy: ``subscribe(key, callback)`` (exchange defaults to empty string)

    Supports:
    - Priority-based backend selection (WebSocket > polling)
    - Automatic fallback when the primary backend is unavailable
    - Reconnect strategy delegation to the backend adapter
    - Heartbeat management (delegated to adapter)
    - Active subscription tracking across all backends

    Args:
        backends: Optional initial list of StreamingBackend instances.
    """

    def __init__(self, backends: list[StreamingBackend] | None = None) -> None:
        self._backends: list[StreamingBackend] = list(backends or [])
        self._active_subscriptions: set[str] = set()
        self._callbacks: dict[str, list[Callable[[Any], None]]] = {}

    # ── Backend Management ────────────────────────────────────────────

    def add_backend(self, backend: StreamingBackend) -> None:
        """Register a streaming backend.

        Backends are sorted by priority (lower = higher priority).

        Args:
            backend: StreamingBackend instance.
        """
        self._backends.append(backend)
        self._backends.sort(key=lambda b: b.priority)
        logger.info(
            "Streaming backend registered: %s (priority=%d)",
            backend.name,
            backend.priority,
        )

    def remove_backend(self, name: str) -> bool:
        """Remove a backend by name.

        Args:
            name: Backend identifier.

        Returns:
            True if found and removed, False otherwise.
        """
        for i, b in enumerate(self._backends):
            if b.name == name:
                self._backends.pop(i)
                return True
        return False

    @property
    def backends(self) -> list[str]:
        """List of registered backend names (in priority order)."""
        return [b.name for b in self._backends]

    # ── Core Routing ──────────────────────────────────────────────────

    def subscribe(
        self,
        key: str,
        exchange: str = "NSE",
        callback: Callable[[Any], None] | None = None,
    ) -> None:
        """Subscribe to an instrument stream via the best available backend.

        Tries backends in priority order. If the primary (e.g., WebSocket)
        is unavailable, falls back to the next available backend.

        Stores the callback for dispatch via ``dispatch_tick()``. Multiple
        callbacks per key are supported.

        Args:
            key: Composite key ``{exchange}:{symbol}``.
            exchange: Exchange code.
            callback: Optional callback for tick data.

        Raises:
            RuntimeError: If no backend is available to handle the subscription.
        """
        backend = self._select_backend()
        if backend is None:
            raise RuntimeError(f"No streaming backend available for subscribe({key})")
        try:
            backend.adapter.subscribe(key, exchange)
            self._active_subscriptions.add(key)
            # Store callback for dispatch
            if callback is not None:
                if key not in self._callbacks:
                    self._callbacks[key] = []
                if callback not in self._callbacks[key]:
                    self._callbacks[key].append(callback)
            logger.debug(
                "StreamingRouter: subscribed via %s for %s",
                backend.name,
                key,
            )
        except Exception as exc:
            logger.warning(
                "StreamingRouter: backend %s failed subscribe(%s): %s",
                backend.name,
                key,
                exc,
            )
            # Try fallback backend
            fallback = self._select_fallback(backend.name)
            if fallback is not None:
                fallback.adapter.subscribe(key, exchange)
                self._active_subscriptions.add(key)
                # Store callback for dispatch
                if callback is not None:
                    if key not in self._callbacks:
                        self._callbacks[key] = []
                    if callback not in self._callbacks[key]:
                        self._callbacks[key].append(callback)
                logger.debug(
                    "StreamingRouter: subscribed via fallback %s for %s",
                    fallback.name,
                    key,
                )
            else:
                raise

    def unsubscribe(
        self,
        key: str,
        exchange: str = "NSE",
        callback: Callable[[Any], None] | None = None,
    ) -> None:
        """Unsubscribe from an instrument stream.

        Tries all backends to ensure cleanup. Removes the specific
        callback if provided; if no callbacks remain, cleans up the key.

        Args:
            key: Composite key ``{exchange}:{symbol}``.
            exchange: Exchange code.
            callback: If provided, removes this specific callback.
        """
        self._active_subscriptions.discard(key)
        # Remove callback if provided
        if callback is not None and key in self._callbacks:
            if callback in self._callbacks[key]:
                self._callbacks[key].remove(callback)
            if not self._callbacks[key]:
                del self._callbacks[key]
        for backend in self._backends:
            try:
                if hasattr(backend.adapter, "unsubscribe"):
                    backend.adapter.unsubscribe(key, exchange)
            except Exception as exc:
                logger.debug(
                    "StreamingRouter: backend %s unsubscribe(%s) warning: %s",
                    backend.name,
                    key,
                    exc,
                )

    # ── Query Methods ─────────────────────────────────────────────────

    @property
    def active_subscriptions(self) -> list[str]:
        """List of currently active subscription keys."""
        return list(self._active_subscriptions)

    def active_count(self) -> int:
        """Number of active subscriptions."""
        return len(self._active_subscriptions)

    def is_subscribed(self, key: str, exchange: str = "") -> bool:
        """Check if a key has an active subscription.

        Implements :meth:`SubscriptionPort.is_subscribed`.

        Args:
            key: Composite key.
            exchange: Exchange code (unused, for interface compliance).

        Returns:
            True if subscribed through any backend.
        """
        return key in self._active_subscriptions

    # ── Callback Dispatch ─────────────────────────────────────────────

    def dispatch_tick(self, key: str, data: Any) -> None:
        """Dispatch tick data to all registered callbacks for a key.

        Args:
            key: Composite key ``{exchange}:{symbol}``.
            data: Tick data to dispatch to callbacks.
        """
        callbacks = list(self._callbacks.get(key, []))
        for cb in callbacks:
            try:
                cb(data)
            except Exception as exc:
                logger.warning(
                    "StreamingRouter: callback error for %s: %s",
                    key,
                    exc,
                )

    # ── Lifecycle ─────────────────────────────────────────────────────

    def disconnect_all(self) -> None:
        """Disconnect all backends and clear active subscriptions."""
        for backend in self._backends:
            try:
                disconnect = getattr(backend.adapter, "disconnect", None)
                if disconnect is not None:
                    disconnect()
                stop = getattr(backend.adapter, "stop", None)
                if stop is not None:
                    stop()
            except Exception as exc:
                logger.debug(
                    "StreamingRouter: disconnect %s warning: %s",
                    backend.name,
                    exc,
                )
        self._active_subscriptions.clear()
        self._callbacks.clear()

    def clear(self) -> None:
        """Clear all subscriptions (for testing / cleanup)."""
        self.disconnect_all()
        self._backends.clear()

    # ── Private Helpers ───────────────────────────────────────────────

    def _select_backend(self) -> StreamingBackend | None:
        """Select the best available backend.

        Returns:
            The highest-priority available backend, or None if none available.
        """
        for backend in self._backends:
            if backend.is_available:
                return backend
        return None

    def _select_fallback(self, exclude_name: str) -> StreamingBackend | None:
        """Select a fallback backend, excluding a specific name.

        Args:
            exclude_name: Backend name to exclude (the failed primary).

        Returns:
            The next available backend, or None if none available.
        """
        for backend in self._backends:
            if backend.name != exclude_name and backend.is_available:
                return backend
        return None
