"""WebSocket connection pool — global singleton for managing shared WebSocket connections.

Provides:
- Global connection pooling to prevent duplicate connections
- Reference counting for connection lifecycle management
- Thread-safe operations for concurrent access
- Connection state tracking and monitoring
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Optional

import websocket

from brokers.domain.exceptions import BrokerDegradedError
from brokers.infrastructure.reconnect_strategy import ReconnectStrategy

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
        """Main connection loop with automatic reconnection."""
        strategy = ReconnectStrategy(
            base_delay=self.reconnect_delay,
            max_delay=self.max_reconnect_delay,
            max_retries=10,
        )
        while self._running:
            try:
                self._connect()
                strategy.reset()
            except Exception as exc:
                logger.warning(
                    "websocket_connection_error",
                    extra={"url": self.ws_url, "error": str(exc)},
                )
                if self._running:
                    while strategy.should_retry():
                        if not self._running:
                            return
                        strategy.wait()
                    return

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


class WebSocketConnectionPool:
    """Global WebSocket connection pool. Ensures single connection per unique configuration."""

    _instances: dict[str, WebSocketConnection] = {}
    _lock = threading.Lock()

    @classmethod
    def _make_key(cls, ws_url: str, headers: dict[str, str], on_message_type: str) -> str:
        """Create unique key for connection pooling."""
        # Sort headers for consistent key generation
        sorted_headers = json.dumps(headers, sort_keys=True)
        key_string = f"{ws_url}|{sorted_headers}|{on_message_type}"
        return hashlib.md5(key_string.encode()).hexdigest()

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
        """Get or create a pooled WebSocket connection."""
        # Use a simple type identifier for different message handlers
        on_message_type = (
            on_message.__name__ if hasattr(on_message, "__name__") else str(on_message)
        )
        key = cls._make_key(ws_url, headers, on_message_type)

        with cls._lock:
            logger.debug(
                "websocket_pool_get_connection",
                extra={"url": ws_url, "key": key, "existing": key in cls._instances},
            )
            if key not in cls._instances:
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

                cls._instances[key] = connection
                logger.info(
                    "websocket_pool_created_connection",
                    extra={"url": ws_url, "key": key, "pool_size": len(cls._instances)},
                )
                logger.debug(
                    "websocket_pool_instances_after_creation",
                    extra={"keys": list(cls._instances.keys())},
                )
            else:
                connection = cls._instances[key]
                logger.debug(
                    "websocket_pool_reused_connection",
                    extra={"url": ws_url, "key": key, "pool_size": len(cls._instances)},
                )

            # Increment reference count
            connection.add_reference()

            # Start connection if not running
            if not connection._running:
                connection.start()

            return connection

    @classmethod
    def release_connection(cls, connection: WebSocketConnection) -> None:
        """Release a connection reference. Cleans up if unused."""
        with cls._lock:
            connection.release_reference()

            # Find the key for this connection
            key_to_remove = None
            for key, conn in cls._instances.items():
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
                # del cls._instances[key_to_remove]
                pass  # Keep in pool for potential reuse

    @classmethod
    def get_pool_stats(cls) -> dict[str, Any]:
        """Get current pool statistics."""
        with cls._lock:
            return {
                "active_connections": len(cls._instances),
                "connection_details": [
                    {
                        "url": conn.ws_url,
                        "state": conn.connection_state,
                        "ref_count": conn.reference_count,
                        "subscriptions": conn.subscription_count,
                    }
                    for conn in cls._instances.values()
                ],
            }

    @classmethod
    def cleanup(cls) -> None:
        """Clean up all connections in the pool."""
        with cls._lock:
            for key, connection in list(cls._instances.items()):
                try:
                    connection.stop()
                except Exception as e:
                    logger.warning(
                        "websocket_pool_cleanup_error",
                        extra={"key": key, "error": str(e)},
                    )
            cls._instances.clear()

        # NOTE: Cannot use logger in atexit context — logging may already be shut down.
        # Use sys.stderr directly as the safest fallback.
        import sys

        try:
            sys.stderr.write("websocket_pool_cleaned_up\n")
        except (ValueError, RuntimeError, AttributeError):
            pass


# Global cleanup on process exit
atexit.register(WebSocketConnectionPool.cleanup)
