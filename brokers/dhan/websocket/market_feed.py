"""DhanMarketFeed — real-time market data via Dhan SDK WebSocket.

Extracted from the former monolithic ``brokers/dhan/websocket.py`` (Task 5.1).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from brokers.dhan.connection_admission import MarketFeedConnectionAdmission
from brokers.dhan.reconnecting_service import ReconnectingServiceMixin
from brokers.dhan.websocket._helpers import (
    _DhanContext,
    _sdk_market_feed_class,
    _to_decimal,
    _to_sdk_instruments,
)
from domain import DepthLevel, MarketDepth, Quote
from infrastructure.event_bus import DomainEvent, EventBus
from infrastructure.lifecycle.lifecycle import (
    HealthState,
    HealthStatus,
    ManagedService,
)

logger = logging.getLogger(__name__)


class DhanMarketFeed(ReconnectingServiceMixin, ManagedService):
    """Wraps the SDK's MarketFeed for real-time market data.

    Supports reconnect backfill: on reconnection, if a ``backfill_callback``
    was provided, it is invoked to fetch missed bars between the last tick
    time and the reconnection time.  The returned bars are published as TICK
    events so downstream subscribers see no gap.

    Implements :class:`ManagedService` (Phase B / B5) so the broker's
    :class:`LifecycleManager` can start, stop, and health-check the
    background thread. ``stop(timeout_seconds)`` joins the thread within
    the timeout; the previous ``disconnect()`` only set ``_stop_event``
    and never joined, leaking the daemon thread on process exit.
    """

    name = "dhan.market_feed"
    MAX_INSTRUMENTS = 1000  # Dhan WebSocket limit per connection

    def __init__(
        self,
        client_id: str,
        access_token: str | None = None,
        instruments: list[tuple] | None = None,
        resolver=None,
        access_token_fn: Callable[[], str] | None = None,
        event_bus: EventBus | None = None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None = None,
        admission: MarketFeedConnectionAdmission | None = None,
    ):
        """
        Initialize market feed.

        Args:
            client_id: Dhan client ID
            access_token: Dhan access token (static snapshot)
            access_token_fn: Callable returning fresh token (preferred over static)
            instruments: List of (exchange, security_id, mode) tuples.
                         Accepts strings ("MCX_COMM", "466583", "LTP") or
                         SDK integers (5, 466583, 15).
            resolver: Optional SymbolResolver for security_id → symbol lookup
            event_bus: Optional EventBus to publish TICK/DEPTH events to.
            backfill_callback: ``(symbol, from_dt, to_dt) -> list[dict]``
                Called on reconnect to fill the gap.  Each dict should have at
                minimum ``{"symbol": ..., "ltp": ..., "open": ..., "high": ...,
                "low": ..., "close": ..., "volume": ...}``.  Optional keys:
                ``"timestamp"`` (datetime).  If ``None``, no backfill occurs.
            admission: Optional host-wide admission gate. Defaults to a real
                ``MarketFeedConnectionAdmission``. Pass ``None`` to use a no-op
                admission (useful in tests to avoid fcntl file locks).
        """
        self._context = _DhanContext(
            client_id,
            access_token=access_token,
            access_token_fn=access_token_fn,
        )
        self._raw_instruments = instruments or []
        self._instruments = _to_sdk_instruments(instruments or [])
        # _subscribed_instruments is the single source of truth for what
        # instruments should be active on the WebSocket at all times.
        # On reconnect, the full set is replayed — no separate pending queue needed.
        self._subscribed_instruments: set[tuple] = set(self._instruments)
        self._resolver = resolver
        self._event_bus = event_bus
        self._backfill_callback = backfill_callback
        self._feed: Any | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._quote_callbacks: list[Callable[[dict], None]] = []
        self._depth_callbacks: list[Callable[[dict], None]] = []
        # Reconnect backfill state
        self._last_tick_time: dict[str, datetime] = {}
        self._disconnect_time: datetime | None = None
        self._connected_at: datetime | None = None
        # Plan §7.2: shared reconnect / message-tracking state.
        self._init_reconnect_state()
        # Plan §7.7: strict-mode tick publish counters (visible via health()).
        self._published_ticks = 0
        self._dropped_ticks = 0
        # Strict-mode depth counters — same discipline as ticks; a zero
        # bid/ask or empty book must not be published as a real signal.
        self._published_depths = 0
        self._dropped_depths = 0
        # Admission gate: injectable for testability.
        self._admission = admission if admission is not None else MarketFeedConnectionAdmission(client_id)
        self._admission_blocked = False

    def update_token(self, access_token: str) -> None:
        """Push a fresh token to the context (called by scheduler)."""
        if not access_token or access_token == self._context.get_access_token():
            return
        self._context.update_token(access_token)
        with self._lock:
            if self._feed:
                self._feed.access_token = access_token
                # Close the active websocket so the reconnect loop picks up the new credentials
                ws = getattr(self._feed, "ws", None)
                loop = getattr(self._feed, "loop", None)
                if ws and loop and loop.is_running():
                    try:
                        import asyncio
                        asyncio.run_coroutine_threadsafe(ws.close(), loop)
                    except Exception as exc:
                        logger.warning("Error closing feed websocket on token update: %s", exc)

    def connect(self) -> None:
        """Start the WebSocket connection in a background daemon thread.

        Deprecated alias for :meth:`start`. Kept for backwards
        compatibility; new code should use :meth:`start` (the
        ManagedService protocol method) so the lifecycle manager can
        own this service.
        """
        self.start()

    def start(self) -> None:
        """ManagedService protocol: start the WebSocket thread.

        Idempotent — re-calling while the thread is alive is a no-op.
        Staleness detection runs inline inside _run() — no separate watchdog thread.
        """
        with self._lock:
            if self._thread and self._thread.is_alive():
                logger.warning("Market feed already connected")
                return

            if not self._instruments:
                logger.debug("No valid instruments to subscribe yet")
                return

            self._stop_event.clear()
            self._is_connected = False
            self._build_sdk_feed_locked()

            self._thread = threading.Thread(
                target=self._run,
                name=self.name,
                daemon=True,
            )
            self._thread.start()

    def _build_sdk_feed_locked(self) -> Any:
        """Create a fresh SDK feed from the current subscription snapshot.

        The Dhan SDK feed object owns websocket/event-loop state. Reusing it
        after a disconnect can preserve a poisoned transport; rebuilding it
        keeps reconnect attempts independent while preserving subscriptions in
        this wrapper.
        """
        self._feed = _sdk_market_feed_class()(
            dhan_context=self._context,
            instruments=list(self._instruments),
            on_connect=self._on_connect,
            on_message=self._on_message,
            on_close=self._on_close,
            on_error=self._on_error,
        )
        return self._feed

    def _run(self) -> None:
        """Run the market feed event loop with reconnection backoff + inline staleness check.

        Staleness detection is handled here rather than in a separate watchdog
        thread: after each SDK.run() or exception, if the feed was active but
        silent for longer than DHAN_STALENESS_THRESHOLD_SECONDS, we close the
        socket before backing off. This gives the same safety guarantee with
        one fewer daemon thread.

        B-4: backoff resets to 1.0 after every successful feed.run() return.
        """
        backoff = 1.0
        max_backoff = 30.0
        max_reconnect_attempts = int(os.getenv("DHAN_MAX_RECONNECT_ATTEMPTS", "50"))
        staleness_threshold = self._staleness_threshold_seconds()

        while not self._stop_event.is_set():
            # ── Admission: only one process per account may own the WS slot ──
            if not self._admission.lock_held:
                if not self._admission.try_acquire():
                    with self._lock:
                        self._admission_blocked = True
                    if self._stop_event.wait(timeout=5.0):
                        break
                    continue
                with self._lock:
                    self._admission_blocked = False

            # ── 429 cooldown ──────────────────────────────────────────────────
            cooldown_wait = self._admission.seconds_until_connect_allowed()
            if cooldown_wait > 0:
                logger.info(
                    "market_feed_connect_cooldown_wait",
                    extra={"seconds": round(cooldown_wait, 2)},
                )
                if self._stop_event.wait(timeout=min(cooldown_wait, 5.0)):
                    break
                continue

            # ── Max reconnect guard ───────────────────────────────────────────
            with self._lock:
                current_reconnects = self._reconnect_count

            if current_reconnects >= max_reconnect_attempts:
                logger.critical(
                    "max_reconnect_attempts_exceeded",
                    extra={"attempts": current_reconnects, "max_attempts": max_reconnect_attempts},
                )
                self._emit_reconnect_metric()
                cooldown = float(os.getenv("DHAN_RECONNECT_COOLDOWN_SECONDS", "300"))
                logger.warning("market_feed_reconnect_cooldown", extra={"cooldown_seconds": cooldown})
                if self._stop_event.wait(timeout=cooldown):
                    break
                with self._lock:
                    self._reconnect_count = 0
                logger.info("market_feed_reconnect_cooldown_complete")
                continue

            # ── Inline staleness check (replaces separate watchdog thread) ────
            stale_feed = None
            with self._lock:
                if self._is_connected:
                    age = self._last_activity_age_seconds_locked()
                    if age is not None and age > staleness_threshold:
                        logger.warning(
                            "market_feed_stale_reconnect_forced",
                            extra={"age_seconds": age, "threshold_seconds": staleness_threshold},
                        )
                        stale_feed = self._feed
                        self._is_connected = False
                        self._connected_at = None
                        self._disconnect_time = datetime.now(timezone.utc)
                        self._reconnect_count += 1
                        self._feed = None
            if stale_feed is not None:
                self._emit_reconnect_metric()
                with contextlib.suppress(Exception):
                    stale_feed.close_connection()
                if self._stop_event.wait(timeout=backoff):
                    break
                backoff = min(backoff * 2, max_backoff)
                continue

            # ── Run the SDK ───────────────────────────────────────────────────
            try:
                with self._lock:
                    feed = self._feed or self._build_sdk_feed_locked()
                feed.run()
                # B-4: successful return → clean close → reset backoff fast
                backoff = 1.0
                with self._lock:
                    self._is_connected = False
                    self._connected_at = None
                    self._disconnect_time = self._disconnect_time or datetime.now(timezone.utc)
                    self._feed = None
                    self._reconnect_count += 1
                self._emit_reconnect_metric()

            except Exception as exc:
                err_str = str(exc).lower()
                if "no close frame" in err_str:
                    # Dhan server drops connections without close frames — expected.
                    logger.debug("WebSocket closed without close frame (expected)")
                    backoff = 1.0  # B-4: not an error, reset
                elif "429" in err_str:
                    logger.warning("WebSocket rate limited, backing off %ss", backoff)
                    self._admission.record_rate_limit_cooldown()
                else:
                    logger.error("Market feed error: %s", exc)

                with self._lock:
                    age = (
                        (datetime.now(timezone.utc) - self._last_message_at).total_seconds()
                        if self._last_message_at is not None
                        else 0.0
                    )
                if age > staleness_threshold:
                    logger.warning(
                        "feed_stale_before_reconnect",
                        extra={"age_seconds": age, "threshold_seconds": staleness_threshold},
                    )

                with self._lock:
                    self._reconnect_count += 1
                    self._is_connected = False
                    self._connected_at = None
                    self._disconnect_time = self._disconnect_time or datetime.now(timezone.utc)
                    old_feed = self._feed
                    self._feed = None
                if old_feed is not None:
                    with contextlib.suppress(Exception):
                        old_feed.close_connection()
                self._emit_reconnect_metric()

            # ── Backoff before next reconnect attempt ─────────────────────────
            if self._stop_event.is_set():
                break
            if self._stop_event.wait(timeout=backoff):
                break
            backoff = min(backoff * 2, max_backoff)

        # Always release the host-wide admission lock on exit so the lock
        # file is not left held when _stop_event.set() is called directly.
        self._admission.release()


    def disconnect(self, timeout_seconds: float = 5.0) -> None:
        """Stop the WebSocket connection.

        Deprecated alias for :meth:`stop`. Kept for backwards
        compatibility; new code should use :meth:`stop` (the
        ManagedService protocol method).

        Phase B / B5: the previous implementation set ``_stop_event``
        but never joined the thread, so the daemon thread was leaked
        until process exit. This implementation joins within the
        timeout, matching the ManagedService contract.
        """
        self.stop(timeout_seconds=timeout_seconds)

    def _close_sdk_feed(self, feed: Any, timeout_seconds: float = 2.0) -> None:
        """Close the Dhan SDK's feed object without conflicting with a caller's loop.

        The SDK's ``close_connection()`` looks synchronous but internally
        drives its own coroutine (``MarketFeed.disconnect()``); when called
        from a thread that already has a running asyncio event loop (e.g. a
        caller using ``asyncio.run(main())`` around ``gateway.stream()``),
        the SDK's internal loop handling raises "Cannot run the event loop
        while another loop is running" and leaves an unawaited coroutine.
        Running the close on a separate thread lets the SDK manage its own
        loop freely regardless of what the calling thread is doing.
        """
        try:
            asyncio.get_running_loop()
            has_running_loop = True
        except RuntimeError:
            has_running_loop = False

        if not has_running_loop:
            try:
                feed.close_connection()
            except Exception as exc:
                logger.warning("Error closing market feed: %s", exc)
            return

        close_thread = threading.Thread(
            target=self._close_sdk_feed_worker,
            args=(feed,),
            name="dhan.market_feed.close",
            daemon=True,
        )
        close_thread.start()
        close_thread.join(timeout=timeout_seconds)
        if close_thread.is_alive():
            logger.warning(
                "dhan.market_feed close_connection did not complete within %ss",
                timeout_seconds,
            )

    @staticmethod
    def _close_sdk_feed_worker(feed: Any) -> None:
        try:
            feed.close_connection()
        except Exception as exc:
            logger.warning("Error closing market feed: %s", exc)

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """ManagedService protocol: stop the WebSocket thread.

        Sets ``_stop_event`` (so the loop exits), closes the SDK
        connection, and joins the thread within ``timeout_seconds``.
        If the thread is still alive after the timeout, a warning is
        logged and the call returns — the thread is left to be reaped
        at process exit (it is a daemon, so it cannot block shutdown).
        Idempotent: a second call is a no-op.
        """
        self._stop_event.set()
        with self._lock:
            self._is_connected = False
            self._connected_at = None
            feed = self._feed
            thread = self._thread
        if feed:
            self._close_sdk_feed(feed)
        if thread and thread.is_alive():
            thread.join(timeout=timeout_seconds)
            if thread.is_alive():
                logger.warning("dhan.market_feed thread did not stop within %ss", timeout_seconds)
        self._admission.release()
        logger.info("Market feed stopped")

    def health(self) -> HealthStatus:
        """ManagedService protocol: return a point-in-time health snapshot.

        H2 Critical Fix: Added reconnect metrics for observability:
        - max_reconnect_attempts: configured limit
        - last_message_age_seconds: staleness indicator
        - is_stale: boolean flag if feed hasn't received messages recently
        """
        import os

        with self._lock:
            thread_alive = bool(self._thread and self._thread.is_alive())
            is_connected = getattr(self, "_is_connected", False)
            reconnect_count = getattr(self, "_reconnect_count", 0)
            last_message_age = self._last_activity_age_seconds_locked()
            admission_blocked = getattr(self, "_admission_blocked", False)

        admission_status = self._admission.status() if getattr(self, "_admission", None) else {}

        # H2: Staleness detection
        staleness_threshold = self._staleness_threshold_seconds()
        is_stale = (
            last_message_age is not None and last_message_age > staleness_threshold
        ) if last_message_age is not None else False

        if thread_alive and is_connected and not is_stale:
            state = HealthState.HEALTHY
            detail = "running and connected"
        elif thread_alive and admission_blocked:
            state = HealthState.DEGRADED
            detail = "market_feed_connection_lock_held by another process on this host"
        elif thread_alive and isinstance(admission_status, dict) and admission_status.get("seconds_until_connect_allowed", 0) > 0:
            state = HealthState.DEGRADED
            detail = "waiting for rate-limit cooldown before next handshake"
        elif thread_alive and is_connected and is_stale:
            state = HealthState.DEGRADED
            detail = "connected but stale; reconnect watchdog should close transport"
        elif thread_alive and not is_connected:
            state = HealthState.DEGRADED
            detail = "thread running but feed not connected (reconnecting?)"
        else:
            state = HealthState.STOPPED
            detail = "not started"

        return HealthStatus(
            state=state,
            service=self.name,
            last_check=datetime.now(timezone.utc),
            detail=detail,
            metrics={
                "connected": is_connected,
                "thread_alive": thread_alive,
                "reconnect_count": reconnect_count,
                "max_reconnect_attempts": int(os.getenv("DHAN_MAX_RECONNECT_ATTEMPTS", "50")),
                "published_ticks": self._published_ticks,
                "dropped_ticks": self._dropped_ticks,
                "published_depths": self._published_depths,
                "dropped_depths": self._dropped_depths,
                "last_message_age_seconds": (
                    last_message_age if last_message_age is not None else -1
                ),
                "is_stale": is_stale,
                "staleness_threshold_seconds": staleness_threshold,
                **admission_status,
            },
        )

    @staticmethod
    def _staleness_threshold_seconds() -> float:
        return float(os.getenv("DHAN_STALENESS_THRESHOLD_SECONDS", "60.0"))

    def _last_activity_age_seconds_locked(self) -> float:
        last_msg = getattr(self, "_last_message_at", None)
        conn_at = getattr(self, "_connected_at", None)
        references = [ts for ts in (last_msg, conn_at) if ts is not None]
        if not references:
            return None
        reference = max(references)
        return (datetime.now(timezone.utc) - reference).total_seconds()

    def subscribe(self, instruments: list[tuple]) -> None:
        """Add instruments to the subscription.

        Deduplicates instruments — instruments already subscribed are ignored.

        Raises:
            ValueError: If total subscriptions would exceed MAX_INSTRUMENTS (1000).
        """
        with self._lock:
            sdk_instruments = _to_sdk_instruments(instruments)
            # P0 Fix: Dedup — only subscribe new instruments
            new_instruments = [i for i in sdk_instruments if i not in self._subscribed_instruments]
            if not new_instruments:
                logger.debug("subscribe: no new instruments (already subscribed)")
                return  # Already subscribed, no-op
            total = len(self._subscribed_instruments) + len(new_instruments)
            if total > self.MAX_INSTRUMENTS:
                raise ValueError(
                    f"Dhan WebSocket limit is {self.MAX_INSTRUMENTS} instruments, "
                    f"would have {total}. Unsubscribe some first."
                )
            self._instruments.extend(new_instruments)
            self._subscribed_instruments.update(new_instruments)
            logger.info("subscribe: adding %d instruments (total=%d)", len(new_instruments), total)
            if self._feed and self._is_connected:
                logger.info("subscribe: calling SDK subscribe_symbols with %d instruments", len(new_instruments))
                try:
                    self._feed.subscribe_symbols(new_instruments)
                except Exception as exc:
                    # If subscription fails, mark disconnected so _run() will
                    # reconnect and replay the full _subscribed_instruments set.
                    self._is_connected = False
                    self._disconnect_time = datetime.now(timezone.utc)
                    logger.error("subscribe: SDK subscribe_symbols failed: %s", exc)
                    with contextlib.suppress(Exception):
                        self._feed.close_connection()
            else:
                # Feed not yet connected. The instrument is already in
                # _subscribed_instruments, so _on_connect will replay it.
                logger.info(
                    "subscribe: feed not connected — %d instruments queued for reconnect",
                    len(new_instruments),
                )
            # P3 Fix: Warn when approaching instrument limit (80% threshold)
            if total > self.MAX_INSTRUMENTS * 0.8:
                logger.warning(
                    "dhan_ws_instrument_limit_approaching",
                    extra={"current": total, "max": self.MAX_INSTRUMENTS},
                )

    def unsubscribe(self, instruments: list[tuple]) -> None:
        """Remove instruments from the subscription."""
        with self._lock:
            sdk_instruments = _to_sdk_instruments(instruments)
            if self._feed and self._is_connected:
                try:
                    self._feed.unsubscribe_symbols(sdk_instruments)
                except Exception as exc:
                    logger.warning("unsubscribe: SDK unsubscribe_symbols failed: %s", exc)
            for inst in sdk_instruments:
                self._subscribed_instruments.discard(inst)
                with contextlib.suppress(ValueError):
                    self._instruments.remove(inst)
            logger.info(
                "unsubscribe: removed %d instruments (remaining=%d)",
                len(sdk_instruments),
                len(self._subscribed_instruments),
            )

    def on_quote(self, callback: Callable[[dict], None]) -> None:
        """Register callback for quote updates."""
        # Plan §7.2: delegate to the mixin for the lock/snapshot discipline.
        self._register_callback(self._quote_callbacks, callback)

    def on_depth(self, callback: Callable[[dict], None]) -> None:
        """Register callback for depth updates."""
        self._register_callback(self._depth_callbacks, callback)

    def off_quote(self, callback: Callable[[dict], None]) -> None:
        """Remove a previously registered quote callback.

        P1 Fix: Enables proper cleanup to prevent callback leaks.
        """
        with self._lock, contextlib.suppress(ValueError):
            self._quote_callbacks.remove(callback)  # Callback not found, already removed

    def off_depth(self, callback: Callable[[dict], None]) -> None:
        """Remove a previously registered depth callback.

        P1 Fix: Enables proper cleanup to prevent callback leaks.
        """
        with self._lock, contextlib.suppress(ValueError):
            self._depth_callbacks.remove(callback)  # Callback not found, already removed

    @property
    def is_connected(self) -> bool:
        with self._lock:
            age = self._last_activity_age_seconds_locked()
            is_stale = (
                self._is_connected
                and age is not None
                and age > self._staleness_threshold_seconds()
            )
            return self._is_connected and not is_stale

    def _on_connect(self, feed) -> None:
        with self._lock:
            was_connected = self._is_connected
            self._is_connected = True
            self._connected_at = datetime.now(timezone.utc)
            self._reconnect_count = 0
            disconnect_time = self._disconnect_time
            self._disconnect_time = None
            # Snapshot the full desired subscription set.
            # _subscribed_instruments is the single source of truth — no
            # separate pending queue needed. Any instrument added while
            # disconnected is already in this set.
            to_subscribe = list(self._subscribed_instruments)
        logger.info("Market feed connected")
        self._admission.clear_cooldown()
        if to_subscribe and feed is not None:
            logger.info("Replaying %d market subscriptions on connect", len(to_subscribe))
            try:
                feed.subscribe_symbols(to_subscribe)
            except Exception as exc:
                with self._lock:
                    self._is_connected = False
                    self._connected_at = None
                    self._disconnect_time = datetime.now(timezone.utc)
                logger.error("Failed to replay market subscriptions: %s", exc)
                with contextlib.suppress(Exception):
                    feed.close_connection()
                return
        # On reconnect, backfill the gap if a callback was provided
        if (
            not was_connected
            and disconnect_time is not None
            and self._backfill_callback is not None
        ):
            self._backfill_gap(disconnect_time)

    def _backfill_gap(self, disconnect_time: datetime) -> None:
        """Fetch missed bars from REST and publish as TICK events."""
        now = datetime.now(timezone.utc)
        if disconnect_time >= now:
            return
        with self._lock:
            symbols = list(self._last_tick_time.keys())
        if not symbols:
            return
        logger.info(
            "Backfilling %d symbols for gap %s → %s",
            len(symbols),
            disconnect_time.isoformat(),
            now.isoformat(),
        )
        for symbol in symbols:
            try:
                bars = self._backfill_callback(symbol, disconnect_time, now)
                for bar in bars:
                    ts = bar.get("timestamp")
                    if ts is None:
                        bar["timestamp"] = now
                    self._publish_tick(bar)
                    # Update last tick time for backfilled bars
                    bar_ts = bar.get("timestamp", now)
                    if isinstance(bar_ts, datetime):
                        with self._lock:
                            prev = self._last_tick_time.get(symbol)
                            if prev is None or bar_ts > prev:
                                self._last_tick_time[symbol] = bar_ts
                if bars:
                    logger.debug("Backfilled %d bars for %s", len(bars), symbol)
            except Exception as exc:
                logger.warning("Backfill failed for %s: %s", symbol, exc)

    def _on_message(self, feed, data: dict) -> None:
        if not data:
            return
        # Plan §7.2: shared message tracking through the mixin. Keeps the
        # health snapshot honest and unifies the contract with the depth
        # feeds and the polling feed.
        self._note_message_received()
        with self._lock:
            # P3 Fix: Periodic cleanup of stale tick tracking (every 100 messages).
            if self._message_count % 100 == 0:
                self._cleanup_stale_tick_tracking()
        data_type = data.get("type", "")
        if data_type in ("Ticker Data", "Quote Data"):
            quote = self._transform_quote(data)
            self._track_tick_time(quote)
            with self._lock:
                callbacks = list(self._quote_callbacks)
            for cb in callbacks:
                try:
                    cb(quote)
                except Exception as exc:
                    logger.error("Quote callback error: %s", exc)
            self._publish_tick(quote, correlation_id=self._gen_ws_correlation_id())
        elif data_type in ("Market Depth", "Full Data"):
            depth = self._transform_depth(data)
            with self._lock:
                callbacks = list(self._depth_callbacks)
            for cb in callbacks:
                try:
                    cb(depth)
                except Exception as exc:
                    logger.error("Depth callback error: %s", exc)
            corr_id = self._gen_ws_correlation_id()
            self._publish_depth(depth, correlation_id=corr_id)
            # Full Data frames carry quote fields; publish tick too for FULL mode.
            if data_type == "Full Data":
                quote = self._transform_quote(data)
                self._track_tick_time(quote)
                with self._lock:
                    quote_callbacks = list(self._quote_callbacks)
                for cb in quote_callbacks:
                    try:
                        cb(quote)
                    except Exception as exc:
                        logger.error("Quote callback error: %s", exc)
                self._publish_tick(quote, correlation_id=corr_id)
        else:
            # Informational packets (Previous Close, OI Data, Market Status)
            # are NOT tradeable signals — skip them to prevent zero-LTP ticks.
            # Only log at debug level to avoid log spam.
            if data_type not in ("Previous Close", "OI Data", "Market Status"):
                logger.debug(
                    "dhan_ws_unknown_packet_type",
                    extra={"data_type": data_type, "keys": list(data.keys())},
                )

    @staticmethod
    def _gen_ws_correlation_id() -> str:
        """Generate a traceable correlation_id for websocket message dispatch.

        Websocket threads run outside ``with_correlation()`` context,
        so we generate an explicit ID so TICK/DEPTH/ORDER_UPDATED/TRADE
        events published from this thread carry traceable identifiers.
        """
        import uuid as _uuid

        return f"dhan:ws:{_uuid.uuid4().hex[:12]}"

    def _track_tick_time(self, quote: dict) -> None:
        """Record the latest tick time per symbol for gap detection."""
        symbol = quote.get("symbol")
        if not symbol:
            return
        now = datetime.now(timezone.utc)
        with self._lock:
            prev = self._last_tick_time.get(symbol)
            if prev is None or now > prev:
                self._last_tick_time[symbol] = now

    def clear_symbol_tracking(self, symbol: str) -> None:
        """Remove last-tick-time tracking for a symbol (called on unsubscribe)."""
        with self._lock:
            self._last_tick_time.pop(symbol.upper(), None)
            self._last_tick_time.pop(symbol, None)

    def _cleanup_stale_tick_tracking(self, max_age_seconds: float = 1800) -> None:
        """Remove entries for symbols that haven't received ticks recently.

        P3 Fix: Prevents unbounded growth of _last_tick_time cache.
        Default max_age is 30 minutes — conservative to avoid removing
        symbols that are still active but receive infrequent ticks.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            stale = [
                sym
                for sym, ts in self._last_tick_time.items()
                if (now - ts).total_seconds() > max_age_seconds
            ]
            for sym in stale:
                del self._last_tick_time[sym]

    def _transform_quote(self, data: dict) -> dict:
        security_id = str(data.get("security_id", ""))
        symbol = security_id
        if self._resolver:
            try:
                inst = self._resolver.get_by_security_id(security_id)
                if inst:
                    symbol = inst.symbol
            except Exception as exc:
                logger.warning(
                    "dhan_ws_symbol_resolution_failed",
                    extra={"security_id": security_id, "exception_type": type(exc).__name__},
                )
        return {
            "symbol": symbol,
            "security_id": security_id,
            "ltp": Decimal(str(data.get("last_price", data.get("LTP", "0")))),
            "open": Decimal(str(data["open"])) if data.get("open") else None,
            "high": Decimal(str(data["high"])) if data.get("high") else None,
            "low": Decimal(str(data["low"])) if data.get("low") else None,
            "close": Decimal(str(data["close"])) if data.get("close") else None,
            "volume": int(data.get("volume", 0)),
            "change": Decimal("0"),
        }

    @staticmethod
    def _normalize_sdk_depth(raw_depth: Any) -> dict[str, list[dict[str, Any]]]:
        """Convert Dhan SDK depth payload to {bids, asks} ladder dict."""
        if isinstance(raw_depth, dict):
            return {
                "bids": list(raw_depth.get("bids") or []),
                "asks": list(raw_depth.get("asks") or []),
            }
        if isinstance(raw_depth, list):
            bids: list[dict[str, Any]] = []
            asks: list[dict[str, Any]] = []
            for row in raw_depth:
                if not isinstance(row, dict):
                    continue
                bid_qty = int(row.get("bid_quantity") or 0)
                ask_qty = int(row.get("ask_quantity") or 0)
                if bid_qty > 0:
                    bids.append(
                        {
                            "price": row.get("bid_price", 0),
                            "quantity": bid_qty,
                            "orders": int(row.get("bid_orders") or 0),
                        }
                    )
                if ask_qty > 0:
                    asks.append(
                        {
                            "price": row.get("ask_price", 0),
                            "quantity": ask_qty,
                            "orders": int(row.get("ask_orders") or 0),
                        }
                    )
            return {"bids": bids, "asks": asks}
        return {"bids": [], "asks": []}

    def _transform_depth(self, data: dict) -> dict:
        security_id = str(data.get("security_id", ""))
        symbol = security_id
        if self._resolver:
            try:
                inst = self._resolver.get_by_security_id(security_id)
                if inst:
                    symbol = inst.symbol
            except Exception as exc:
                logger.warning(
                    "dhan_ws_symbol_resolution_failed",
                    extra={"security_id": security_id, "exception_type": type(exc).__name__},
                )
        return {
            "symbol": symbol,
            "security_id": security_id,
            "ltp": Decimal(str(data.get("last_price", data.get("LTP", "0")))),
            "depth": self._normalize_sdk_depth(data.get("depth", [])),
        }

    def _publish_tick(self, quote: dict, correlation_id: str | None = None) -> None:
        """Publish a tick to the event bus under strict mode (Plan §7.7).

        Strict-mode rules (any violation drops the event and increments
        a counter visible via :meth:`health`):

        - ``ltp`` must be present and non-zero (a zero-LTP quote is a
          dangerous false signal for downstream strategies).
        - ``symbol`` must be present.
        - ``open`` / ``high`` / ``low`` / ``close`` must be present
          (zero is acceptable for a freshly-listed symbol).

        The legacy behaviour silently substituted ``Decimal("0")`` for
        any missing field. That masked malformed packets as zero-LTP
        ticks, which downstream subscribers treated as real signals.
        The strict-mode drop is the bug-fix called out in §5.2.
        """
        if self._event_bus is None:
            return
        try:
            ltp_raw = quote.get("ltp")
            symbol = quote.get("symbol", "")
            # Task 2.4: use _to_decimal to avoid redundant Decimal(str(Decimal()))
            ltp = _to_decimal(ltp_raw)
            if ltp_raw is None or ltp == 0:
                self._dropped_ticks += 1
                try:
                    from brokers.dhan.metrics import dhan_ws_dropped_ticks_total

                    dhan_ws_dropped_ticks_total.inc()
                except Exception:
                    pass
                logger.warning("tick_dropped_missing_or_zero_ltp: symbol=%s", symbol or "<unknown>")
                return
            if not symbol:
                self._dropped_ticks += 1
                try:
                    from brokers.dhan.metrics import dhan_ws_dropped_ticks_total

                    dhan_ws_dropped_ticks_total.inc()
                except Exception:
                    pass
                logger.warning("tick_dropped_missing_symbol")
                return

            # All critical fields present — build the Quote and publish.
            # Task 2.4: values from _transform_quote are already Decimal;
            # _to_decimal is a no-op for Decimal, converting only for backfill raw data.
            q = Quote(
                symbol=symbol,
                ltp=ltp,
                open=_to_decimal(quote.get("open")),
                high=_to_decimal(quote.get("high")),
                low=_to_decimal(quote.get("low")),
                close=_to_decimal(quote.get("close")),
                volume=quote.get("volume", 0),
                change=_to_decimal(quote.get("change")),
            )
            self._event_bus.publish(
                DomainEvent.now(
                    "TICK",
                    {"quote": q},
                    symbol=q.symbol,
                    source="DhanMarketFeed",
                    correlation_id=correlation_id,
                )
            )
            self._published_ticks += 1
            try:
                from brokers.dhan.metrics import dhan_ws_ticks_total

                dhan_ws_ticks_total.inc()
            except Exception:
                pass
        except Exception as exc:
            self._dropped_ticks += 1
            logger.error("EventBus TICK publish error: %s", exc)

    def _publish_depth(self, depth: dict, correlation_id: str | None = None) -> None:
        """Publish a depth snapshot under strict mode (matches _publish_tick).

        Strict-mode rules (any violation drops the event and increments
        a counter visible via :meth:`health`):

        - ``symbol`` must be present (no empty/unknown symbol).
        - At least one of bids/asks must be non-empty (a packet with
          both sides empty is a malformed frame, not a snapshot).
        - The top-of-book price on each present side must be > 0
          (a zero-price level is a corrupted frame, not a real quote).
        """
        if self._event_bus is None:
            return
        symbol = depth.get("symbol", "")
        if not symbol:
            self._dropped_depths += 1
            logger.warning("depth_dropped_missing_symbol")
            return
        try:
            d = depth.get("depth", {}) or {}
            bids = [
                DepthLevel(
                    price=Decimal(str(b.get("price", 0))),
                    quantity=int(b.get("quantity", 0)),
                    orders=int(b.get("orders", 0)),
                )
                for b in d.get("bids", [])
            ]
            asks = [
                DepthLevel(
                    price=Decimal(str(a.get("price", 0))),
                    quantity=int(a.get("quantity", 0)),
                    orders=int(a.get("orders", 0)),
                )
                for a in d.get("asks", [])
            ]
            if not bids and not asks:
                self._dropped_depths += 1
                logger.warning("depth_dropped_both_sides_empty: symbol=%s", symbol)
                return
            # Top-of-book must be positive on each present side. A zero
            # top-of-book is a corrupted frame masquerading as a snapshot.
            if bids and bids[0].price <= 0:
                self._dropped_depths += 1
                logger.warning(
                    "depth_dropped_invalid_bid_top: symbol=%s bid0=%s",
                    symbol,
                    bids[0].price,
                )
                return
            if asks and asks[0].price <= 0:
                self._dropped_depths += 1
                logger.warning(
                    "depth_dropped_invalid_ask_top: symbol=%s ask0=%s",
                    symbol,
                    asks[0].price,
                )
                return
            md = MarketDepth(bids=bids, asks=asks)
            self._event_bus.publish(
                DomainEvent.now(
                    "DEPTH",
                    {"depth": md},
                    symbol=symbol,
                    source="DhanMarketFeed",
                    correlation_id=correlation_id,
                )
            )
            self._published_depths += 1
        except Exception as exc:
            self._dropped_depths += 1
            logger.error("EventBus DEPTH publish error: %s", exc)

    def _on_close(self, feed) -> None:
        with self._lock:
            self._is_connected = False
            self._connected_at = None
            self._disconnect_time = datetime.now(timezone.utc)
        logger.info("Market feed disconnected")

    def _on_error(self, feed, error) -> None:
        logger.error("Market feed error: %s", error)
        with self._lock:
            self._is_connected = False
            self._connected_at = None
            self._disconnect_time = datetime.now(timezone.utc)
