"""Central subscription engine — single source of truth for market/order stream state.

Owns instrument ref-counting, callback registration, and feed lifecycle.
All consumers must route subscribe/unsubscribe through here.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


class SubscriptionEngine:
    """Instrument-centric subscription ref-counting for one Dhan account."""

    def __init__(self, connection: Any) -> None:
        self._conn = connection
        self._lock = threading.RLock()
        self._instrument_refs: dict[tuple[str, str], int] = {}
        self._instrument_modes: dict[tuple[str, str], str] = {}
        self._market_callbacks: dict[tuple[str, str], list[Any]] = {}
        self._market_wrappers: dict[tuple[str, str], list[tuple[Any, Any]]] = {}
        self._order_callbacks: list[Any] = []
        self._order_wrappers: list[tuple[Any, Any]] = []

    # ------------------------------------------------------------------
    # Market subscriptions
    # ------------------------------------------------------------------

    def subscribe_market(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to market data for symbol; returns the shared feed."""
        from brokers.domain.symbols import make_position_key

        inst = self._conn.instruments.resolve(symbol, exchange)
        sid = int(inst.security_id)
        key = make_position_key(symbol, exchange)

        with self._lock:
            feed = self._ensure_market_feed()
            feed.subscribe([(inst.exchange_segment, sid, mode)])
            self._instrument_modes[key] = mode
            self._instrument_refs[key] = self._instrument_refs.get(key, 0) + 1

            if on_tick is not None:
                existing = self._market_callbacks.get(key, [])
                if on_tick not in existing:

                    def _wrap(
                        data: dict, _sym: str = symbol, _cb: Any = on_tick
                    ) -> None:
                        try:
                            from brokers.domain.entities import Quote

                            q = Quote(
                                symbol=data.get("symbol", _sym),
                                ltp=data.get("ltp", Decimal("0")),
                                open=data.get("open", Decimal("0")),
                                high=data.get("high", Decimal("0")),
                                low=data.get("low", Decimal("0")),
                                close=data.get("close", Decimal("0")),
                                volume=int(data.get("volume", 0)),
                                change=data.get("change", Decimal("0")),
                            )
                            _cb(q)
                        except Exception as exc:
                            logger.warning(
                                "tick_quote_wrap_failed",
                                extra={"symbol": _sym, "error": str(exc)},
                            )
                            _cb(data)

                    feed.on_depth(
                        _wrap
                    )  # Note: using on_depth for legacy compatibility
                    self._market_callbacks.setdefault(key, []).append(on_tick)
                    self._market_wrappers.setdefault(key, []).append((on_tick, _wrap))

            if not feed.is_connected:
                feed.start()

            return feed

    def unsubscribe_market(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_tick: Any | None = None,
    ) -> None:
        """Remove a market callback; SDK unsubscribe when last ref released."""
        from brokers.domain.symbols import make_position_key

        key = make_position_key(symbol, exchange)

        with self._lock:
            callbacks = self._market_callbacks.get(key, [])
            wrappers = self._market_wrappers.get(key, [])
            feed = self._conn.streaming  # Use streaming as market feed

            if on_tick is not None:
                with contextlib.suppress(ValueError):
                    callbacks.remove(on_tick)
                to_remove = [(cb, wrap) for cb, wrap in wrappers if cb is on_tick]
                for cb, wrap in to_remove:
                    with contextlib.suppress(ValueError):
                        wrappers.remove((cb, wrap))
                    if feed is not None:
                        feed.unsubscribe(symbol, exchange)
            else:
                if feed is not None:
                    for _cb, wrap in list(wrappers):
                        feed.unsubscribe(symbol, exchange)
                callbacks.clear()
                wrappers.clear()

            if not callbacks:
                self._market_callbacks.pop(key, None)
                self._market_wrappers.pop(key, None)

            refs = self._instrument_refs.get(key, 0)
            if refs <= 1:
                self._instrument_refs.pop(key, None)
            else:
                self._instrument_refs[key] = refs - 1

    # ------------------------------------------------------------------
    # Order stream subscriptions
    # ------------------------------------------------------------------

    def subscribe_order(self, on_order: Any | None = None) -> Any:
        """Subscribe to account-wide order updates; returns the shared stream."""
        with self._lock:
            stream = self._ensure_order_stream()
            if on_order is not None:
                existing = [cb for cb, _ in self._order_wrappers]
                if on_order not in existing:

                    def _wrap(data: dict, _cb: Any = on_order) -> None:
                        _cb(data)

                    stream.on_order_update(_wrap)
                    self._order_callbacks.append(on_order)
                    self._order_wrappers.append((on_order, _wrap))

            if not stream.is_connected:
                stream.start()
            return stream

    def unsubscribe_order(self, on_order: Any | None = None) -> None:
        """Remove an order-update callback."""
        stream = self._conn.order_stream
        if stream is None:
            return

        if on_order is not None:
            to_remove = [
                (cb, wrap) for cb, wrap in self._order_wrappers if cb is on_order
            ]
            for cb, wrap in to_remove:
                with contextlib.suppress(ValueError):
                    self._order_wrappers.remove((cb, wrap))
                    self._order_callbacks.remove(cb)
                stream.off_order_update(wrap)
        else:
            for _cb, wrap in list(self._order_wrappers):
                stream.off_order_update(wrap)
            self._order_wrappers.clear()
            self._order_callbacks.clear()

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def subscription_count(self) -> int:
        with self._lock:
            return len(self._instrument_refs)

    def callback_count(self) -> int:
        with self._lock:
            market_cbs = sum(len(v) for v in self._market_callbacks.values())
            return market_cbs + len(self._order_callbacks)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_market_feed(self) -> Any:
        feed = getattr(self._conn, "streaming", None)
        if feed is None:
            # Create feed via lifecycle if available
            feed = self._conn.streaming
        return feed

    def _ensure_order_stream(self) -> Any:
        stream = getattr(self._conn, "order_stream", None)
        if stream is None:
            stream = self._conn.order_stream
        return stream
