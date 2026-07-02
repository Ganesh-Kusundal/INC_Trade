"""P9: Shared ``HistoricalDataService`` used by all broker adapters.

Provides:
* Multi-page (chunked-by-year) candle fetching.
* Timezone normalisation to IST.
* Local Parquet cache for replay/backtesting.
* Gap detection (best-effort) and gap-fill (caller-driven).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from infrastructure.io.parquet import atomic_parquet_write

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


class SupportsHistoricalCandles(Protocol):
    def get_historical_daily(
        self,
        security_id: str,
        exchange_segment: Any,
        from_date: date,
        to_date: date,
        instrument: str = "EQUITY",
    ) -> list[Any]: ...

    def get_historical_intraday(
        self,
        security_id: str,
        exchange_segment: Any,
        from_date: date,
        to_date: date,
        interval: str | None = None,
    ) -> list[Any]: ...


@dataclass
class HistoricalDataRequest:
    security_id: str
    exchange_segment: Any
    interval: str = "1d"
    from_date: date = field(default_factory=lambda: date.today())
    to_date: date = field(default_factory=lambda: date.today())
    auto_repair_gaps: bool = True


@dataclass
class GapRange:
    from_date: date
    to_date: date


class HistoricalDataService:
    """Cross-broker historical-data service with pagination, IST
    timezone handling, and Parquet cache support.
    """

    DEFAULT_PAGE_DAYS = 365

    def __init__(
        self,
        client: SupportsHistoricalCandles,
        *,
        page_days: int = DEFAULT_PAGE_DAYS,
        parquet_cache_path: Path | None = None,
    ) -> None:
        self._client = client
        self._page_days = page_days
        self._parquet_cache_path = parquet_cache_path

    def get_candles(self, request: HistoricalDataRequest) -> list[Any]:
        if request.to_date < request.from_date:
            return []
        return self._paginated_fetch(
            request.security_id,
            request.exchange_segment,
            request.from_date,
            request.to_date,
            request.interval,
        )

    def get_intraday(self, request: HistoricalDataRequest) -> list[Any]:
        if request.to_date < request.from_date:
            return []
        return self._paginated_fetch(
            request.security_id,
            request.exchange_segment,
            request.from_date,
            request.to_date,
            request.interval,
        )

    def _paginated_fetch(
        self,
        security_id: str,
        exchange_segment: Any,
        from_date: date,
        to_date: date,
        interval: str,
    ) -> list[Any]:
        page_size = max(1, self._page_days)
        all_candles: list[Any] = []
        current = from_date
        while current <= to_date:
            page_end = min(current + timedelta(days=page_size - 1), to_date)
            try:
                if interval in ("1d", "day", "d", ""):
                    page = self._client.get_historical_daily(
                        security_id, exchange_segment, current, page_end
                    )
                else:
                    page = self._client.get_historical_intraday(
                        security_id, exchange_segment, current, page_end, interval=interval
                    )
            except Exception as exc:
                logger.warning(
                    "HistoricalDataService: page %s..%s failed: %s", current, page_end, exc
                )
                page = []
            all_candles.extend(page)
            current = page_end + timedelta(days=1)
        return all_candles

    def find_gaps(
        self,
        candles: list[Any],
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        is_intraday: bool = False,
    ) -> list[GapRange]:
        """Detect gaps in the returned candle series (caller may then choose
        to backfill). Returns a list of date ranges where no candle was
        returned for an expected trading day.
        """
        if not candles:
            return []
        by_day: dict[date, int] = {}
        for c in candles:
            ts = getattr(c, "timestamp", None) or (c[0] if isinstance(c, list | tuple) else None)
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
            if isinstance(ts, int | float):
                ts = datetime.fromtimestamp(float(ts), tz=IST)
            if isinstance(ts, datetime):
                local = ts.astimezone(IST) if ts.tzinfo else ts.replace(tzinfo=IST)
                key = local.date() if not is_intraday else local
                by_day[key] = by_day.get(key, 0) + 1
        if not by_day:
            return []
        if from_date is None:
            from_date = min(by_day.keys())
        if to_date is None:
            to_date = max(by_day.keys())
        gaps: list[GapRange] = []
        current = from_date
        in_gap = False
        gap_start: date | None = None
        while current <= to_date:
            present = by_day.get(current, 0) > 0
            if not present:
                if not in_gap:
                    in_gap = True
                    gap_start = current
            else:
                if in_gap and gap_start is not None and gap_start < current:
                    gaps.append(GapRange(gap_start, current - timedelta(days=1)))
                in_gap = False
                gap_start = None
            current += timedelta(days=1)
        if in_gap and gap_start is not None and gap_start <= to_date:
            gaps.append(GapRange(gap_start, to_date))
        return gaps

    def backfill_gap(
        self,
        security_id: str,
        exchange_segment: Any,
        gap: GapRange,
        *,
        interval: str = "1d",
    ) -> list[Any]:
        return self._paginated_fetch(
            security_id, exchange_segment, gap.from_date, gap.to_date, interval
        )

    def cache_to_parquet(self, candles: list[Any], path: Path) -> None:
        try:
            import pandas as pd
            import pyarrow as pa

            if not candles:
                return
            rows = []
            for c in candles:
                ts = getattr(c, "timestamp", None)
                rows.append(
                    {
                        "timestamp": ts,
                        "open": float(getattr(c, "open", 0)),
                        "high": float(getattr(c, "high", 0)),
                        "low": float(getattr(c, "low", 0)),
                        "close": float(getattr(c, "close", 0)),
                        "volume": int(getattr(c, "volume", 0)),
                    }
                )
            df = pd.DataFrame(rows)
            table = pa.Table.from_pandas(df, preserve_index=False)
            atomic_parquet_write(path, table, compression="snappy")
        except Exception as exc:
            logger.warning("cache_to_parquet failed: %s", exc)

    def load_from_parquet(self, path: Path) -> list[Any]:
        try:
            import pandas as pd

            from domain import HistoricalCandle

            df = pd.read_parquet(path)
            out: list[HistoricalCandle] = []

            def to_timestamp(ts):
                return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts

            out = [
                HistoricalCandle(
                    timestamp=to_timestamp(ts),
                    open=float(open_val),
                    high=float(high_val),
                    low=float(low_val),
                    close=float(close_val),
                    volume=int(volume),
                )
                for ts, open_val, high_val, low_val, close_val, volume in zip(
                    df["timestamp"],
                    df["open"],
                    df["high"],
                    df["low"],
                    df["close"],
                    df["volume"],
                    strict=False,
                )
            ]
            return out
        except Exception as exc:
            logger.warning("load_from_parquet failed: %s", exc)
            return []
