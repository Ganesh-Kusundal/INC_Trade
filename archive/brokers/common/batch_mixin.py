"""BatchFetchMixin — shared parallel-fetch implementation for gateways."""

from __future__ import annotations

import logging
from decimal import Decimal

import pandas as pd

from brokers.common.batch_executor import batch_execute
from domain import Quote
from domain.constants import BATCH_MAX_WORKERS

logger = logging.getLogger(__name__)


class BatchFetchMixin:
    """Mixin providing parallel batch-fetch methods via :func:`batch_execute`."""

    _batch_max_workers: int = BATCH_MAX_WORKERS

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        results: dict[str, Decimal] = {}
        raw = batch_execute(
            symbols,
            lambda sym: self.ltp(sym, exchange),  # type: ignore[attr-defined]
            max_workers=self._batch_max_workers,
        )
        for sym in symbols:
            if sym in raw:
                results[sym] = raw[sym]
            else:
                results[sym] = Decimal("0")
        return results

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        return batch_execute(
            symbols,
            lambda sym: self.quote(sym, exchange),  # type: ignore[attr-defined]
            max_workers=self._batch_max_workers,
        )

    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """Return historical data for multiple symbols as a single concatenated DataFrame.

        Each row includes a 'symbol' column for identification.
        """
        per_symbol = batch_execute(
            symbols,
            lambda sym: self.history(sym, exchange, timeframe, lookback_days),  # type: ignore[attr-defined]
            max_workers=self._batch_max_workers,
        )

        frames = []
        for sym in symbols:
            if sym in per_symbol and not per_symbol[sym].empty:
                df = per_symbol[sym].copy()
                df["symbol"] = sym
                frames.append(df)

        if not frames:
            return pd.DataFrame()

        return pd.concat(frames, ignore_index=True)
