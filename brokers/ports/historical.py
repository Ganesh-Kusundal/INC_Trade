"""Historical data port."""

from __future__ import annotations

import abc
from datetime import datetime

from brokers.domain.entities import Candle


class HistoricalPort(abc.ABC):
    """Abstract port for historical market data retrieval."""

    @abc.abstractmethod
    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        """Fetch historical OHLCV candles.

        Parameters
        ----------
        symbol : str
            Instrument symbol.
        exchange : str
            Exchange identifier.
        start_time : datetime
            Start time for historical data.
        end_time : datetime
            End time for historical data.
        resolution : str
            Time resolution (e.g., '1', '5', '15', '60', '1D').

        Returns
        -------
        list[Candle]
            List of historical candles.
        """
        ...
