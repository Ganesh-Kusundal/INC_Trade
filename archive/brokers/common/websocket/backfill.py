"""BackfillCoordinator — broker-agnostic gap-fill logic for WebSocket reconnections.

Both DhanMarketFeed and UpstoxMarketDataV3Multiplexer implemented the same
pattern independently: track ``_last_tick_time`` per instrument, record
``_disconnect_time`` on connection loss, then call a ``backfill_callback``
on reconnect to fetch missed bars and publish them as synthetic ticks.

This class centralises that pattern so neither adapter needs to reimplement it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)


SymbolOrList = list[str] | str
"""A single symbol string, or a list of symbol strings.

Dhan backfill callbacks accept a single symbol ``str`` per invocation
while Upstox callbacks accept ``list[str]``.  The coordinator normalises
both forms internally — if a single string is passed, it wraps it in a
list before forwarding to the callback so the callback always receives
``list[str]``.
"""


class BackfillProvider(Protocol):
    """Callable that fetches missed data for a gap period.

    Both Dhan and Upstox REST APIs support fetching historical bars
    for a symbol/instrument within a time window.

    The ``symbols`` parameter accepts ``list[str] | str`` so the same
    protocol can be used with Dhan-style callbacks (single symbol per
    call) and Upstox-style callbacks (list of instruments per call).
    """

    def __call__(
        self,
        symbols: SymbolOrList,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch bars for *symbols* in the half-open interval [from_dt, to_dt).

        Returns a list of dicts, each with at minimum ``symbol`` and
        OHLCV fields.
        """
        ...


class BackfillCoordinator:
    """Tracks per-instrument tick times and triggers gap-fill on reconnect.

    Usage
    -----
        backfill = BackfillCoordinator(backfill_callback=my_fetch_fn)

        # On every tick:
        backfill.record_tick(instrument_key)

        # On disconnect:
        backfill.record_disconnect()

        # On reconnect:
        backfill.fill_gap(subscribed_instruments)
    """

    def __init__(
        self,
        backfill_callback: BackfillProvider | None = None,
        min_gap_seconds: float = 5.0,
        outside_market_hours_check: Callable[[datetime, datetime], bool] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        backfill_callback : BackfillProvider, optional
            If provided, invoked on ``fill_gap()`` to fetch missed bars.
        min_gap_seconds : float
            Minimum disconnect duration to trigger backfill (default 5s).
        outside_market_hours_check : callable, optional
            ``(disconnect_time, now) -> bool`` that returns ``True`` if the
            gap falls entirely outside market hours (no backfill needed).
        """
        self._callback = backfill_callback
        self._min_gap = float(min_gap_seconds)
        self._outside_check = outside_market_hours_check
        self._last_tick_time: dict[str, datetime] = {}
        self._disconnect_time: datetime | None = None

    # ── Tick tracking ──────────────────────────────────────────────────

    def record_tick(self, instrument_key: str, timestamp: datetime | None = None) -> None:
        """Record a tick time for *instrument_key*.

        Only updates if *timestamp* is newer than the previously
        recorded time for that key.
        """
        ts = timestamp or datetime.now(timezone.utc)
        prev = self._last_tick_time.get(instrument_key)
        if prev is None or ts > prev:
            self._last_tick_time[instrument_key] = ts

    def clear_tracking(self, instrument_key: str) -> None:
        """Remove tick tracking for *instrument_key* (called on unsubscribe)."""
        self._last_tick_time.pop(instrument_key, None)

    def clear_all(self) -> None:
        """Clear all tick tracking state."""
        self._last_tick_time.clear()

    # ── Disconnect / reconnect lifecycle ───────────────────────────────

    def record_disconnect(self) -> None:
        """Record the current time as the disconnect moment."""
        self._disconnect_time = datetime.now(timezone.utc)

    def fill_gap(
        self,
        subscribed_keys: list[str] | None = None,
    ) -> list[dict[str, Any]] | None:
        """If a gap exists, invoke the backfill callback and return bars.

        Parameters
        ----------
        subscribed_keys : list[str], optional
            Keys to backfill. If omitted, uses keys from tick tracking.

        Returns
        -------
        list[dict] | None
            The bars returned by the backfill callback, or ``None`` if
            no gap-fill was needed.
        """
        if self._callback is None:
            return None

        disconnect_time = self._disconnect_time
        if disconnect_time is None:
            return None
        now = datetime.now(timezone.utc)
        self._disconnect_time = None

        # Skip if disconnect was too brief to matter
        gap_seconds = (now - disconnect_time).total_seconds()
        if gap_seconds < self._min_gap:
            logger.debug(
                "backfill_skipped_gap_too_small",
                extra={"gap_seconds": round(gap_seconds, 1), "min_gap": self._min_gap},
            )
            return None

        # Skip if connector was closed at or after now (clock skew guard)
        if disconnect_time >= now:
            return None

        # Skip if gap is entirely outside market hours
        if self._outside_check is not None and self._outside_check(disconnect_time, now):
            logger.debug(
                "backfill_skipped_outside_market_hours",
                extra={"disconnect": disconnect_time.isoformat(), "now": now.isoformat()},
            )
            return None

        # Determine which instruments to backfill
        instruments = subscribed_keys or list(self._last_tick_time.keys())
        if not instruments:
            return None

        logger.info(
            "backfilling %d instruments for gap %s → %s (%.1fs)",
            len(instruments),
            disconnect_time.isoformat(),
            now.isoformat(),
            gap_seconds,
        )

        try:
            bars = self._callback(instruments, disconnect_time, now)
        except Exception as exc:
            logger.warning("backfill_callback_failed: %s", exc)
            return None

        if bars:
            logger.debug("backfilled %d bars", len(bars))
        return bars

    # ── Cleanup ────────────────────────────────────────────────────────

    def cleanup_stale(self, max_age_seconds: float = 1800.0) -> None:
        """Remove entries for instruments not seen within *max_age_seconds*.

        Prevents unbounded growth of the tick-tracking cache.
        """
        now = datetime.now(timezone.utc)
        stale = [
            key
            for key, ts in self._last_tick_time.items()
            if (now - ts).total_seconds() > max_age_seconds
        ]
        for key in stale:
            del self._last_tick_time[key]
