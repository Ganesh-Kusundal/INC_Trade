"""WebSocket connection pool — instance-scoped factory + DI-friendly lifecycle.

The previous design stored a class-level ``_instances`` dict on
:class:`WebSocketConnectionPool` and registered :func:`atexit` cleanup on
the class itself. That created hidden coupling and global mutable state
shared across the whole process — making it impossible to spin up an
isolated pool for tests, multi-tenant scenarios, or DI containers.

The refactored design follows three principles:

* **All state is instance-level** on :class:`WebSocketPoolFactory`.
* A default factory is exposed via :class:`WebSocketPoolScope` for
  backward compatibility with the existing module-level call sites.
* :func:`atexit` cleanup is registered on the **default factory**, not
  on a class — so the safety net is preserved without making the global
  state a class invariant.

Existing public method signatures (``WebSocketConnectionPool.get_connection``,
``release_connection``, ``get_pool_stats``, ``cleanup``) are preserved as
thin class-method shims that delegate to the default factory.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import threading
from collections.abc import Callable
from typing import Any

import websocket

from inc_trade.infrastructure.reconnect_strategy import ReconnectStrategy, run_reconnect_loop

logger = logging.getLogger(__name__)


class WebSocketConnection:
    """Managed WebSocket connection with state tracking and automatic reconnection."""

    def __init__(
        self,
        ws_url: str,
        headers: dict[str, str],
        on_message: Callable[[str], None],
        on_open: Callable[[], None] | None = None,
        on_close: Callable[[int, str], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
    ):
        self.ws_url = ws_url
        self.headers = headers
        self.on_message = on_message
        self.on_open = on_open
        self.on_close = on_close
        self.on_error = on_error
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay

        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.RLock()
        self._connection_state = "disconnected"  # disconnected, connecting, connected
        self._subscriptions: set[str] = set()
        self._pending_subscriptions: set[str] = set()
        self._ref_count = 0

    @property
    def is_connected(self) -> bool:
        """Check if connection is currently active."""
        with self._lock:
            return self._connection_state == "connected" and self._ws is not None

    @property
    def connection_state(self) -> str:
        """Get current connection state."""
        with self._lock:
            return self._connection_state

    @property
    def subscription_count(self) -> int:
        """Get number of active subscriptions."""
        with self._lock:
            return len(self._subscriptions)

    @property
    def reference_count(self) -> int:
        """Get current reference count."""
        with self._lock:
            return self._ref_count

    def add_reference(self) -> None:
        """Increment reference count."""
        with self._lock:
            self._ref_count += 1
            logger.debug(
                "websocket_ref_count_increased",
                extra={"url": self.ws_url, "ref_count": self._ref_count},
            )

    def release_reference(self) -> None:
        """Decrement reference count and cleanup if unused."""
        with self._lock:
            self._ref_count -= 1
            logger.debug(
                "websocket_ref_count_decreased",
                extra={"url": self.ws_url, "ref_count": self._ref_count},
            )

            if self._ref_count <= 0:
                self._running = False
                if self._ws:
                    try:
                        self._ws.close()
                    except Exception as e:
                        logger.warning(
                            "websocket_cleanup_error",
                            extra={"url": self.ws_url, "error": str(e)},
                        )
                self._ws = None
                self._connection_state = "disconnected"

    def subscribe(self, key: str) -> None:
        """Subscribe to a symbol. Queues if disconnected, sends immediately if connected."""
        with self._lock:
            if key not in self._subscriptions:
                self._subscriptions.add(key)
                logger.debug(
                    "websocket_subscription_added",
                    extra={"url": self.ws_url, "key": key},
                )

            # If connected, send immediately
            if self.is_connected:
                self._send_subscribe([key])
            else:
                # Queue for when connection establishes
                self._pending_subscriptions.add(key)

    def unsubscribe(self, key: str) -> None:
        """Unsubscribe from a symbol."""
        with self._lock:
            if key in self._subscriptions:
                self._subscriptions.discard(key)
                logger.debug(
                    "websocket_subscription_removed",
                    extra={"url": self.ws_url, "key": key},
                )

            if key in self._pending_subscriptions:
                self._pending_subscriptions.discard(key)

            # Send unsubscribe if connected
            if self.is_connected:
                self._send_unsubscribe([key])

    def start(self) -> None:
        """Start the WebSocket connection."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._connection_state = "connecting"

            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run_connection,
                    name=f"ws-pool-{hashlib.md5(self.ws_url.encode()).hexdigest()[:8]}",
                    daemon=True,
                )
                self._thread.start()

    def stop(self) -> None:
        """Stop the WebSocket connection."""
        with self._lock:
            self._running = False
            if self._ws:
                try:
                    self._ws.close()
                except Exception:
                    pass
            self._ws = None
            self._connection_state = "disconnected"

    def _run_connection(self) -> None:
        """Main connection loop with automatic reconnection.

        Preserves legacy behaviour: clean disconnect retries immediately
        without backoff; only exception-driven failures use the
        ``ReconnectStrategy`` schedule.
        """
        strategy = ReconnectStrategy(
            base_delay=self.reconnect_delay,
            max_delay=self.max_reconnect_delay,
            max_retries=10,
        )

        def _on_reconnecting(delay: float) -> None:
            logger.warning(
                "websocket_connection_error",
                extra={"url": self.ws_url, "next_delay": delay},
            )

        run_reconnect_loop(
            connect=self._connect,
            strategy=strategy,
            is_running=lambda: self._running,
            on_reconnecting=_on_reconnecting,
            wait_on_success=False,
        )

    def _connect(self) -> None:
        """Establish WebSocket connection."""
        with self._lock:
            self._ws = websocket.WebSocketApp(
                self.ws_url,
                header=self.headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self._connection_state = "connecting"

        try:
            self._ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception:
            with self._lock:
                self._connection_state = "disconnected"
                self._ws = None
            raise

    def _on_open(self, ws: object) -> None:
        """Handle connection open event."""
        with self._lock:
            self._connection_state = "connected"
            logger.info(
                "websocket_connected",
                extra={"url": self.ws_url},
            )

            # Send pending subscriptions
            if self._pending_subscriptions:
                self._send_subscribe(list(self._pending_subscriptions))
                self._pending_subscriptions.clear()

        if self.on_open:
            self.on_open()

    def _on_message(self, ws: object, message: str) -> None:
        """Handle incoming messages."""
        try:
            self.on_message(message)
        except Exception as exc:
            logger.error(
                "websocket_message_handler_error",
                extra={"url": self.ws_url, "error": str(exc)},
            )

    def _on_error(self, ws: object, error: Exception) -> None:
        """Handle WebSocket errors."""
        with self._lock:
            self._connection_state = "disconnected"

        if self.on_error:
            self.on_error(error)
        else:
            logger.warning(
                "websocket_error",
                extra={"url": self.ws_url, "error": str(error)},
            )

    def _on_close(self, ws: object, close_status_code: int, close_msg: str) -> None:
        """Handle connection close event."""
        with self._lock:
            self._connection_state = "disconnected"
            self._ws = None

        logger.info(
            "websocket_disconnected",
            extra={
                "url": self.ws_url,
                "status_code": close_status_code,
                "message": close_msg,
            },
        )

        if self.on_close:
            self.on_close(close_status_code, close_msg)

    def _send_subscribe(self, keys: list[str]) -> None:
        """Send subscribe message. Base class does nothing, subclasses should override."""
        pass

    def _send_unsubscribe(self, keys: list[str]) -> None:
        """Send unsubscribe message. Base class does nothing, subclasses should override."""
        pass


class WebSocketPoolFactory:
    """Instance-scoped factory that owns a set of pooled WebSocket connections.

    Each factory owns its own ``_instances`` dict and lock, so multiple
    factories can coexist for tests, multi-tenant setups, or DI
    containers. The :class:`WebSocketPoolScope` exposes a default factory
    for backward-compatible module-level usage.
    """

    def __init__(self) -> None:
        self._instances: dict[str, WebSocketConnection] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _make_key(ws_url: str, headers: dict[str, str], on_message_type: str) -> str:
        """Create unique key for connection pooling."""
        # Sort headers for consistent key generation
        sorted_headers = json.dumps(headers, sort_keys=True)
        key_string = f"{ws_url}|{sorted_headers}|{on_message_type}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def get_connection(
        self,
        ws_url: str,
        headers: dict[str, str],
        on_message: Callable[[str], None],
        on_open: Callable[[], None] | None = None,
        on_close: Callable[[int, str], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        connection_factory: Callable[..., WebSocketConnection] | None = None,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
    ) -> WebSocketConnection:
        """Get or create a pooled WebSocket connection."""
        # Use a simple type identifier for different message handlers
        on_message_type = (
            on_message.__name__ if hasattr(on_message, "__name__") else str(on_message)
        )
        key = self._make_key(ws_url, headers, on_message_type)

        with self._lock:
            logger.debug(
                "websocket_pool_get_connection",
                extra={"url": ws_url, "key": key, "existing": key in self._instances},
            )
            if key not in self._instances:
                if connection_factory:
                    connection = connection_factory(
                        ws_url,
                        headers,
                        on_message,
                        on_open,
                        on_close,
                        on_error,
                        reconnect_delay,
                        max_reconnect_delay,
                    )
                else:
                    # Default factory - create basic connection
                    connection = WebSocketConnection(
                        ws_url,
                        headers,
                        on_message,
                        on_open,
                        on_close,
                        on_error,
                        reconnect_delay,
                        max_reconnect_delay,
                    )

                self._instances[key] = connection
                logger.info(
                    "websocket_pool_created_connection",
                    extra={"url": ws_url, "key": key, "pool_size": len(self._instances)},
                )
                logger.debug(
                    "websocket_pool_instances_after_creation",
                    extra={"keys": list(self._instances.keys())},
                )
            else:
                connection = self._instances[key]
                logger.debug(
                    "websocket_pool_reused_connection",
                    extra={"url": ws_url, "key": key, "pool_size": len(self._instances)},
                )

            # Increment reference count
            connection.add_reference()

            # Start connection if not running
            if not connection._running:
                connection.start()

            return connection

    def release_connection(self, connection: WebSocketConnection) -> None:
        """Release a connection reference. Cleans up if unused."""
        with self._lock:
            connection.release_reference()

            # Find the key for this connection
            key_to_remove = None
            for key, conn in self._instances.items():
                if conn is connection:
                    key_to_remove = key
                    break

            # Clean up if no references and not running
            # Keep disconnected connections in pool for reuse
            if (
                key_to_remove is not None
                and connection.reference_count <= 0
                and not connection._running
                and connection._connection_state == "disconnected"
            ):
                # Only remove if we have too many disconnected connections
                # For now, keep all disconnected connections for reuse
                # del self._instances[key_to_remove]
                pass  # Keep in pool for potential reuse

    def get_pool_stats(self) -> dict[str, Any]:
        """Get current pool statistics."""
        with self._lock:
            return {
                "active_connections": len(self._instances),
                "connection_details": [
                    {
                        "url": conn.ws_url,
                        "state": conn.connection_state,
                        "ref_count": conn.reference_count,
                        "subscriptions": conn.subscription_count,
                    }
                    for conn in self._instances.values()
                ],
            }

    def close_all(self) -> None:
        """Stop every connection owned by this factory and clear the pool.

        This is the explicit lifecycle hook that consumers call. It is
        safe to call multiple times — subsequent calls are no-ops.
        """
        with self._lock:
            for key, connection in list(self._instances.items()):
                try:
                    connection.stop()
                except Exception as e:
                    logger.warning(
                        "websocket_pool_cleanup_error",
                        extra={"key": key, "error": str(e)},
                    )
            self._instances.clear()

    # Backward-compat alias — preserve the historical method name.
    cleanup = close_all


class WebSocketPoolScope:
    """Module-level scope that exposes a default :class:`WebSocketPoolFactory`.

    This is the only remaining class-level mutable state in the module,
    and it is intentionally minimal: a single ``Optional[WebSocketPoolFactory]``
    plus the lock that guards its lazy initialisation. Tests can call
    :meth:`reset` to obtain a fresh default factory.

    The atexit safety net for the default factory is registered by
    :func:`_register_default_cleanup`, which runs at import time.
    """

    _default_factory: WebSocketPoolFactory | None = None
    _lock = threading.Lock()

    @classmethod
    def get_default(cls) -> WebSocketPoolFactory:
        """Return the default factory, creating it on first access."""
        if cls._default_factory is None:
            with cls._lock:
                if cls._default_factory is None:
                    cls._default_factory = WebSocketPoolFactory()
        return cls._default_factory

    @classmethod
    def set_default(cls, factory: WebSocketPoolFactory | None) -> None:
        """Replace the default factory.

        Pass ``None`` to clear the default. Use this in tests to obtain
        a clean scope between runs; production code should not call it.
        """
        with cls._lock:
            cls._default_factory = factory

    @classmethod
    def reset(cls) -> WebSocketPoolFactory:
        """Reset the default factory to a fresh instance and return it."""
        with cls._lock:
            cls._default_factory = WebSocketPoolFactory()
            return cls._default_factory


class WebSocketConnectionPool:
    """Backward-compatible class-method facade over :class:`WebSocketPoolFactory`.

    All class methods delegate to the default factory exposed by
    :class:`WebSocketPoolScope`. New code should depend on a
    :class:`WebSocketPoolFactory` instance directly for full DI control.
    """

    @classmethod
    def _make_key(cls, ws_url: str, headers: dict[str, str], on_message_type: str) -> str:
        """Create unique key for connection pooling (kept for backward compat)."""
        return WebSocketPoolFactory._make_key(ws_url, headers, on_message_type)

    @classmethod
    def get_connection(
        cls,
        ws_url: str,
        headers: dict[str, str],
        on_message: Callable[[str], None],
        on_open: Callable[[], None] | None = None,
        on_close: Callable[[int, str], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        connection_factory: Callable[..., WebSocketConnection] | None = None,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
    ) -> WebSocketConnection:
        """Get or create a pooled WebSocket connection (delegates to default factory)."""
        return WebSocketPoolScope.get_default().get_connection(
            ws_url,
            headers,
            on_message,
            on_open,
            on_close,
            on_error,
            connection_factory,
            reconnect_delay,
            max_reconnect_delay,
        )

    @classmethod
    def release_connection(cls, connection: WebSocketConnection) -> None:
        """Release a connection reference. Cleans up if unused."""
        WebSocketPoolScope.get_default().release_connection(connection)

    @classmethod
    def get_pool_stats(cls) -> dict[str, Any]:
        """Get current pool statistics."""
        return WebSocketPoolScope.get_default().get_pool_stats()

    @classmethod
    def cleanup(cls) -> None:
        """Clean up all connections owned by the default factory."""
        WebSocketPoolScope.get_default().close_all()


# ── Process-exit safety net ────────────────────────────────────────────────
# atexit registers a single handler on the *default factory*, not on the
# WebSocketConnectionPool class. This is the only remaining global
# behaviour, and it is the same safety net the old design provided: if a
# process exits while a default-scope pool is still live, every owned
# connection is stopped cleanly.
#
# We import ``sys`` inside the handler because logging may already be
# shut down by the time atexit runs.


def _register_default_cleanup() -> None:
    """Register a single atexit hook for the default factory's pool."""
    default_factory = WebSocketPoolScope.get_default()
    atexit.register(_atexit_close_all, default_factory)


def _atexit_close_all(factory: WebSocketPoolFactory) -> None:
    """atexit handler — close every connection owned by *factory*."""
    import sys

    try:
        factory.close_all()
    except Exception:
        pass
    try:
        sys.stderr.write("websocket_pool_cleaned_up\n")
    except (ValueError, RuntimeError, AttributeError):
        pass


_register_default_cleanup()
