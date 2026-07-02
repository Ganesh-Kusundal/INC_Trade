"""MarketDataPort — single port for all historical market data access.

This is the canonical contract that every analytics consumer depends on.
Implementations (DuckDB-backed, cached, in-memory, CSV, etc.) are hidden
behind this protocol so that Replay, Backtesting, Scanner, API, Research,
Walk-Forward, Paper Trading, and CLI all consume identical historical
datasets through one interface.

No analytics module may bypass this port to access DuckDB, Parquet,
broker APIs, or file paths directly.

Usage::

    from domain.ports import MarketDataPort

    def analyse(port: MarketDataPort) -> None:
        df = port.history("RELIANCE", timeframe="1m", lookback_days=30)
        ...
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd

from domain.entities.options import FutureChain, OptionChain


@runtime_checkable
class MarketDataPort(Protocol):
    """Single port for all historical market data access.

    Every analytics module, API endpoint, CLI command, and replay/backtest
    engine must obtain market data exclusively through this interface.

    Implementations include:
    - ``DataLakeMarketDataProvider`` (Parquet + DuckDB)
    - ``DataFrameMarketDataProvider`` (in-memory DataFrames, for tests)
    - ``CsvMarketDataProvider`` (CSV files, for notebooks)
    - ``CachedMarketDataProvider`` (decorator adding caching)
    """

    # ── Single-symbol access ────────────────────────────────────────

    def history(
        self,
        symbol: str,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Load historical OHLCV bars for *symbol*.

        Parameters
        ----------
        symbol:
            NSE/BSE symbol (e.g. ``"RELIANCE"``).
        timeframe:
            Candle timeframe (``"1m"``, ``"5m"``, ``"1D"``, etc.).
        lookback_days:
            Number of calendar days to look back.  Ignored when
            *from_date* is provided.
        from_date:
            Start date ``YYYY-MM-DD``.  Overrides *lookback_days*.
        to_date:
            End date ``YYYY-MM-DD``.  Defaults to today.

        Returns
        -------
        pd.DataFrame
            OHLCV data with at least ``timestamp``, ``open``, ``high``,
            ``low``, ``close``, ``volume`` columns.
        """
        ...

    def option_chain(
        self,
        underlying: str,
        *,
        expiry: str | None = None,
    ) -> OptionChain:
        """Load option chain for *underlying*.

        Parameters
        ----------
        underlying:
            Underlying symbol.
        expiry:
            Expiry date ``YYYY-MM-DD``.  ``None`` returns nearest expiry.
        """
        ...

    def future_chain(self, underlying: str) -> FutureChain:
        """Load futures chain for *underlying*."""
        ...

    def ltp(self, symbol: str, *, exchange: str = "NSE") -> float:
        """Return last-traded price for *symbol*."""
        ...

    # ── Batch / universe access ─────────────────────────────────────

    def history_batch(
        self,
        symbols: list[str],
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Load historical OHLCV for multiple symbols in one call.

        Returns a single DataFrame with a ``symbol`` column.
        """
        ...

    def list_symbols(self, timeframe: str = "1m") -> list[str]:
        """List all symbols that have data for *timeframe*."""
        ...

    # ── Analytical escape hatch ─────────────────────────────────────

    def query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        """Execute a raw SQL query against the analytical engine.

        This is an explicit escape hatch for analytical workloads
        (scanners, ranking, feature engineering) that benefit from
        direct SQL.  Implementations should route through DuckDB or
        equivalent columnar engine.

        Parameters
        ----------
        sql:
            SQL query string.
        params:
            Positional parameters for the query.

        Returns
        -------
        pd.DataFrame
            Query results.
        """
        ...


__all__ = ["MarketDataPort"]
