"""Upstox V3 market data WebSocket multiplexer.

Mirrors Trade_J ``UpstoxWebSocketMultiplexer``. Provides ``subscribe``,
``change_mode``, ``unsubscribe`` and dispatches parsed ticks to listeners.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
from collections.abc import Callable
from typing import Any

from brokers.upstox.auth.config import (
    UPSTOX_WS_PING_INTERVAL_SECONDS,
    UPSTOX_WS_PING_TIMEOUT_SECONDS,
)
from brokers.upstox.websocket.feed_authorizer import (
    UpstoxFeedAuthorizer,
    build_subscribe_payload,
    encode_subscribe_payload,
)
from brokers.upstox.websocket.v3_auto_reconnect import UpstoxAutoReconnect
from brokers.upstox.websocket.v3_decoder import UpstoxV3Decoder
from brokers.upstox.websocket.v3_subscription_manager import (
    UpstoxV3SubscriptionLimits,
    UpstoxV3SubscriptionManager,
)
from infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)

# NSE market hours in UTC: 03:45-10:00 (09:15-15:30 IST), weekdays only.
_MARKET_OPEN_UTC_HOUR = 3
_MARKET_OPEN_UTC_MIN = 45
_MARKET_CLOSE_UTC_HOUR = 10
_MARKET_CLOSE_UTC_MIN = 0


def _overlaps_market_hours(start: Any, end: Any) -> bool:
    """Return True if [start, end] overlaps NSE market hours on a weekday."""
    from datetime import time as dt_time

    if start.weekday() >= 5 and end.weekday() >= 5:
        return False
    market_open = dt_time(_MARKET_OPEN_UTC_HOUR, _MARKET_OPEN_UTC_MIN)
    market_close = dt_time(_MARKET_CLOSE_UTC_HOUR, _MARKET_CLOSE_UTC_MIN)
    for dt in (start, end):
        t = dt.time()
        if market_open <= t <= market_close and dt.weekday() < 5:
            return True
    # Also detect ranges that span across market hours (start before, end after)
    return (
        start < end
        and start.weekday() < 5
        and start.time() <= market_open
        and end.time() >= market_close
    )


TickListener = Callable[[str, dict[str, Any]], None]


class UpstoxMarketDataV3Multiplexer:
    """Subscribe to Upstox V3 WebSocket feed and dispatch parsed ticks.

    In production this opens a real ``websockets`` connection to the
    authorized URI. In tests the connection can be replaced via the
    ``socket_factory`` constructor argument.

    Supports reconnect backfill: on reconnection, if a ``backfill_callback``
    was provided, it is invoked to fetch missed bars between the last tick
    time and the reconnection time.
    """

    def __init__(
        self,
        authorizer: UpstoxFeedAuthorizer,
        decoder: UpstoxV3Decoder | None = None,
        limits: UpstoxV3SubscriptionLimits | None = None,
        auto_reconnect: UpstoxAutoReconnect | None = None,
        socket_factory: Callable[[str], Any] | None = None,
        event_bus: EventBus | None = None,
        backfill_callback: Callable[[str, Any, Any], list[dict]] | None = None,
    ) -> None:
        self._authorizer = authorizer
        self._decoder = decoder or UpstoxV3Decoder()
        self._subscriptions = UpstoxV3SubscriptionManager(limits)
        self._reconnect = auto_reconnect or UpstoxAutoReconnect()
        self._socket_factory = socket_factory or _default_socket_factory
        self._event_bus = event_bus
        self._backfill_callback = backfill_callback
        self._socket: Any = None
        self._listeners: list[TickListener] = []
        self._listener_lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._subscribed: set[str] = set()
        self._task: asyncio.Task[Any] | None = None
        self._stopped = False
        self._connected = False
        # Reconnect backfill state
        self._last_tick_time: dict[str, Any] = {}
        self._disconnect_time: Any = None
        self._just_reconnected = False

    @property
    def subscription_manager(self) -> UpstoxV3SubscriptionManager:
        return self._subscriptions

    @property
    def is_connected(self) -> bool:
        return self._connected and not self._stopped

    def add_listener(self, listener: TickListener) -> None:
        with self._listener_lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: TickListener) -> None:
        with self._listener_lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def subscribe(
        self,
        instrument_keys: list[str],
        mode: str = "ltpc",
        *,
        guid: str | None = None,
    ) -> None:
        self._subscriptions.subscribe(instrument_keys, mode)
        if self._socket is not None:
            self._send_subscribe(instrument_keys, mode, guid=guid)
        self._subscribed.update(instrument_keys)

    def change_mode(
        self,
        instrument_keys: list[str],
        mode: str,
        *,
        guid: str | None = None,
    ) -> None:
        self._subscriptions.change_mode(instrument_keys, mode)
        if self._socket is not None:
            payload = build_subscribe_payload(instrument_keys, mode, guid=guid)
            self._send_raw("change_mode", payload)

    def unsubscribe(self, instrument_keys: list[str]) -> None:
        self._subscriptions.unsubscribe(instrument_keys)
        if self._socket is not None:
            payload = {
                "guid": "",
                "method": "unsub",
                "data": {"instrumentKeys": list(instrument_keys)},
            }
            self._send_raw("unsub", payload)
        for k in instrument_keys:
            self._subscribed.discard(k)
            self._last_tick_time.pop(k, None)

    def feed_authorize_url(self) -> str:
        return self._authorizer.authorize_market_data_v3()

    async def connect(self) -> None:
        """Open the WebSocket connection and start the read loop."""
        url = self._authorizer.authorize_market_data_v3()
        if not url:
            raise RuntimeError("Upstox V3 feed authorize did not return a URL")
        self._socket = await self._open_socket(url)
        await self._maybe_send_initial_subscriptions()
        self._stopped = False
        self._connected = True
        with contextlib.suppress(Exception):
            from brokers.upstox.metrics import upstox_ws_connected

            upstox_ws_connected.set(1)
        self._task = asyncio.create_task(self._read_loop())

    async def _open_socket(self, url: str) -> Any:
        socket_or_awaitable = self._socket_factory(url)
        import inspect
        if inspect.isawaitable(socket_or_awaitable):
            return await socket_or_awaitable
        return socket_or_awaitable

    async def _reconnect_socket(self) -> bool:
        """Re-authorize, open a new socket, and replay subscriptions."""
        try:
            if self._socket is not None:
                close = getattr(self._socket, "close", None)
                if close is not None:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
                self._socket = None
            url = self._authorizer.authorize_market_data_v3()
            if not url:
                return False
            self._socket = await self._open_socket(url)
            await self._maybe_send_initial_subscriptions()
            self._connected = True
            with contextlib.suppress(Exception):
                from brokers.upstox.metrics import upstox_ws_connected, upstox_ws_reconnects

                upstox_ws_reconnects.inc()
                upstox_ws_connected.set(1)
            return True
        except Exception as exc:
            logger.warning("Upstox V3 reconnect failed: %s", exc)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        self._stopped = True
        self._connected = False
        from datetime import datetime, timezone

        self._disconnect_time = datetime.now(timezone.utc)
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        if self._socket is not None:
            try:
                close = getattr(self._socket, "close", None)
                if close is not None:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
            except Exception as exc:
                logger.debug("websocket_close_failed: %s", exc)
            self._socket = None
        with contextlib.suppress(Exception):
            from brokers.upstox.metrics import upstox_ws_connected

            upstox_ws_connected.set(0)
        self._reconnect.reset()

    async def _maybe_send_initial_subscriptions(self) -> None:
        if not self._subscribed:
            return
        for mode in ("ltpc", "option_greeks", "full", "full_d30"):
            keys = self._subscriptions.keys_for_mode(mode)
            if keys:
                self._send_subscribe(keys, mode)

    def _send_subscribe(
        self, instrument_keys: list[str], mode: str, *, guid: str | None = None
    ) -> None:
        payload = build_subscribe_payload(instrument_keys, mode, guid=guid)
        self._send_raw("sub", payload)

    def _send_raw(self, method: str, payload: dict[str, Any]) -> None:
        if self._socket is None:
            return
        send = getattr(self._socket, "send", None)
        if send is None:
            return
        
        import asyncio
        data = encode_subscribe_payload(payload)
        
        if asyncio.iscoroutinefunction(send):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(send(data))
            except RuntimeError:
                # No running event loop in this thread, schedule it thread-safe if task loop exists
                if self._task and not self._task.done():
                    loop = self._task.get_loop()
                    asyncio.run_coroutine_threadsafe(send(data), loop)
                else:
                    logger.warning("Upstox V3 send failed: no running event loop found to schedule send")
        else:
            with self._send_lock:
                try:
                    send(data)
                except Exception as exc:
                    logger.warning("Upstox V3 send failed: %s", exc)
                    self._reconnect.record_failure()

    async def _read_loop(self) -> None:
        recv = getattr(self._socket, "recv", None)
        if recv is None:
            return
        was_disconnected = False
        while not self._stopped:
            try:
                raw = await recv() if asyncio.iscoroutinefunction(recv) else recv()
            except Exception as exc:
                logger.warning("Upstox V3 recv error: %s", exc)
                was_disconnected = True
                if self._disconnect_time is None:
                    from datetime import datetime, timezone

                    self._disconnect_time = datetime.now(timezone.utc)
                if not self._reconnect.should_retry():
                    self._connected = False
                    break
                delay = self._reconnect.next_delay()
                self._reconnect.record_failure()
                await asyncio.sleep(delay)
                if await self._reconnect_socket():
                    was_disconnected = True
                continue
            # Successfully received — check if we just reconnected
            if was_disconnected and self._backfill_callback is not None:
                self._just_reconnected = True
            was_disconnected = False
            self._reconnect.reset()
            if not raw:
                continue
            if isinstance(raw, str):
                # First-tick is JSON with market_info
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "market_info":
                    # Trigger backfill after market_info (reconnection confirmed)
                    if self._just_reconnected:
                        self._just_reconnected = False
                        self._backfill_gap()
                    with self._listener_lock:
                        listeners = list(self._listeners)
                    for listener in listeners:
                        with contextlib.suppress(Exception):
                            listener("market_info", msg)
                continue
            try:
                frames = self._decoder.parse(raw)
            except Exception:
                continue
            if not frames:
                continue
            
            # Support both list of frames and a single frame (backward/test compatibility)
            if not isinstance(frames, list):
                frames = [frames]
                
            for frame in frames:
                # Track tick times for backfill
                self._track_tick_from_frame(frame)
                with self._listener_lock:
                    listeners = list(self._listeners)
                for listener in listeners:
                    with contextlib.suppress(Exception):
                        listener("tick", {"frame_type": frame.type, "payload": frame.payload})

    def _track_tick_from_frame(self, frame: Any) -> None:
        """Record latest tick time per instrument for gap detection."""
        from datetime import datetime, timezone

        payload = getattr(frame, "payload", None)
        if payload is None:
            return
        instrument_key = getattr(payload, "instrument_key", None) or (
            payload.get("instrumentKey") if isinstance(payload, dict) else None
        )
        if not instrument_key:
            return
        now = datetime.now(timezone.utc)
        prev = self._last_tick_time.get(instrument_key)
        if prev is None or now > prev:
            self._last_tick_time[instrument_key] = now

    def _backfill_gap(self) -> None:
        """Fetch missed bars from REST and dispatch as ticks."""
        from datetime import datetime, timezone

        disconnect_time = self._disconnect_time
        if disconnect_time is None:
            return
        now = datetime.now(timezone.utc)
        self._disconnect_time = None
        if disconnect_time >= now:
            return
        # Skip backfill if the entire gap falls outside market hours
        # (NSE: 03:45-10:00 UTC / 09:15-15:30 IST, weekdays only).
        if not _overlaps_market_hours(disconnect_time, now):
            logger.debug(
                "backfill_skipped_outside_market_hours",
                extra={"disconnect": disconnect_time.isoformat(), "now": now.isoformat()},
            )
            return
        instrument_keys = list(self._last_tick_time.keys())
        if not instrument_keys:
            instrument_keys = list(self._subscribed)
        if not instrument_keys:
            return
        logger.info(
            "Backfilling %d instruments for gap %s → %s",
            len(instrument_keys),
            disconnect_time.isoformat(),
            now.isoformat(),
        )
        try:
            bars = self._backfill_callback(instrument_keys, disconnect_time, now)
        except Exception as exc:
            logger.warning("Backfill callback failed: %s", exc)
            return
        if not bars:
            return
        for bar in bars:
            with self._listener_lock:
                listeners = list(self._listeners)
            for listener in listeners:
                with contextlib.suppress(Exception):
                    listener("tick", {"frame_type": "backfill", "payload": bar})


def _default_socket_factory(url: str) -> Any:
    """Open a real ``websockets`` connection. Returns an awaitable that
    resolves to the connected WebSocket client."""
    try:
        import websockets  # type: ignore

        return websockets.connect(
            url,
            ping_interval=UPSTOX_WS_PING_INTERVAL_SECONDS,
            ping_timeout=UPSTOX_WS_PING_TIMEOUT_SECONDS,
            max_size=2**20,
        )
    except ImportError as exc:
        raise RuntimeError(
            "websockets library is required for live Upstox V3 WebSocket; "
            "install via `pip install websockets`"
        ) from exc
