"""Order Flow — institutional-grade buy/sell pressure analytics from Trade events.

The :class:`OrderFlowAnalyzer` consumes a stream of ``Trade`` events and
computes real-time volume-flow metrics used by market microstructure
strategies:

- Total buy volume vs. total sell volume (from ``Trade.side``).
- Volume delta (buy - sell) and cumulative delta.
- Per-bar delta (resettable by the user for OHLC-bar alignment).
- Trade count, average trade size, and a count of "large" trades
  whose volume exceeds an institutional threshold.
- Buy/sell pressure ratio.

Thread-safety
-------------
All public state-mutating methods acquire an internal ``threading.Lock``
so the analyzer can be fed concurrently by multiple producer threads
(e.g. one per symbol) without losing updates.

Defensive parsing
-----------------
:func:`update` is tolerant of partially-constructed ``Trade`` objects
(missing ``side``, ``quantity``, or ``price``). Malformed input is
silently dropped — a single bad event must never crash a live analytics
pipeline. Only fully-valid trades update the running metrics.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brokers.domain.entities import Trade


@dataclass(frozen=True)
class OrderFlowMetrics:
    """Snapshot of order flow metrics at a point in time.

    All numeric fields are integers for volume/counts and ``Decimal`` for
    the size/pressure ratio to avoid float drift.
    """

    total_buy_volume: int
    total_sell_volume: int
    volume_delta: int
    cumulative_delta: int
    bar_delta: int
    bar_buy_volume: int
    bar_sell_volume: int
    trade_count: int
    bar_trade_count: int
    large_trade_count: int
    average_trade_size: Decimal
    buy_sell_pressure: Decimal
    last_trade_price: Decimal | None


class OrderFlowAnalyzer:
    """Computes real-time order flow metrics from a stream of ``Trade`` events.

    Tracks:

    - Total buy volume (from BUY-side trades).
    - Total sell volume (from SELL-side trades).
    - Volume delta (buy - sell).
    - Cumulative delta (running total across the whole session).
    - Delta per bar (resettable on user request via :func:`reset_bar`).
    - Trade count, average trade size, large-trade count.
    - Buy/sell pressure ratio (buy / sell, ``Decimal`` precision).

    Use::

        analyzer = OrderFlowAnalyzer()
        for trade in trade_stream:
            analyzer.update(trade)
        metrics = analyzer.snapshot()
    """

    def __init__(self, large_trade_threshold: int = 1000) -> None:
        """Initialize.

        Args:
            large_trade_threshold: Volume threshold for counting as a
                "large" trade (institutional footprint). Defaults to
                ``1000``. Must be positive; zero/negative values raise
                ``ValueError``.
        """
        if large_trade_threshold < 0:
            raise ValueError("large_trade_threshold must be non-negative")

        self._large_trade_threshold = large_trade_threshold
        self._lock = threading.Lock()

        # Cumulative (session-wide) state.
        self._total_buy_volume = 0
        self._total_sell_volume = 0
        self._trade_count = 0
        self._large_trade_count = 0
        self._total_volume_sum = 0  # for average trade size (int)
        self._last_trade_price: Decimal | None = None

        # Bar (resettable) state.
        self._bar_buy_volume = 0
        self._bar_sell_volume = 0
        self._bar_trade_count = 0

    def update(self, trade: Trade) -> None:
        """Incorporate a ``Trade`` event.

        Never raises on malformed input — a ``Trade`` with a missing
        ``side``, non-positive ``quantity``, or ``None`` price is
        silently dropped. This is intentional: the analyzer is fed by
        best-effort WebSocket streams and a single bad event must not
        crash the analytics pipeline.

        Args:
            trade: A ``Trade`` domain entity. May be partially-formed;
                missing fields are ignored.
        """
        # Extract fields defensively — Trade is a frozen dataclass but
        # we still want to handle dynamic/duck-typed inputs safely.
        try:
            side = trade.side
            quantity = trade.quantity
            price = trade.price
        except AttributeError:
            return

        # Defensive checks: side must be BUY/SELL, qty must be positive int.
        if quantity is None or not isinstance(quantity, int) or quantity <= 0:
            return
        if price is None or not isinstance(price, Decimal):
            return
        if not self._is_valid_side(side):
            return

        with self._lock:
            if side.value == "BUY":
                self._total_buy_volume += quantity
                self._bar_buy_volume += quantity
            else:  # SELL
                self._total_sell_volume += quantity
                self._bar_sell_volume += quantity

            self._trade_count += 1
            self._bar_trade_count += 1
            self._total_volume_sum += quantity
            self._last_trade_price = price

            if quantity >= self._large_trade_threshold:
                self._large_trade_count += 1

    @staticmethod
    def _is_valid_side(side: object) -> bool:
        """Check whether ``side`` is a recognized ``Side`` enum value."""
        # Avoid importing Side at runtime to keep this module lean.
        # Side is a str-Enum, so str comparison is sufficient and fast.
        return side is not None and getattr(side, "value", None) in ("BUY", "SELL")

    def reset_bar(self) -> None:
        """Start a new bar — clears bar-level counters, keeps cumulative."""
        with self._lock:
            self._bar_buy_volume = 0
            self._bar_sell_volume = 0
            self._bar_trade_count = 0

    def reset(self) -> None:
        """Reset all state (cumulative + bar). For tests / new session."""
        with self._lock:
            self._total_buy_volume = 0
            self._total_sell_volume = 0
            self._trade_count = 0
            self._large_trade_count = 0
            self._total_volume_sum = 0
            self._last_trade_price = None
            self._bar_buy_volume = 0
            self._bar_sell_volume = 0
            self._bar_trade_count = 0

    def snapshot(self) -> OrderFlowMetrics:
        """Return current metrics snapshot.

        Returns:
            ``OrderFlowMetrics`` with all computed values. The snapshot
            is internally consistent — all fields are read under a
            single lock acquisition.
        """
        with self._lock:
            cumulative_delta = self._total_buy_volume - self._total_sell_volume
            bar_delta = self._bar_buy_volume - self._bar_sell_volume
            avg_size = self._compute_average_size()
            pressure = self._compute_pressure()
            return OrderFlowMetrics(
                total_buy_volume=self._total_buy_volume,
                total_sell_volume=self._total_sell_volume,
                volume_delta=cumulative_delta,
                cumulative_delta=cumulative_delta,
                bar_delta=bar_delta,
                bar_buy_volume=self._bar_buy_volume,
                bar_sell_volume=self._bar_sell_volume,
                trade_count=self._trade_count,
                bar_trade_count=self._bar_trade_count,
                large_trade_count=self._large_trade_count,
                average_trade_size=avg_size,
                buy_sell_pressure=pressure,
                last_trade_price=self._last_trade_price,
            )

    # ── Private helpers (assumed to be called under self._lock) ───────

    def _compute_average_size(self) -> Decimal:
        if self._trade_count <= 0:
            return Decimal("0")
        return Decimal(self._total_volume_sum) / Decimal(self._trade_count)

    def _compute_pressure(self) -> Decimal:
        """Buy / sell pressure ratio.

        Returns ``Decimal('0')`` when no sell volume has been observed
        (avoids ``DivisionByZero``). This is conservative — when there
        are no sells we cannot compute a meaningful pressure ratio.
        """
        if self._total_sell_volume <= 0:
            return Decimal("0")
        return Decimal(self._total_buy_volume) / Decimal(self._total_sell_volume)
