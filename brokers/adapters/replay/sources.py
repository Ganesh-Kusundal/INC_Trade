"""CSV data source for the Replay Engine.

Loads historical OHLCV candles from CSV files. Format::

    symbol,exchange,timestamp,open,high,low,close,volume
    RELIANCE,NSE,2024-01-02 09:15:00,2500.00,2510.00,2495.00,2505.00,500000
    ...
"""

from __future__ import annotations

import csv
import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from brokers.domain.entities import Candle

logger = logging.getLogger(__name__)


class CsvSource:
    """Loads historical candles from a CSV file.

    Usage::

        source = CsvSource()
        candles_by_symbol = source.load("data/reliance.csv")
    """

    def load(self, filepath: str) -> dict[str, list[Candle]]:
        """Load candles from a CSV file grouped by composite key.

        Args:
            filepath: Path to CSV file.

        Returns:
            Dict mapping ``{exchange}:{symbol}`` to list of ``Candle``,
            sorted by timestamp.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If a row has invalid data.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        grouped: dict[str, list[Candle]] = defaultdict(list)
        with path.open("r", newline="") as fh:
            reader = csv.DictReader(fh)
            for row_num, row in enumerate(reader, start=2):
                try:
                    candle, exchange = self._row_to_candle(row)
                    key = f"{exchange}:{candle.symbol}"
                    grouped[key].append(candle)
                except (KeyError, ValueError, InvalidOperation) as exc:
                    logger.warning("CsvSource: row %d skipped: %s", row_num, exc)
                    continue

        for key in grouped:
            grouped[key].sort(key=lambda c: c.timestamp)
        return dict(grouped)

    @staticmethod
    def _row_to_candle(row: dict[str, str]) -> tuple[Candle, str]:
        symbol = row["symbol"].strip()
        exchange = row["exchange"].strip()
        ts = datetime.fromisoformat(row["timestamp"].strip())
        candle = Candle(
            symbol=symbol,
            timestamp=ts,
            open=Decimal(row["open"].strip()),
            high=Decimal(row["high"].strip()),
            low=Decimal(row["low"].strip()),
            close=Decimal(row["close"].strip()),
            volume=int(row["volume"].strip()),
        )
        return candle, exchange
