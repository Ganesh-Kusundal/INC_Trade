"""Tick source — converts historical candles to synthetic ticks.

Each candle becomes a sequence of quotes. The close price is the
authoritative value; synthetic intra-candle variation is added for
realism but is not used for analytics.
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from inc_trade.domain.entities import Quote

if TYPE_CHECKING:
    from collections.abc import Generator
    from datetime import datetime  # noqa: F401

    from inc_trade.domain.entities import Candle


class TickSource:
    """Generate tick-by-tick quotes from candle history.

    Args:
        jitter_bps: Basis-points of price jitter for intra-candle ticks.
            Default 5 (i.e., 0.05 %).
        ticks_per_candle: How many synthetic ticks to emit per candle.
            Default 1 (just the close).
    """

    def __init__(
        self,
        jitter_bps: int = 5,
        ticks_per_candle: int = 1,
        seed: int | None = None,
    ) -> None:
        self._jitter_bps = jitter_bps
        self._ticks_per_candle = max(1, ticks_per_candle)
        self._rng = random.Random(seed)

    def generate(
        self,
        symbol: str,
        exchange: str,
        candles: list[Candle],
    ) -> Generator[Quote, None, None]:
        """Yield Quote objects for each candle.

        Args:
            symbol: Instrument symbol (for the Quote entity).
            exchange: Exchange code.
            candles: List of ``Candle`` to convert.

        Yields:
            ``Quote`` entities with close price (plus optional jitter).
        """
        for candle in candles:
            for i in range(self._ticks_per_candle):
                price = self._apply_jitter(candle.close)
                ts = candle.timestamp + timedelta(milliseconds=i)
                yield Quote(
                    symbol=symbol,
                    exchange=exchange,
                    ltp=price,
                    volume=candle.volume,
                    timestamp=ts,
                )

    def _apply_jitter(self, price: Decimal) -> Decimal:
        if self._jitter_bps <= 0:
            return price
        jitter = Decimal(self._rng.randint(-self._jitter_bps, self._jitter_bps))
        return price * (Decimal("1") + jitter / Decimal("10000"))
