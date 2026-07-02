"""Unified binary-packet depth WebSocket feed for Dhan.

Plan §7.1: ``DhanDepth20Feed`` (50 instruments, depth-20 layout) and
``DhanDepth200Feed`` (1 instrument, depth-200 layout) used to duplicate
the binary-packet framing, header parsing, level loop, quantity filter,
side cache, reconnect loop, callback fan-out, and event-bus emission.
The only meaningful differences were:

- ``MAX_INSTRUMENTS``         (50 vs 1)
- ``TOTAL_DEPTH_PACKETS``     (20 vs 200)
- ``ENDPOINT``                (WS_DEPTH_20 vs WS_DEPTH_200)
- ``REQUEST_CODE``            (23 vs 23 — same)
- ``DEPTH_TYPE``              ("DEPTH_20" vs "DEPTH_200")
- Header layout in the binary packet itself (``security_id`` at offset 4
  for depth-20, ``num_rows`` at offset 8 for depth-200) — see Plan §5.1.

This module introduces :class:`BinaryDepthFeed` that owns the shared
machinery, plus thin subclasses ``DhanDepth20Feed`` and
``DhanDepth200Feed`` that preserve the exact public surface their callers
and tests already use.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from brokers.dhan.connection_admission import MarketFeedConnectionAdmission
from brokers.dhan.reconnecting_service import ReconnectingServiceMixin
from domain import DepthLevel, MarketDepth
from domain.symbols import normalize_symbol
from infrastructure.event_bus import DomainEvent, EventBus
from infrastructure.lifecycle.lifecycle import (
    HealthState,
    HealthStatus,
    ManagedService,
)

logger = logging.getLogger(__name__)


# Header / level sizes — must match production Dhan binary layout.
_HEADER_SIZE = 12
_LEVEL_SIZE = 16  # 8 bytes price + 4 bytes quantity + 4 bytes orders


class BinaryDepthFeed(ReconnectingServiceMixin, ManagedService):
    """Unified WebSocket feed for Dhan's binary depth streams.

    Parameters
    ----------
    total_slots:
        Number of depth levels per side that the wire format carries
        (20 for ``DhanDepth20Feed``, 200 for ``DhanDepth200Feed``).
    subs_per_connection:
        Hard cap on the number of (segment, security_id) tuples one
        connection may subscribe to (50 for depth-20, 1 for depth-200).
    endpoint, request_code, depth_type:
        Wire-format identifiers stamped on every message.
    header_carries_security_id:
        ``True`` for depth-20 (offset 4 = security_id); ``False`` for
        depth-200 (offset 8 = num_rows, security_id is implicit per
        connection). See Plan §5.1 for the layout divergence.
    name:
        ManagedService identifier — ``"dhan.depth_20"`` / ``"dhan.depth_200"``.
    event_name:
        EventBus event name — ``"DEPTH_20"`` / ``"DEPTH_200"``.
    """

    total_slots: int
    subs_per_connection: int
    ENDPOINT: str
    REQUEST_CODE: int
    DEPTH_TYPE: str
    name: str
    EVENT_NAME: str
    header_carries_security_id: bool

    # Binary packet constants (also exposed as class attrs for backwards compat)
    HEADER_SIZE = _HEADER_SIZE
    DEPTH_LEVEL_SIZE = _LEVEL_SIZE
    BID_RESPONSE_CODE = 41
    ASK_RESPONSE_CODE = 51

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
        event_bus: EventBus | None = None,
        admission: Any | None = None,
    ):
        self._client_id = client_id
        self._access_token = access_token
        self._event_bus = event_bus
        # Shared 429-cooldown tracking per (client_id, depth_type). Unlike
        # market-feed, depth-200 intentionally opens multiple concurrent
        # connections (one per instrument via Depth200ConnectionPool), so we
        # only reuse the cooldown bookkeeping here, never try_acquire/release
        # — the exclusive host lock is not appropriate for a connection type
        # that legitimately runs several connections at once.
        self._admission = admission or MarketFeedConnectionAdmission(
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

        # Public aliases preserved on the class so legacy code/tests reading
        # ``DhanDepth20Feed.MAX_INSTRUMENTS`` etc. still resolve.
        self.MAX_INSTRUMENTS = subs_per_connection
        self.TOTAL_DEPTH_PACKETS = total_slots

        self._subscriptions: list[tuple[str, str]] = []
        # Backwards-compat alias for code/tests reading ``_instruments``.
        self._instruments: list[tuple[str, str]] = self._subscriptions
        self._depth_callbacks: list[Callable[[MarketDepth], None]] = []
        self._callback_lock = threading.Lock()

        self._ws = None
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        # Plan §7.2: shared reconnect / message-tracking state from the
        # ReconnectingServiceMixin. The mixin replaces the duplicated
        # ``_stop_event``/``_is_connected``/``_reconnect_count``/``_last_message_at``
        # attributes that previously lived on every depth feed.
        self._init_reconnect_state()
        self._lock = threading.Lock()

        # Per-security_id depth cache.  Each entry holds the last-seen bids
        # and asks independently so that a one-sided packet never zeros out
        # the other side. For depth-200 (1 instrument per connection) there
        # is exactly one entry; the dict-keyed shape is future-proof against
        # gateway-level fan-out.
        self._depth_cache: dict[int, dict[str, list[DepthLevel]]] = {}
        self._depth_cache_lock = threading.Lock()
        # security_id → canonical symbol for EventBus routing and MarketDepth.symbol
        self._sec_id_to_symbol: dict[int, str] = {}
        # Counters surfaced via health() so an operator can see
        # drop+publish rates without scraping logs.
        self._published_depths = 0
        self._dropped_depths = 0

    # ── Subscription management ────────────────────────────────────────────

    @property
    def max_instruments(self) -> int:
        """Maximum number of instruments allowed per connection."""
        return self.subs_per_connection

    @property
    def subscriptions(self) -> list[tuple[str, str]]:
        """Return a copy of the current subscription list."""
        return list(self._subscriptions)

    @property
    def is_running(self) -> bool:
        """Whether the feed thread is alive (started and not stopped)."""
        return bool(self._thread and self._thread.is_alive())

    def on_depth(self, callback: Callable[[MarketDepth], None]) -> None:
        """Register a callback for depth updates."""
        with self._callback_lock:
            self._depth_callbacks.append(callback)

    def register_symbol(self, security_id: int, symbol: str) -> None:
        """Map a Dhan security_id to a canonical symbol for event routing."""
        self._sec_id_to_symbol[int(security_id)] = normalize_symbol(symbol)

    def subscribe(self, instruments: list[tuple[str, str]] | tuple[str, str]) -> None:
        """Subscribe to one or more instruments.

        Accepts either a single tuple (depth-200 style) or a list of tuples
        (depth-20 style). Both call sites are preserved.
        """
        new_instruments = [instruments] if isinstance(instruments, tuple) else list(instruments)

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

    def unsubscribe(
        self, instruments: list[tuple[str, str]] | tuple[str, str] | None = None
    ) -> None:
        """Unsubscribe from instruments and evict their depth cache entries."""
        if instruments is None:
            removed = list(self._subscriptions)
            self._subscriptions.clear()
            with self._depth_cache_lock:
                self._depth_cache.clear()
            logger.info("%s_unsubscribe_all", self.DEPTH_TYPE.lower())
            return

        instruments_list = [instruments] if isinstance(instruments, tuple) else list(instruments)

        removed: list[tuple[str, str]] = []
        for inst in instruments_list:
            if inst in self._subscriptions:
                self._subscriptions.remove(inst)
                removed.append(inst)
                try:
                    sec_id = int(inst[1])
                    with self._depth_cache_lock:
                        self._depth_cache.pop(sec_id, None)
                except (ValueError, IndexError):
                    pass

        if removed:
            logger.info(
                "%s_unsubscribe",
                self.DEPTH_TYPE.lower(),
                extra={"count": len(removed), "total": len(self._subscriptions)},
            )

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Deprecated alias for :meth:`start`."""
        self.start()

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

    def disconnect(self, timeout_seconds: float = 5.0) -> None:
        """Deprecated alias for :meth:`stop`."""
        self.stop(timeout_seconds)

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

        logger.info("%s_stopped", self.DEPTH_TYPE.lower())

    def health(self) -> HealthStatus:
        """ManagedService protocol: return a point-in-time health snapshot."""
        with self._lock:
            thread_alive = bool(self._thread and self._thread.is_alive())
            is_connected = self._is_connected
            reconnect_count = self._reconnect_count
            last_message_age = (
                (datetime.now(timezone.utc) - self._last_message_at).total_seconds()
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
            last_check=datetime.now(timezone.utc),
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
                time.sleep(min(2 ** min(self._reconnect_count, 5), 30))

    def _connect_and_run(self) -> None:
        """Establish WebSocket connection and process messages."""
        import importlib.util

        if importlib.util.find_spec("websockets") is None:
            logger.error("websockets package not installed: pip install websockets")
            return

        logger.info("%s_connecting", self.DEPTH_TYPE.lower(), extra={"endpoint": self.ENDPOINT})

        # Run async WebSocket in a new event loop
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

    def _build_ws_url(self) -> str:
        """Build the authenticated WebSocket URL using the current token."""
        return f"{self.ENDPOINT}?token={self._access_token}&clientId={self._client_id}&authType=2"

    async def _websocket_handler(self) -> None:
        """Async WebSocket handler with auto-reconnect."""
        import websockets

        backoff = 1.0
        max_backoff = 30.0

        while not self._stop_event.is_set():
            # ── 429 cooldown ────────────────────────────────────────────────
            cooldown_wait = self._admission.seconds_until_connect_allowed()
            if cooldown_wait > 0:
                logger.info(
                    "%s_connect_cooldown_wait",
                    self.DEPTH_TYPE.lower(),
                    extra={"seconds": round(cooldown_wait, 2)},
                )
                await asyncio.sleep(min(cooldown_wait, 5.0))
                continue

            url = self._build_ws_url()
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

                        except asyncio.TimeoutError:
                            continue

                        except websockets.ConnectionClosed:
                            logger.warning("%s_connection_closed", self.DEPTH_TYPE.lower())
                            break

            except Exception as exc:
                err_str = str(exc).lower()
                if "429" in err_str:
                    logger.warning(
                        "%s WebSocket rate limited, backing off", self.DEPTH_TYPE.lower()
                    )
                    self._admission.record_rate_limit_cooldown()
                else:
                    logger.error("%s_connection_error: %s", self.DEPTH_TYPE.lower(), exc)
                with self._lock:
                    self._is_connected = False
                    self._ws = None
                    self._reconnect_count += 1

            if not self._stop_event.is_set():
                wait_time = min(backoff, max_backoff)
                logger.info("%s_reconnecting in %.1fs", self.DEPTH_TYPE.lower(), wait_time)
                await asyncio.sleep(wait_time)
                backoff = min(backoff * 2, max_backoff)

    def _send_subscription(self, instruments: list[tuple[str, str]]) -> None:
        """Send subscription JSON message over the live WebSocket.

        The Dhan depth WebSocket is driven by an async event loop running
        on a dedicated thread; we are called from the depth feed thread
        (synchronous) and need to hand the send to that loop.

        Previous implementation used ``loop.create_task(self._ws.send(...))``
        and never awaited the task. If the loop closed between scheduling
        and execution, the subscription message was silently dropped and
        the reconnected connection would carry no instruments — depth
        data would never arrive without any error or counter increment.

        The new implementation uses ``asyncio.run_coroutine_threadsafe``,
        which:
        - returns a ``concurrent.futures.Future`` we can monitor for
          delivery confirmation, and
        - raises immediately if the loop has already closed (instead of
          silently dropping the task).

        In test contexts (no running loop) we log a warning and increment
        a counter rather than swallowing the failure silently.
        """
        subscription_msg = {
            "RequestCode": self.REQUEST_CODE,
            "InstrumentCount": len(instruments),
            "InstrumentList": [
                {
                    "ExchangeSegment": exchange,
                    "SecurityId": security_id,
                }
                for exchange, security_id in instruments
            ],
        }
        payload = json.dumps(subscription_msg)

        logger.debug(
            "%s_subscription_sending",
            self.DEPTH_TYPE.lower(),
            extra={"count": len(instruments)},
        )

        if not self._ws:
            self._dropped_depths += 1
            logger.warning("%s_subscription_dropped_no_ws", self.DEPTH_TYPE.lower())
            return

        # Subscriptions from gateway threads must use the feed's dedicated loop,
        # not asyncio.get_running_loop() on the caller thread.
        loop = self._ws_loop
        if loop is None or not loop.is_running():
            self._dropped_depths += 1
            logger.warning(
                "%s_subscription_dropped_no_ws_loop",
                self.DEPTH_TYPE.lower(),
            )
            return

        # run_coroutine_threadsafe returns a concurrent.futures.Future.
        # We register a done-callback so failures increment the dropped
        # counter instead of vanishing.
        future = asyncio.run_coroutine_threadsafe(self._ws.send(payload), loop)

        def _on_send_done(fut) -> None:
            try:
                fut.result()
            except Exception as exc:
                self._dropped_depths += 1
                logger.error(
                    "%s_subscription_send_failed: %s",
                    self.DEPTH_TYPE.lower(),
                    exc,
                )

        future.add_done_callback(_on_send_done)

    # ── Binary parsing ─────────────────────────────────────────────────────

    def _process_binary_message(self, data: bytes) -> None:
        """Parse binary depth packet and dispatch callbacks."""
        try:
            if len(data) < _HEADER_SIZE:
                logger.warning(
                    "%s_packet_too_short: %d bytes",
                    self.DEPTH_TYPE.lower(),
                    len(data),
                )
                return

            response_code = data[2]

            if self.header_carries_security_id:
                # depth-20 layout: offset 4 = security_id
                header_value = struct.unpack_from("<I", data, 4)[0]
            else:
                # depth-200 layout: offset 8 = num_rows
                header_value = struct.unpack_from("<I", data, 8)[0]

            # Plan §7.2: shared message tracking through the mixin so the
            # health endpoint reflects real bytes received, not heartbeat-only.
            self._note_message_received()

            if response_code in (self.BID_RESPONSE_CODE, self.ASK_RESPONSE_CODE):
                depth_data = self._parse_depth_packet(data, response_code, header_value)
                self._dispatch_depth(depth_data)

        except Exception as exc:
            logger.exception(
                "%s_parse_error: %s",
                self.DEPTH_TYPE.lower(),
                exc,
            )

    def _parse_depth_packet(self, data: bytes, response_code: int, header_value: int) -> dict:
        """Parse the depth body of a binary packet.

        For depth-20 ``header_value`` is the security_id (extracted from
        offset 4). For depth-200 ``header_value`` is the row count (offset 8);
        the security_id is implicit (one instrument per connection).
        """
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
        """For depth-200 (single instrument per connection), recover the
        security_id from the existing subscription.

        Returns ``None`` if no instrument is yet subscribed AND the cache
        is empty. Returning ``None`` (rather than the previous ``0``) makes
        the dispatcher DROP the packet instead of silently caching it
        under key ``0``. Under the legacy behaviour, a depth-200 packet
        received before :meth:`subscribe` would land in cache key ``0``;
        the next packet after subscribe could keep going to key ``0``
        until the cache was invalidated, producing a real race window
        for live depth-200 data.
        """
        if self._subscriptions:
            try:
                return int(self._subscriptions[0][1])
            except (ValueError, IndexError):
                pass
        # If a cache entry already exists (from a previous connection),
        # reuse its key — the dispatcher has been writing consistently to
        # the real security_id and we should keep doing so.
        with self._depth_cache_lock:
            if self._depth_cache:
                return next(iter(self._depth_cache))
        # No subscription, no cache: cannot resolve. Caller drops the packet.
        return None

    def _dispatch_depth(self, depth_data: dict) -> None:
        """Update the depth cache and dispatch to callbacks / event bus."""
        side = depth_data["side"]
        levels = depth_data["levels"]
        # depth-20: header_value IS the security_id.
        # depth-200: header_value is num_rows; security_id is implicit
        # (one instrument per connection). If we cannot resolve the
        # implicit security_id (no subscription, empty cache), drop the
        # packet rather than silently caching it under a placeholder.
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
            # Dhan sends bid/ask in separate packets; never wipe a side with
            # an empty level list (can happen when qty filter drops all rows).
            if levels:
                entry[side] = levels
            merged = MarketDepth(
                symbol=symbol,
                bids=list(entry["bids"]),
                asks=list(entry["asks"]),
                depth_type=self.DEPTH_TYPE,
                timestamp=datetime.now(timezone.utc),
            )

        callbacks = self._snapshot_callbacks(self._depth_callbacks)
        for callback in callbacks:
            try:
                callback(merged)
            except Exception as exc:
                logger.error("%s_callback_error: %s", self.DEPTH_TYPE.lower(), exc)

        if self._event_bus:
            try:
                # Plan §7.2: stamp every published event with a correlation
                # id so an event-bus subscriber can trace one logical
                # operation end-to-end (was a gap in §4 invariant checklist).
                correlation_id = self.next_correlation_id(prefix=f"depth_{self.DEPTH_TYPE.lower()}")
                self._event_bus.publish(
                    DomainEvent.now(
                        self.EVENT_NAME,
                        {
                            "depth": merged,
                            "depth_type": self.DEPTH_TYPE,
                            "correlation_id": correlation_id,
                        },
                        symbol=symbol or None,
                        source=self.name,
                        correlation_id=correlation_id,
                    )
                )
                self._published_depths += 1
            except Exception as exc:
                self._dropped_depths += 1
                logger.error("%s_event_publish_error: %s", self.DEPTH_TYPE.lower(), exc)

    def _close_active_websocket(
        self,
        ws: Any,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """Close the live socket from a synchronous caller."""
        close = getattr(ws, "close", None)
        if not callable(close):
            return
        try:
            if loop is not None and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(close(), loop)
                future.result(timeout=2.0)
                return
            result = close()
            if asyncio.iscoroutine(result):
                logger.debug(
                    "%s_auth_reconnect_close_skipped_no_loop",
                    self.DEPTH_TYPE.lower(),
                )
        except Exception as exc:
            logger.debug(
                "%s_auth_reconnect_close_failed: %s",
                self.DEPTH_TYPE.lower(),
                exc,
            )

    def update_token(self, new_token: str) -> None:
        """Token-refresh hook called by ``DhanConnection.register_token_receiver``.

        Updates the cached token and closes the live socket so the reconnect
        loop picks up the new credentials immediately.
        """
        if not new_token or new_token == self._access_token:
            return
        self._access_token = new_token
        self.request_auth_reconnect()

    def request_auth_reconnect(self) -> None:
        """Close the active WebSocket so ``_websocket_loop`` reconnects with fresh auth."""
        with self._lock:
            ws = self._ws
            loop = self._ws_loop
        if ws is None:
            return
        self._close_active_websocket(ws, loop=loop)
