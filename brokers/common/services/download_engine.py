"""HistoricalDownloadEngine — chunking, retries, merge, dedup, parallel.

This is the universal data download engine that handles:
  - Automatic chunking of large date ranges
  - Retries with exponential backoff
  - Merge and deduplication of results
  - Parallel multi-symbol downloads
  - Progress tracking
  - Parquet caching

Usage:
    from brokers.common.services.download_engine import HistoricalDownloadEngine
    from brokers.common.gateway import MarketDataGateway

    gw: MarketDataGateway = PaperGateway()  # Any broker implementing the contract
    engine = HistoricalDownloadEngine(gw)

    # Single symbol, 5 years
    df = engine.download("RELIANCE", years=5, timeframe="1D")

    # Multi-symbol
    df = engine.download(["RELIANCE", "TCS", "INFY"], years=2)

    # With parallel
    df = engine.download(symbols, years=1, parallel=True, max_workers=5)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
import pyarrow as pa

from infrastructure.io.parquet import atomic_parquet_write

logger = logging.getLogger(__name__)


@dataclass
class DownloadConfig:
    """Configuration for historical data downloads."""

    # Chunking
    chunk_days: int = 365  # Days per API request

    # Retry
    max_retries: int = 3
    retry_base_delay: float = 1.0  # Seconds
    retry_max_delay: float = 30.0  # Seconds

    # Parallel
    max_workers: int = 5
    rate_limit_per_second: float = 5.0  # Conservative default

    # Caching
    cache_dir: Path | None = None
    cache_format: str = "parquet"  # parquet or csv

    # Validation
    dedup: bool = True
    sort: bool = True
    validate_schema: bool = True


@dataclass
class DownloadProgress:
    """Tracks download progress."""

    total_symbols: int = 0
    completed_symbols: int = 0
    total_chunks: int = 0
    completed_chunks: int = 0
    failed_chunks: int = 0
    total_rows: int = 0
    start_time: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time if self.start_time else 0.0

    @property
    def symbol_progress(self) -> float:
        return self.completed_symbols / self.total_symbols if self.total_symbols else 0.0

    @property
    def chunk_progress(self) -> float:
        return self.completed_chunks / self.total_chunks if self.total_chunks else 0.0

    def summary(self) -> str:
        return (
            f"symbols={self.completed_symbols}/{self.total_symbols} "
            f"chunks={self.completed_chunks}/{self.total_chunks} "
            f"failed={self.failed_chunks} "
            f"rows={self.total_rows} "
            f"time={self.elapsed:.1f}s"
        )


class HistoricalDownloadEngine:
    """Universal historical data download engine.

    Handles chunking, retries, merge, dedup, and parallel downloads
    for any broker that implements the MarketDataGateway contract.
    """

    # Timeframe to max days mapping (Upstox limits)
    TIMEFRAME_MAX_DAYS: ClassVar[dict[str, int]] = {
        "1m": 30,
        "5m": 30,
        "15m": 30,
        "30m": 30,
        "1h": 90,
        "1D": 365 * 10,
    }

    def __init__(
        self,
        gateway: Any,
        config: DownloadConfig | None = None,
        on_progress: Callable[[DownloadProgress], None] | None = None,
    ) -> None:
        self._gateway = gateway
        self._config = config or DownloadConfig()
        self._on_progress = on_progress

    def download(
        self,
        symbols: str | list[str],
        *,
        years: int = 1,
        timeframe: str = "1D",
        from_date: str | None = None,
        to_date: str | None = None,
        exchange: str = "NSE",
        parallel: bool = True,
        max_workers: int | None = None,
    ) -> pd.DataFrame:
        """Download historical data for one or more symbols.

        Parameters
        ----------
        symbols : str or list[str]
            Single symbol or list of symbols.
        years : int
            Years of history to download (ignored if from_date/to_date set).
        timeframe : str
            Candle interval: 1m, 5m, 15m, 30m, 1h, 1D.
        from_date : str or None
            Start date (YYYY-MM-DD). Overrides years.
        to_date : str or None
            End date (YYYY-MM-DD). Defaults to today.
        exchange : str
            Exchange identifier.
        parallel : bool
            Download multiple symbols in parallel.
        max_workers : int or None
            Override max parallel workers.

        Returns
        -------
        pd.DataFrame with canonical columns: timestamp, open, high, low, close, volume, oi, symbol, exchange, timeframe
        """
        sym_list = [symbols] if isinstance(symbols, str) else symbols
        progress = DownloadProgress(total_symbols=len(sym_list), start_time=time.time())

        # Calculate date range
        end = date.fromisoformat(to_date) if to_date else date.today()
        start = date.fromisoformat(from_date) if from_date else end - timedelta(days=years * 365)

        # Check broker capabilities for this timeframe
        max_days = self.TIMEFRAME_MAX_DAYS.get(timeframe, 365)
        if hasattr(self._gateway, "capabilities"):
            cap = self._gateway.capabilities()
            # BrokerCapabilities dataclass or dict
            if hasattr(cap, "max_intraday_days"):
                broker_max = cap.max_intraday_days if timeframe != "1D" else 3650
            else:
                broker_max = (
                    cap.get("max_intraday_days", max_days)
                    if timeframe != "1D"
                    else cap.get("max_daily_days", 3650)
                )
        else:
            broker_max = max_days
        effective_max = min(max_days, broker_max)

        # Calculate chunks
        chunks = self._compute_chunks(start, end, effective_max)
        progress.total_chunks = len(chunks) * len(sym_list)

        logger.info(
            "Downloading %d symbols, %d chunks each, timeframe=%s",
            len(sym_list),
            len(chunks),
            timeframe,
        )

        if parallel and len(sym_list) > 1:
            workers = max_workers or self._config.max_workers
            frames = self._download_parallel(
                sym_list, chunks, timeframe, exchange, progress, workers
            )
        else:
            frames = self._download_sequential(sym_list, chunks, timeframe, exchange, progress)

        if not frames:
            return pd.DataFrame()

        # Merge all frames
        df = pd.concat(frames, ignore_index=True)

        # Dedup
        if self._config.dedup:
            df = self._dedup(df)

        # Sort
        if self._config.sort:
            df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

        # Validate schema
        if self._config.validate_schema:
            df = self._validate_schema(df)

        # Cache
        if self._config.cache_dir:
            self._cache(df, symbols, timeframe)

        progress.total_rows = len(df)
        progress.completed_symbols = len(sym_list)

        elapsed = time.time() - progress.start_time
        logger.info("Download complete: %s (%.1fs)", progress.summary(), elapsed)

        if self._on_progress:
            self._on_progress(progress)

        return df

    def _compute_chunks(self, start: date, end: date, max_days: int) -> list[tuple[date, date]]:
        """Split date range into broker-compatible chunks."""
        chunks = []
        current = start
        while current <= end:
            chunk_end = min(current + timedelta(days=max_days - 1), end)
            chunks.append((current, chunk_end))
            current = chunk_end + timedelta(days=1)
        return chunks

    def _download_sequential(
        self,
        symbols: list[str],
        chunks: list[tuple[date, date]],
        timeframe: str,
        exchange: str,
        progress: DownloadProgress,
    ) -> list[pd.DataFrame]:
        """Download symbols sequentially."""
        frames = []
        for sym in symbols:
            for chunk_start, chunk_end in chunks:
                df = self._fetch_chunk(sym, exchange, timeframe, chunk_start, chunk_end, progress)
                if df is not None and not df.empty:
                    frames.append(df)
        return frames

    def _download_parallel(
        self,
        symbols: list[str],
        chunks: list[tuple[date, date]],
        timeframe: str,
        exchange: str,
        progress: DownloadProgress,
        max_workers: int,
    ) -> list[pd.DataFrame]:
        """Download symbols in parallel using ThreadPoolExecutor."""
        frames = []

        def _fetch_task(sym: str, chunk_start: date, chunk_end: date) -> pd.DataFrame | None:
            return self._fetch_chunk(sym, exchange, timeframe, chunk_start, chunk_end, progress)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for sym in symbols:
                for chunk_start, chunk_end in chunks:
                    future = executor.submit(_fetch_task, sym, chunk_start, chunk_end)
                    futures[future] = (sym, chunk_start, chunk_end)

            for future in as_completed(futures):
                sym, chunk_start, chunk_end = futures[future]
                try:
                    df = future.result()
                    if df is not None and not df.empty:
                        frames.append(df)
                        progress.completed_chunks += 1
                        progress.total_rows += len(df)
                except Exception as exc:
                    progress.failed_chunks += 1
                    progress.errors.append(f"{sym} {chunk_start}..{chunk_end}: {exc}")
                    logger.warning(
                        "Download failed for %s %s..%s: %s", sym, chunk_start, chunk_end, exc
                    )

                if self._on_progress:
                    self._on_progress(progress)

        progress.completed_symbols = len(symbols)
        return frames

    def _fetch_chunk(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        from_date: date,
        to_date: date,
        progress: DownloadProgress,
    ) -> pd.DataFrame | None:
        """Fetch a single chunk with retries."""
        for attempt in range(self._config.max_retries + 1):
            try:
                df = self._gateway.history(
                    symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    from_date=from_date.isoformat(),
                    to_date=to_date.isoformat(),
                )

                if df is not None and not df.empty:
                    # Ensure required columns
                    for col in ["symbol", "exchange", "timeframe"]:
                        if col not in df.columns:
                            df[col] = (
                                symbol
                                if col == "symbol"
                                else exchange
                                if col == "exchange"
                                else timeframe
                            )
                    return df

                return pd.DataFrame()

            except Exception as exc:
                if attempt < self._config.max_retries:
                    delay = min(
                        self._config.retry_base_delay * (2**attempt),
                        self._config.retry_max_delay,
                    )
                    logger.warning(
                        "Retry %d/%d for %s %s..%s in %.1fs: %s",
                        attempt + 1,
                        self._config.max_retries,
                        symbol,
                        from_date,
                        to_date,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                else:
                    progress.failed_chunks += 1
                    progress.errors.append(f"{symbol} {from_date}..{to_date}: {exc}")
                    logger.error(
                        "Failed after %d retries for %s %s..%s: %s",
                        self._config.max_retries,
                        symbol,
                        from_date,
                        to_date,
                        exc,
                    )
                    return None

        return None

    def _dedup(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove duplicate rows."""
        before = len(df)
        df = df.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
        removed = before - len(df)
        if removed > 0:
            logger.info("Dedup: removed %d duplicate rows", removed)
        return df

    def _validate_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate and fix DataFrame schema."""
        required = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                logger.warning("Missing column: %s, adding default", col)
                if col == "volume":
                    df[col] = 0
                elif col == "timestamp":
                    df[col] = pd.Timestamp.now()
                else:
                    df[col] = 0.0

        # Ensure numeric columns
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def _cache(self, df: pd.DataFrame, symbols: str | list[str], timeframe: str) -> None:
        """Cache downloaded data to disk atomically."""
        if self._config.cache_dir is None:
            return

        cache_dir = self._config.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

        sym_str = symbols if isinstance(symbols, str) else "_".join(symbols[:5])
        filename = f"{sym_str}_{timeframe}.{self._config.cache_format}"
        path = cache_dir / filename

        try:
            if self._config.cache_format == "parquet":
                table = pa.Table.from_pandas(df, preserve_index=False)
                atomic_parquet_write(path, table, compression="snappy")
            else:
                df.to_csv(path, index=False)
            logger.info("Cached %d rows to %s", len(df), path)
        except Exception as exc:
            logger.warning("Cache failed: %s", exc)
