"""Historical data adapter — candle fetching and timeframe mapping.

Responsibility: Fetch historical OHLCV candles from Upstox V3 API with
automatic date range clipping and timeframe normalization.
Thread-safe: All methods are stateless and thread-safe.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import pandas as pd

from domain.parsing import parse_timestamp

if TYPE_CHECKING:
    from brokers.upstox.broker import UpstoxBroker


# Timeframe to V3 API interval mapping: (unit, interval)
_INTERVAL_MAP: dict[str, tuple[str, str]] = {
    "1": ("minutes", "1"),
    "1MIN": ("minutes", "1"),
    "3": ("minutes", "3"),
    "3MIN": ("minutes", "3"),
    "5": ("minutes", "5"),
    "5MIN": ("minutes", "5"),
    "15": ("minutes", "15"),
    "15MIN": ("minutes", "15"),
    "30": ("minutes", "30"),
    "30MIN": ("minutes", "30"),
    "60": ("hours", "1"),
    "60MIN": ("hours", "1"),
    "1H": ("hours", "1"),
    "4H": ("hours", "4"),
    "1D": ("days", "1"),
    "D": ("days", "1"),
    "DAY": ("days", "1"),
    "1W": ("weeks", "1"),
    "W": ("weeks", "1"),
    "MON": ("months", "1"),
    "MONTH": ("months", "1"),
}

_MAX_DAYS_BY_UNIT: dict[str, int] = {
    "minutes": 30,
    "hours": 90,
    "days": 3650,  # 10 years for days/weeks/months
    "weeks": 3650,
    "months": 3650,
}


def _to_ist_timestamp(value: Any) -> Any:
    """Normalize candle timestamps to Asia/Kolkata."""
    ts = parse_timestamp(value)
    if ts is None:
        return pd.NaT
    ist = ZoneInfo("Asia/Kolkata")
    if ts.tzinfo is None:
        return ts.replace(tzinfo=ist)
    return ts.astimezone(ist)


class HistoricalAdapter:
    """Adapter for historical candle data operations.

    Encapsulates historical data fetching with automatic timeframe mapping,
    date range validation, and API limit enforcement.

    Thread Safety:
        All methods are stateless and thread-safe. No instance state is mutated.

    Example::

        adapter = HistoricalAdapter(broker)
        df = adapter.fetch_candles("RELIANCE", "NSE", "1D", lookback_days=90)
    """

    def __init__(self, broker: UpstoxBroker) -> None:
        """Initialize with broker facade.

        Args:
            broker: UpstoxBroker instance providing access to historical_v3 client
        """
        self._broker = broker

    @staticmethod
    def resolve_timeframe(timeframe: str) -> tuple[str, str]:
        """Map a timeframe string to V3 API (unit, interval) tuple.

        Args:
            timeframe: Timeframe string (e.g., "1D", "5MIN", "1H")

        Returns:
            Tuple of (unit, interval) for V3 API calls

        Example:
            >>> HistoricalAdapter.resolve_timeframe("5MIN")
            ('minutes', '5')
            >>> HistoricalAdapter.resolve_timeframe("1D")
            ('days', '1')
        """
        tf = timeframe.upper() if timeframe else "1D"
        return _INTERVAL_MAP.get(tf, ("days", "1"))

    @staticmethod
    def get_max_days(unit: str) -> int:
        """Get maximum allowed date range for a given time unit.

        Args:
            unit: Time unit ("minutes", "hours", "days", etc.)

        Returns:
            Maximum number of days allowed by V3 API
        """
        return _MAX_DAYS_BY_UNIT.get(unit, 3650)

    def fetch_candles(
        self,
        symbol: str,
        exchange: str,
        instrument_key: str,
        from_date: str,
        to_date: str,
        unit: str,
        interval: str,
    ) -> pd.DataFrame:
        """Fetch historical candles for a single symbol.

        Automatically clips date ranges to V3 API limits.

        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment
            instrument_key: Resolved Upstox instrument key
            from_date: Start date in "YYYY-MM-DD" format
            to_date: End date in "YYYY-MM-DD" format
            unit: Time unit ("minutes", "hours", "days")
            interval: Interval value (e.g., "1", "5", "15")

        Returns:
            DataFrame with columns: timestamp, open, high, low, close,
            volume, oi, symbol, exchange, timeframe
        """
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()

        # Enforce V3 API date range limits
        max_days = self.get_max_days(unit)
        if (to_dt - from_dt).days > max_days:
            from_dt = to_dt - timedelta(days=max_days)

        # Fetch from V3 API
        body = self._broker.historical_v3.get_candles(
            instrument_key, unit, interval, to_dt, from_dt
        )
        data = body.get("data", {})

        # Extract candles from response
        if isinstance(data, dict):
            candles = data.get("candles", [])
        elif isinstance(data, list):
            candles = data
        else:
            candles = []

        if not candles:
            return pd.DataFrame(
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "oi",
                    "symbol",
                    "exchange",
                    "timeframe",
                ]
            )

        # Parse candles into DataFrame
        records = []
        for c in candles:
            if isinstance(c, list) and len(c) >= 6:
                records.append(
                    {
                        "timestamp": _to_ist_timestamp(c[0]),
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": int(c[5]),
                        "oi": int(c[6]) if len(c) > 6 else 0,
                        "symbol": symbol,
                        "exchange": exchange,
                        "timeframe": interval,
                    }
                )

        return pd.DataFrame(records)

    def fetch_history_batch(
        self,
        symbols: list[str],
        exchange: str,
        instrument_keys: list[str],
        from_date: str,
        to_date: str,
        unit: str,
        interval: str,
    ) -> pd.DataFrame:
        """Fetch historical candles for multiple symbols.

        Args:
            symbols: List of canonical trading symbols
            exchange: Exchange segment
            instrument_keys: List of resolved Upstox instrument keys
            from_date: Start date in "YYYY-MM-DD" format
            to_date: End date in "YYYY-MM-DD" format
            unit: Time unit
            interval: Interval value

        Returns:
            Concatenated DataFrame for all symbols
        """
        frames = []
        for symbol, key in zip(symbols, instrument_keys, strict=False):
            df = self.fetch_candles(symbol, exchange, key, from_date, to_date, unit, interval)
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
