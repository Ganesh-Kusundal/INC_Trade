"""Unified binary-packet depth WebSocket feed for Dhan.

Provides shared binary parsing, subscription management, and reconnect logic
for depth-20 and depth-200 feeds. Uses ReconnectingServiceMixin for shared
state tracking and backoff arithmetic.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import struct
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from brokers_core.domain import DepthLevel, MarketDepth
from brokers_core.domain.lifecycle_health import HealthState, HealthStatus
from brokers_core.infrastructure.lifecycle import ManagedService

from brokers_core.adapters.dhan.connection_admission import (
    ConnectionAdmission,
)
from brokers_core.adapters.dhan.reconnecting_service import ReconnectingServiceMixin

logger = logging.getLogger(__name__)

# Binary packet constants
_HEADER_SIZE = 12
_LEVEL_SIZE = 16  # 8 bytes price + 4 bytes quantity + 4 bytes orders


class BinaryDepthFeed(ReconnectingServiceMixin, ManagedService):
    """Unified WebSocket feed for Dhan's binary depth streams.

    Parameters
    ----------
    total_slots:
        Number of depth levels per side (20 for depth-20, 200 for depth-200).
    subs_per_connection:
        Max (segment, security_id) tuples per connection (50 for depth-20, 1 for depth-200).
    endpoint:
        WebSocket endpoint URL.
    request_code:
        Wire format request code (23 for Full Market Depth).
    depth_type:
        "DEPTH_20" or "DEPTH_200".
    name:
        ManagedService identifier.
    event_name:
        EventBus event name.
    header_carries_security_id:
        True for depth-20 (offset 4 = security_id), False for depth-200.
    """

    name: str
    ENDPOINT: str
    REQUEST_CODE: int
    DEPTH_TYPE: str
    EVENT_NAME: str

    def __init__(
        self,
        client_id: str,
        access_token: str,
        endpoint: str,
        request_code: int,
        total_slots: int,
        subs_per_connection: int,
        depth_type: str,
        name: str,
        event_name: str,
        header_carries_security_id: bool,
        event_bus: Any = None,
        admission: Any = None,
    ):
        self._client_id = client_id
        self._access_token = access_token
        self._event_bus = event_bus
        self._admission = admission or ConnectionAdmission(
            client_id, connection_type=f"depth-{depth_type.lower()}"
        )

        self.ENDPOINT = endpoint
        self.REQUEST_CODE = request_code
        self.total_slots = total_slots
        self.subs_per_connection = subs_per_connection
        self.DEPTH_TYPE = depth_type
        self.name = name
        self.EVENT_NAME = event_name
        self.header_carries_security_id = header_carries_security_id

        # Public aliases for backward compatibility
        self.MAX_INSTRUMENTS = subs_per_connection
        self.TOTAL_DEPTH_PACKETS = total_slots

        self._subscriptions: list[tuple[str, str]] = []
        self._instruments: list[tuple[str, str]] = self._subscriptions
        self._depth_callbacks: list[Callable[[MarketDepth], None]] = []
        self._callback_lock = threading.Lock()

        self._ws: Any = None
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Initialize shared reconnect state
        self._init_reconnect_state()

        # Per-security_id depth cache (preserves both sides independently)
        self._depth_cache: dict[int, dict[str, list[DepthLevel]]] = {}
        self._depth_cache_lock = threading.Lock()
        self._sec_id_to_symbol: dict[int, str] = {}

        # Counters for observability
        self._published_depths = 0
        self._dropped_depths = 0

    # ── Subscription management ───────────────────────────────────────────

    @property
    def max_instruments(self) -> int:
        return self.subs_per_connection

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def on_depth(self, callback: Callable[[MarketDepth], None]) -> None:
        with self._callback_lock:
            self._depth_callbacks.append(callback)

    def register_symbol(self, security_id: int, symbol: str) -> None:
        """Map security_id to canonical symbol for event routing."""
        from brokers_core.domain.symbols import normalize_symbol

        self._sec_id_to_symbol[int(security_id)] = normalize_symbol(symbol)

    def subscribe(self, instruments: list[tuple[str, str]] | tuple[str, str]) -> None:
        """Subscribe to one or more instruments."""
        new_instruments = (
            [instruments] if isinstance(instruments, tuple) else list(instruments)
        )
        new_instruments = [i for i in new_instruments if i not in self._subscriptions]
        if not new_instruments:
            return

        total = len(self._subscriptions) + len(new_instruments)
        if total > self.subs_per_connection:
            raise ValueError(
                f"Maximum {self.subs_per_connection} instrument"
                f"{'s' if self.subs_per_connection != 1 else ''} allowed for "
                f"{self.DEPTH_TYPE} depth, would have {total}"
            )

        self._subscriptions.extend(new_instruments)
        logger.info(
            "%s_subscribe",
            self.DEPTH_TYPE.lower(),
            extra={"count": len(new_instruments), "total": len(self._subscriptions)},
        )

        if self._is_connected and self._ws:
            self._send_subscription(new_instruments)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """ManagedService protocol: start the WebSocket connection."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._websocket_loop,
            name=self.name,
            daemon=True,
        )
        self._thread.start()
        logger.info("%s_started", self.DEPTH_TYPE.lower())

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """ManagedService protocol: stop the WebSocket connection."""
        self._stop_event.set()

        with self._lock:
            ws = self._ws
            thread = self._thread

        if ws:
            self._close_active_websocket(ws, loop=getattr(self, "_ws_loop", None))

        if thread and thread.is_alive():
            thread.join(timeout=timeout_seconds)
            if thread.is_alive():
                logger.warning(
                    "%s thread did not stop within %ss",
                    self.name,
                    timeout_seconds,
                )

        admission = getattr(self, "_admission", None)
        if admission is not None:
            with contextlib.suppress(Exception):
                admission.release()

        logger.info("%s_stopped", self.DEPTH_TYPE.lower())

    def health(self) -> HealthStatus:
        """ManagedService protocol: return health snapshot."""
        with self._lock:
            thread_alive = bool(self._thread and self._thread.is_alive())
            is_connected = self._is_connected
            reconnect_count = self._reconnect_count
            last_message_age = (
                (datetime.now(UTC) - self._last_message_at).total_seconds()
                if self._last_message_at is not None
                else None
            )

        if thread_alive and is_connected:
            state = HealthState.HEALTHY
            detail = "running and connected"
        elif thread_alive and not is_connected:
            state = HealthState.DEGRADED
            detail = "thread running but not connected (reconnecting?)"
        else:
            state = HealthState.STOPPED
            detail = "not started"

        return HealthStatus(
            state=state,
            service=self.name,
            last_check=datetime.now(UTC),
            detail=detail,
            metrics={
                "reconnect_count": reconnect_count,
                "subscriptions": len(self._subscriptions),
                "depth_type": self.DEPTH_TYPE,
                "subscribed_instrument_count": len(self._subscriptions),
                "published_depths": self._published_depths,
                "dropped_depths": self._dropped_depths,
                "last_message_age_seconds": last_message_age
                if last_message_age is not None
                else -1,
            },
        )

    # ── WebSocket loop ─────────────────────────────────────────────────────

    def _websocket_loop(self) -> None:
        """Main WebSocket loop with auto-reconnect."""
        while not self._stop_event.is_set():
            try:
                self._connect_and_run()
            except Exception as exc:
                logger.error("%s_error: %s", self.DEPTH_TYPE.lower(), exc)

            if not self._stop_event.is_set():
                self._reconnect_count += 1
                delay = float(min(2 ** min(self._reconnect_count, 5), 30))
                self._backoff_sleep(delay)

    def _connect_and_run(self) -> None:
        """Establish WebSocket and process messages."""
        import importlib.util

        if importlib.util.find_spec("websockets") is None:
            logger.error("websockets package not installed: pip install websockets")
            return

        logger.info(
            "%s_connecting", self.DEPTH_TYPE.lower(), extra={"endpoint": self.ENDPOINT}
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._ws_loop = loop

        try:
            loop.run_until_complete(self._websocket_handler())
        finally:
            loop.close()
            with self._lock:
                self._ws_loop = None
                self._is_connected = False

    async def _websocket_handler(self) -> None:
        """Async WebSocket handler with auto-reconnect."""
        import websockets

        backoff = 1.0
        max_backoff = 30.0

        while not self._stop_event.is_set():
            # 429 cooldown
            cooldown_wait = self._admission.seconds_until_connect_allowed()
            if cooldown_wait > 0:
                logger.info(
                    "%s_connect_cooldown_wait",
                    self.DEPTH_TYPE.lower(),
                    extra={"seconds": round(cooldown_wait, 2)},
                )
                await asyncio.sleep(min(cooldown_wait, 5.0))
                continue

            url = f"{self.ENDPOINT}?token={self._access_token}&clientId={self._client_id}&authType=2"
            try:
                async with websockets.connect(url) as ws:
                    with self._lock:
                        self._ws = ws
                        self._is_connected = True
                        self._reconnect_count = 0

                    logger.info("%s_connected", self.DEPTH_TYPE.lower())
                    self._admission.clear_cooldown()

                    if self._subscriptions:
                        self._send_subscription(self._subscriptions)

                    while not self._stop_event.is_set():
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=30.0)
                            if isinstance(message, bytes):
                                self._process_binary_message(message)
                            backoff = 1.0

                        except TimeoutError:
                            continue

                        except websockets.ConnectionClosed:
                            logger.warning(
                                "%s_connection_closed", self.DEPTH_TYPE.lower()
                            )
                            break

            except Exception as exc:
                err_str = str(exc).lower()
                if "429" in err_str:
                    logger.warning(
                        "%s WebSocket rate limited, backing off",
                        self.DEPTH_TYPE.lower(),
                    )
                    self._admission.record_rate_limit_cooldown()
                else:
                    logger.error(
                        "%s_connection_error: %s", self.DEPTH_TYPE.lower(), exc
                    )
                with self._lock:
                    self._is_connected = False
                    self._ws = None
                    self._reconnect_count += 1

            if not self._stop_event.is_set():
                wait_time = min(backoff, max_backoff)
                logger.info(
                    "%s_reconnecting in %.1fs", self.DEPTH_TYPE.lower(), wait_time
                )
                await asyncio.sleep(wait_time)
                backoff = min(backoff * 2, max_backoff)

    def _send_subscription(self, instruments: list[tuple[str, str]]) -> None:
        """Send subscription JSON over live WebSocket."""
        payload = json.dumps(
            {
                "RequestCode": self.REQUEST_CODE,
                "InstrumentCount": len(instruments),
                "InstrumentList": [
                    {"ExchangeSegment": exchange, "SecurityId": security_id}
                    for exchange, security_id in instruments
                ],
            }
        )

        if not self._ws:
            self._dropped_depths += 1
            logger.warning("%s_subscription_dropped_no_ws", self.DEPTH_TYPE.lower())
            return

        loop = self._ws_loop
        if loop is None or not loop.is_running():
            self._dropped_depths += 1
            logger.warning(
                "%s_subscription_dropped_no_ws_loop", self.DEPTH_TYPE.lower()
            )
            return

        future = asyncio.run_coroutine_threadsafe(self._ws.send(payload), loop)

        def _on_send_done(fut) -> None:
            try:
                fut.result()
            except Exception as exc:
                self._dropped_depths += 1
                logger.error(
                    "%s_subscription_send_failed: %s", self.DEPTH_TYPE.lower(), exc
                )

        future.add_done_callback(_on_send_done)

    # ── Binary parsing ─────────────────────────────────────────────────────

    def _process_binary_message(self, data: bytes) -> None:
        """Parse binary depth packet and dispatch callbacks."""
        try:
            if len(data) < _HEADER_SIZE:
                logger.warning(
                    "%s_packet_too_short: %d bytes", self.DEPTH_TYPE.lower(), len(data)
                )
                return

            response_code = data[2]

            if self.header_carries_security_id:
                header_value = struct.unpack_from("<I", data, 4)[0]
            else:
                header_value = struct.unpack_from("<I", data, 8)[0]

            self._note_message_received()

            if response_code in (self.BID_RESPONSE_CODE, self.ASK_RESPONSE_CODE):
                depth_data = self._parse_depth_packet(data, response_code, header_value)
                self._dispatch_depth(depth_data)

        except Exception as exc:
            logger.exception("%s_parse_error: %s", self.DEPTH_TYPE.lower(), exc)

    def _parse_depth_packet(
        self, data: bytes, response_code: int, header_value: int
    ) -> dict:
        """Parse depth body of binary packet."""
        depth_levels = []

        for i in range(self.total_slots):
            offset = _HEADER_SIZE + (i * _LEVEL_SIZE)
            if offset + _LEVEL_SIZE > len(data):
                break
            price = struct.unpack_from("<d", data, offset)[0]
            quantity = struct.unpack_from("<I", data, offset + 8)[0]
            orders = struct.unpack_from("<I", data, offset + 12)[0]
            if quantity > 0:
                depth_levels.append(
                    DepthLevel(
                        price=Decimal(str(round(price, 2))),
                        quantity=quantity,
                        orders=orders,
                    )
                )

        return {
            "levels": depth_levels,
            "side": "bids" if response_code == self.BID_RESPONSE_CODE else "asks",
            "header_value": header_value,
        }

    def _resolve_implicit_security_id(self) -> int | None:
        """For depth-200, recover security_id from subscription."""
        if self._subscriptions:
            try:
                return int(self._subscriptions[0][1])
            except (ValueError, IndexError):
                pass
        with self._depth_cache_lock:
            if self._depth_cache:
                return next(iter(self._depth_cache))
        return None

    def _dispatch_depth(self, depth_data: dict) -> None:
        """Update depth cache and dispatch to callbacks / event bus."""
        side = depth_data["side"]
        levels = depth_data["levels"]

        if self.header_carries_security_id:
            sec_id = depth_data["header_value"]
        else:
            sec_id = self._resolve_implicit_security_id()

        if sec_id is None:
            self._dropped_depths += 1
            logger.warning(
                "%s_packet_dropped_no_security_id: arriving before subscribe()",
                self.DEPTH_TYPE.lower(),
            )
            return

        symbol = self._sec_id_to_symbol.get(sec_id, "")

        with self._depth_cache_lock:
            entry = self._depth_cache.setdefault(sec_id, {"bids": [], "asks": []})
            if levels:
                entry[side] = levels
            merged = MarketDepth(
                symbol=symbol,
                bids=list(entry["bids"]),
                asks=list(entry["asks"]),
                timestamp=datetime.now(UTC),
            )

        callbacks = self._snapshot_callbacks(self._depth_callbacks)
        for callback in callbacks:
            try:
                callback(merged)
            except Exception as exc:
                logger.error("%s_callback_error: %s", self.DEPTH_TYPE.lower(), exc)

        if self._event_bus:
            correlation_id = self.next_correlation_id(
                prefix=f"depth_{self.DEPTH_TYPE.lower()}"
            )
            self._event_bus.publish(
                {
                    "type": self.EVENT_NAME,
                    "depth": merged,
                    "depth_type": self.DEPTH_TYPE,
                    "correlation_id": correlation_id,
                    "symbol": symbol or None,
                }
            )
            self._published_depths += 1

    # ── WebSocket close ────────────────────────────────────────────────────

    def _close_active_websocket(
        self, ws: Any, *, loop: asyncio.AbstractEventLoop | None = None
    ) -> None:
        """Close live socket from synchronous caller."""
        close = getattr(ws, "close", None)
        if not callable(close):
            return
        try:
            if loop is not None and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(close(), loop)
                future.result(timeout=2.0)
            else:
                result = close()
                if asyncio.iscoroutine(result):
                    logger.debug(
                        "%s_auth_reconnect_close_skipped_no_loop",
                        self.DEPTH_TYPE.lower(),
                    )
        except Exception as exc:
            logger.debug(
                "%s_auth_reconnect_close_failed: %s", self.DEPTH_TYPE.lower(), exc
            )

    # ── Constants (for backward compatibility) ─────────────────────────────

    HEADER_SIZE = _HEADER_SIZE
    DEPTH_LEVEL_SIZE = _LEVEL_SIZE
    BID_RESPONSE_CODE = 41
    ASK_RESPONSE_CODE = 51

    def update_token(self, new_token: str) -> None:
        """Token-refresh hook - closes socket to reconnect with fresh auth."""
        if not new_token or new_token == self._access_token:
            return
        self._access_token = new_token
        self._request_auth_reconnect()

    def _request_auth_reconnect(self) -> None:
        """Close active WebSocket so reconnection loop picks up new token."""
        with self._lock:
            ws = self._ws
            loop = self._ws_loop
        if ws:
            self._close_active_websocket(ws, loop=loop)
