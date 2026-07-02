"""Pandas-dependent market data adapters.

These adapters convert pandas DataFrames to domain ``HistoricalSeries``
objects.  They live in the infrastructure layer (not the domain port)
so the domain protocol stays free of pandas.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from domain.historical import (
    DateRange,
    HistoricalBar,
    HistoricalSeries,
    InstrumentRef,
)
from domain.provenance import DataProvenance
from domain.symbols import make_instrument_key


def _df_to_historical_series(
    df: Any,
    symbol: str,
    exchange: str,
    interval: str,
    start: date,
    end: date,
) -> HistoricalSeries | None:
    """Convert a pandas DataFrame of OHLCV bars to a HistoricalSeries."""
    import pandas as pd

    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return None

    instrument = InstrumentRef(symbol=symbol, exchange=exchange)
    provenance = DataProvenance.now(broker_id="adapter", request_id="adapter-history")

    bars: list[HistoricalBar] = []
    for _idx, row in df.iterrows():
        ts_raw = row.get("date", row.name if hasattr(row, "name") else None)
        if ts_raw is None:
            event_time = datetime.now(timezone.utc)
        elif isinstance(ts_raw, datetime):
            event_time = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
        elif isinstance(ts_raw, date):
            event_time = datetime(ts_raw.year, ts_raw.month, ts_raw.day, tzinfo=timezone.utc)
        else:
            event_time = datetime.now(timezone.utc)

        bars.append(
            HistoricalBar(
                instrument=instrument,
                timeframe=interval,
                event_time=event_time,
                open=Decimal(str(row.get("open", row.get("close", 0)))),
                high=Decimal(str(row.get("high", row.get("close", 0)))),
                low=Decimal(str(row.get("low", row.get("close", 0)))),
                close=Decimal(str(row.get("close", 0))),
                volume=int(row.get("volume", 0)),
                provenance=provenance,
            )
        )

    if not bars:
        return None

    return HistoricalSeries(
        bars=bars,
        coverage=DateRange(start=start, end=end),
        instrument=instrument,
        timeframe=interval,
    )


class GatewayMarketDataAdapter:
    """Wraps a broker gateway ``history`` method as :class:`MarketDataPort`."""

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        interval: str = "1m",
        exchange: str = "NSE",
    ) -> HistoricalSeries | None:
        history_fn = getattr(self._gateway, "history", None)
        if history_fn is None:
            return None
        df = history_fn(symbol, start, end, interval=interval, exchange=exchange)
        return _df_to_historical_series(df, symbol, exchange, interval, start, end)


class DataFrameMarketDataAdapter:
    """Serves pre-loaded OHLCV for replay/backtest parity tests."""

    def __init__(self, frames: dict[tuple[str, str], Any]) -> None:
        self._frames = frames

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        interval: str = "1m",
        exchange: str = "NSE",
    ) -> HistoricalSeries | None:
        import pandas as pd

        key = make_instrument_key(symbol, exchange)
        df = self._frames.get(key)
        if df is None:
            return None
        if isinstance(df, pd.DataFrame) and "date" in df.columns:
            mask = (df["date"] >= start) & (df["date"] <= end)
            df = df.loc[mask].copy()
        elif isinstance(df, pd.DataFrame):
            df = df.copy()
        return _df_to_historical_series(df, symbol, exchange, interval, start, end)
