"""Scan criteria — pluggable predicate for matching instruments.

Each criterion is a small object that implements the ``ScanCriteria``
protocol. Criteria are pure logic: they read market data and return a
boolean. They are decoupled from scanner scheduling and result
aggregation.

Architecture rules:
- criteria import only from ``brokers.domain`` and ``brokers.market``
- criteria must not import adapters, trading, infrastructure, or services
"""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ScanCriteria(Protocol):
    """Predicate protocol — does this instrument match?

    Implementations read from ``MarketDataContext`` to evaluate the
    instrument. They must be side-effect free.
    """

    def matches(self, instrument: Any, market_data: Any) -> bool:
        """Return True if the instrument satisfies this criterion."""
        ...

    def describe(self) -> str:
        """Human-readable description of this criterion."""
        ...


class PriceAbove:
    """Match when LTP >= threshold."""

    def __init__(self, threshold: Decimal) -> None:
        self._threshold = threshold

    def matches(self, instrument: Any, market_data: Any) -> bool:
        try:
            quote = market_data.quote(instrument.symbol, instrument.exchange)
            return quote.ltp >= self._threshold
        except Exception:
            return False

    def describe(self) -> str:
        return f"PriceAbove({self._threshold})"


class PriceBelow:
    """Match when LTP <= threshold."""

    def __init__(self, threshold: Decimal) -> None:
        self._threshold = threshold

    def matches(self, instrument: Any, market_data: Any) -> bool:
        try:
            quote = market_data.quote(instrument.symbol, instrument.exchange)
            return quote.ltp <= self._threshold
        except Exception:
            return False

    def describe(self) -> str:
        return f"PriceBelow({self._threshold})"


class VolumeSpike:
    """Match when current volume exceeds multiplier x reference volume.

    Reference volume is taken from the instrument's cached QuoteState;
    if unavailable, the criterion conservatively does not match.
    """

    def __init__(self, multiplier: Decimal = Decimal("2")) -> None:
        self._multiplier = multiplier

    def matches(self, instrument: Any, market_data: Any) -> bool:
        try:
            state = market_data.quote_state(instrument.symbol, instrument.exchange)
        except Exception:
            return False
        if state is None or state.volume <= 0:
            return False
        # Treat open volume as the baseline; spike means current > 2x open baseline
        baseline = state.open if state.open > 0 else Decimal("0")
        if baseline <= 0:
            return False
        # current / baseline >= multiplier  (re-arrange: current >= multiplier * baseline)
        return Decimal(state.volume) >= self._multiplier * baseline

    def describe(self) -> str:
        return f"VolumeSpike(x{self._multiplier})"


class CrossingMA:
    """Match when LTP crosses above a simple moving average from candles.

    Requires historical data access through ``MarketDataContext``.
    """

    def __init__(self, period: int = 20) -> None:
        self._period = period

    def matches(self, instrument: Any, market_data: Any) -> bool:
        from datetime import datetime, timedelta

        try:
            end = datetime.now(UTC)
            start = end - timedelta(days=max(self._period * 2, 5))
            candles = market_data.ohlcv(
                symbol=instrument.symbol,
                exchange=instrument.exchange,
                start_time=start,
                end_time=end,
                resolution="1D",
            )
        except Exception:
            return False
        if len(candles) < self._period:
            return False
        recent = candles[-self._period :]
        closes = [c.close for c in recent]
        sma = sum(closes) / Decimal(len(closes))
        try:
            quote = market_data.quote(instrument.symbol, instrument.exchange)
        except Exception:
            return False
        return quote.ltp > sma

    def describe(self) -> str:
        return f"CrossingMA(period={self._period})"
