"""Historical data provider port — pluggable data source abstraction.

This is a narrow Protocol for data sources that can serve historical
candles. Broker adapters, CSV files, replay engines, and cache all
implement this interface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from inc_trade.domain.entities import Candle


@runtime_checkable
class HistoricalProvider(Protocol):
    """Protocol for historical market data providers.

    Implementations include broker adapters, replay engines, CSV file
    readers, and database backends.
    """

    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        """Fetch historical OHLCV candles.

        Args:
            symbol: Instrument symbol.
            exchange: Exchange identifier.
            start_time: Start time for historical data.
            end_time: End time for historical data.
            resolution: Time resolution (e.g., '1', '5', '15', '60', '1D').

        Returns:
            List of historical candles.
        """
        ...

    @property
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g., 'dhan', 'upstox', 'replay')."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether this provider is currently available for queries."""
        ...
