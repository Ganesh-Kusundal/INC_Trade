"""[DEPRECATED] Historical data service. Use Instrument.ohlcv() directly. — domain layer for historical market data.

This service provides business logic for fetching and caching historical
data. It depends on the HistoricalPort abstraction, not on any specific
broker implementation.
"""

from __future__ import annotations

import logging
from datetime import datetime

from inc_trade.domain.entities import Candle
from inc_trade.ports.historical import HistoricalPort

logger = logging.getLogger(__name__)


class HistoricalService:
    """Domain service for historical market data.

    Encapsulates business rules for data fetching, caching, and normalization.
    """

    def __init__(self, historical_port: HistoricalPort):
        """Initialize with a historical data port.

        Args:
            historical_port: Broker-agnostic historical data interface
        """
        self._historical_port = historical_port

    def fetch_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        """Fetch historical candles with validation.

        Args:
            symbol: Instrument symbol
            exchange: Exchange code
            start_time: Start datetime
            end_time: End datetime
            resolution: Time resolution (e.g., '1', '5', '15', '60', '1D')

        Returns:
            List of historical candles
        """
        # Validate time range
        if start_time >= end_time:
            logger.warning("Invalid time range: start >= end")
            return []

        # Validate resolution
        valid_resolutions = {"1", "5", "15", "25", "60", "1D", "D", "DAY"}
        if resolution not in valid_resolutions:
            logger.warning(f"Invalid resolution: {resolution}")
            return []

        # Delegate to broker-specific implementation
        return self._historical_port.get_historical_candles(
            symbol=symbol,
            exchange=exchange,
            start_time=start_time,
            end_time=end_time,
            resolution=resolution,
        )

    def fetch_intraday_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str = "1",
    ) -> list[Candle]:
        """Fetch intraday candles (convenience method).

        Args:
            symbol: Instrument symbol
            exchange: Exchange code
            start_time: Start datetime
            end_time: End datetime
            resolution: Time resolution (default: '1' minute)

        Returns:
            List of intraday candles
        """
        return self.fetch_candles(
            symbol=symbol,
            exchange=exchange,
            start_time=start_time,
            end_time=end_time,
            resolution=resolution,
        )
