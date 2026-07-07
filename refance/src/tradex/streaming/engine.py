"""WebSocket stream engine — lifecycle management, reconnect, heartbeat."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable, Coroutine, Optional

from tradex.core.config import StreamConfig
from tradex.core.errors import StreamError
from tradex.core.logging_config import get_logger

logger = get_logger("streaming.engine")


MessageHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
ConnectHandler = Callable[[], Coroutine[Any, Any, None]]
DisconnectHandler = Callable[[str], Coroutine[Any, Any, None]]


class StreamEngine:
    """Generic WebSocket stream engine.

    Handles:
    - Connection lifecycle
    - Auto-reconnect with exponential backoff
    - Heartbeat / ping-pong
    - Message dispatch to handlers
    - Backpressure via bounded buffer
    """

    def __init__(self, config: StreamConfig) -> None:
        self._config = config
        self._ws: Any = None
        self._connected = False
        self._running = False
        self._reconnect_count = 0
        self._last_heartbeat = 0.0
        self._message_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=config.message_buffer_size
        )
        self._on_message: Optional[MessageHandler] = None
        self._on_connect: Optional[ConnectHandler] = None
        self._on_disconnect: Optional[DisconnectHandler] = None
        self._tasks: list[asyncio.Task[None]] = []
        self._lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def on_message(self, handler: MessageHandler) -> None:
        self._on_message = handler

    def on_connect(self, handler: ConnectHandler) -> None:
        self._on_connect = handler

    def on_disconnect(self, handler: DisconnectHandler) -> None:
        self._on_disconnect = handler

    async def connect(self, create_ws: Callable[..., Coroutine[Any, Any, Any]]) -> None:
        """Connect to the WebSocket using the provided factory.

        Args:
            create_ws: Async callable that returns a WebSocket connection.
        """
        self._running = True
        self._reconnect_count = 0
        self._create_ws = create_ws
        await self._do_connect()

    async def _do_connect(self) -> None:
        """Perform the actual connection."""
        try:
            self._ws = await self._create_ws()
            self._connected = True
            self._last_heartbeat = time.time()
            logger.info("stream_connected", url=self._config.url)

            if self._on_connect:
                await self._on_connect()

            # Start background tasks
            self._tasks = [
                asyncio.create_task(self._receive_loop()),
                asyncio.create_task(self._heartbeat_loop()),
            ]

        except Exception as e:
            self._connected = False
            logger.error("stream_connect_failed", error=str(e))
            if self._config.reconnect:
                await self._schedule_reconnect()
            else:
                raise StreamError(f"Connection failed: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect cleanly."""
        self._running = False
        self._connected = False

        for task in self._tasks:
            task.cancel()

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        logger.info("stream_disconnected")

    async def send(self, data: dict[str, Any]) -> None:
        """Send a message through the WebSocket."""
        if not self._connected or not self._ws:
            raise StreamError("Not connected")

        async with self._send_lock:
            try:
                await self._ws.send(json.dumps(data))
            except Exception as e:
                self._connected = False
                raise StreamError(f"Send failed: {e}") from e

    async def _receive_loop(self) -> None:
        """Main receive loop."""
        try:
            while self._connected and self._ws:
                message = await self._ws.recv()
                self._last_heartbeat = time.time()

                if isinstance(message, str):
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        logger.warning("stream_decode_error", message=message[:100])
                        continue

                    # Put in queue for backpressure handling
                    try:
                        self._message_queue.put_nowait(data)
                    except asyncio.QueueFull:
                        logger.warning("stream_buffer_full")

                    # Dispatch to handler
                    if self._on_message:
                        try:
                            await self._on_message(data)
                        except Exception as e:
                            logger.error("stream_handler_error", error=str(e))

        except asyncio.CancelledError:
            # Task cancelled (e.g. during disconnect) — don't change state
            pass
        except Exception as e:
            logger.error("stream_receive_error", error=str(e))
            self._connected = False
            if self._config.reconnect and self._running:
                await self._schedule_reconnect()

    async def _heartbeat_loop(self) -> None:
        """Send periodic pings to keep connection alive."""
        try:
            while self._connected and self._ws:
                await asyncio.sleep(self._config.ping_interval)
                if self._ws:
                    try:
                        await self._ws.ping()
                    except Exception:
                        self._connected = False
                        break
        except asyncio.CancelledError:
            pass

    async def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt."""
        if self._reconnect_count >= self._config.max_reconnect_attempts:
            logger.error("stream_reconnect_exhausted", attempts=self._reconnect_count)
            if self._on_disconnect:
                await self._on_disconnect("Max reconnect attempts reached")
            return

        delay = min(
            self._config.reconnect_delay * (2**self._reconnect_count),
            self._config.max_reconnect_delay,
        )
        self._reconnect_count += 1
        logger.info("stream_reconnecting", delay=delay, attempt=self._reconnect_count)

        await asyncio.sleep(delay)
        if self._running:
            await self._do_connect()

    async def get_messages(self, timeout: float = 1.0) -> Optional[dict[str, Any]]:
        """Get next message from buffer with timeout."""
        try:
            return await asyncio.wait_for(self._message_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
