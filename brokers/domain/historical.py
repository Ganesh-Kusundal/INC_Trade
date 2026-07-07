"""Normalized historical bar models.

``HistoricalBar`` and ``HistoricalSeries`` are the canonical output types for
all historical data operations.  ``InstrumentRef`` is deleted — the rich
``Instrument`` class is used directly (or symbol/exchange strings for
provider-internal calls).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class BarLabelConvention(str, Enum):
    """Describes which edge of the bar interval the timestamp refers to.

    LEFT   — timestamp is the bar *open* time (most common, e.g. Upstox).
    RIGHT  — timestamp is the bar *close* time (some broker responses).
    CENTER — timestamp is the midpoint (unusual; flag explicitly).
    """

    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CENTER = "CENTER"


@dataclass(frozen=True, slots=True)
class HistoricalBar:
    """A single normalized OHLCV bar.

    Fields
    ------
    symbol     — the instrument symbol this bar belongs to.
    exchange   — exchange string, e.g. ``"NSE"``.
    timeframe  — candle interval, e.g. ``"1m"``, ``"5m"``, ``"1D"``.
    event_time — bar open time (UTC, timezone-aware).
    open / high / low / close / volume — OHLCV data.
    open_interest — optional OI for derivatives.
    is_partial   — True for the last bar in a live response.
    label_convention — whether the raw broker timestamp was LEFT or RIGHT.
    """

    symbol: str
    exchange: str
    timeframe: str
    event_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    open_interest: int = 0
    is_partial: bool = False
    label_convention: BarLabelConvention = BarLabelConvention.LEFT


@dataclass(frozen=True, slots=True)
class DateRange:
    """An inclusive date range."""

    start: date
    end: date

    def days(self) -> int:
        return (self.end - self.start).days + 1

    def __contains__(self, d: date) -> bool:
        return self.start <= d <= self.end


@dataclass(frozen=True, slots=True)
class Gap:
    """A gap within a ``HistoricalSeries`` — a date range where bars are missing.

    reason may be: ``"broker_error"``, ``"quota_exhausted"``, ``"no_data"``
    (holidays / non-trading days), ``"range_exceeded"``.
    """

    start: date
    end: date
    reason: str = "no_data"


@dataclass
class HistoricalSeries:
    """Normalized collection of historical bars for a single instrument.

    bars     — sequence of bars ordered by ``event_time`` ascending.
    coverage — date range that was *requested* (not necessarily fully filled).
    gaps     — explicit gaps within the coverage range.
    """

    bars: list[HistoricalBar]
    coverage: DateRange
    symbol: str
    exchange: str
    timeframe: str
    gaps: list[Gap] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True when there are no registered gaps."""
        return len(self.gaps) == 0

    @property
    def bar_count(self) -> int:
        return len(self.bars)


__all__ = [
    "BarLabelConvention",
    "DateRange",
    "Gap",
    "HistoricalBar",
    "HistoricalSeries",
]
