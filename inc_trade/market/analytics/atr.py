"""ATR — Average True Range calculator.

True Range for a candle::

    TR = max(high - low, |high - prev_close|, |low - prev_close|)

ATR is a simple moving average of True Range over ``period`` candles.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inc_trade.domain.entities import Candle


class ATRCalculator:
    """Average True Range over a configurable period.

    Args:
        period: Number of candles in the moving average. Default 14.
    """

    def __init__(self, period: int = 14) -> None:
        if period <= 0:
            raise ValueError("period must be positive")
        self._period = period
        self._trs: deque[Decimal] = deque(maxlen=period)
        self._prev_close: Decimal | None = None

    def update(self, candle: Candle) -> None:
        """Incorporate a new candle.

        Args:
            candle: ``Candle`` with high, low, close.
        """
        high_low = candle.high - candle.low
        if self._prev_close is None:
            tr = high_low
        else:
            tr = max(
                high_low,
                abs(candle.high - self._prev_close),
                abs(candle.low - self._prev_close),
            )
        self._trs.append(tr)
        self._prev_close = candle.close

    @property
    def value(self) -> Decimal:
        """Current ATR. ``Decimal('0')`` until the period is filled."""
        if not self._trs:
            return Decimal("0")
        return sum(self._trs) / Decimal(len(self._trs))

    @property
    def is_ready(self) -> bool:
        """True once the period has been filled."""
        return len(self._trs) >= self._period

    def reset(self) -> None:
        """Clear all state."""
        self._trs.clear()
        self._prev_close = None
