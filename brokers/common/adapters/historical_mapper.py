"""Map canonical OHLCV DataFrames to HistoricalBar domain objects."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from domain.historical import BarLabelConvention, HistoricalBar, InstrumentRef
from domain.provenance import DataProvenance


def _parse_timestamp(value: object) -> datetime:
    ts = value if isinstance(value, datetime) else pd.Timestamp(value).to_pydatetime()
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def dataframe_to_historical_bars(
    df: pd.DataFrame,
    instrument: InstrumentRef,
    timeframe: str,
    broker_id: str,
    request_id: str,
) -> list[HistoricalBar]:
    """Convert a broker history DataFrame to normalized HistoricalBar list."""
    if df is None or df.empty:
        return []

    bars: list[HistoricalBar] = []
    for idx, row in df.iterrows():
        ts_col = None
        for candidate in ("timestamp", "date", "datetime", "time"):
            if candidate in df.columns:
                ts_col = candidate
                break
        if ts_col is None:
            continue

        open_val = row.get("open", row.get("Open", 0))
        high_val = row.get("high", row.get("High", open_val))
        low_val = row.get("low", row.get("Low", open_val))
        close_val = row.get("close", row.get("Close", open_val))
        volume_val = row.get("volume", row.get("Volume", 0))

        bars.append(
            HistoricalBar(
                instrument=instrument,
                timeframe=timeframe,
                event_time=_parse_timestamp(row[ts_col]),
                open=Decimal(str(open_val)),
                high=Decimal(str(high_val)),
                low=Decimal(str(low_val)),
                close=Decimal(str(close_val)),
                volume=int(volume_val or 0),
                open_interest=int(row.get("oi", row.get("open_interest", 0)) or 0),
                bar_index=int(idx) if isinstance(idx, int) else len(bars),
                provenance=DataProvenance.now(
                    broker_id=broker_id,
                    request_id=request_id,
                    provider_timestamp=_parse_timestamp(row[ts_col]),
                    transformation_chain=("market_data.history", "normalize.ohlcv.v1"),
                ),
                label_convention=BarLabelConvention.LEFT,
            )
        )
    return bars
