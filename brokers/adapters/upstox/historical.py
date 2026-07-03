"""Upstox historical data adapter — daily and intraday candles."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from brokers.adapters.upstox.config import EXCHANGE_TO_SEGMENT
from brokers.adapters.upstox.http import UpstoxHttpClient
from brokers.domain.entities import Candle

logger = logging.getLogger(__name__)

_INTERVAL_MAP = {
    "1m": "minute",
    "1M": "minute",
    "1": "minute",
    "5m": "5minute",
    "5M": "5minute",
    "5": "5minute",
    "15m": "15minute",
    "15M": "15minute",
    "15": "15minute",
    "30m": "30minute",
    "30M": "30minute",
    "30": "30minute",
    "60m": "60minute",
    "60M": "60minute",
    "60": "60minute",
    "1D": "day",
    "D": "day",
    "DAY": "day",
    "1W": "week",
    "W": "week",
}


class UpstoxHistorical:
    def __init__(self, client: UpstoxHttpClient):
        self._client = client

    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        segment = EXCHANGE_TO_SEGMENT.get(exchange.upper(), exchange)
        instrument_key = f"{segment}|{symbol}"
        interval = _INTERVAL_MAP.get(resolution, resolution)

        from_date = start_time.strftime("%Y-%m-%d")
        to_date = end_time.strftime("%Y-%m-%d")

        endpoint = (
            f"/v2/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"
        )
        data = self._client.get(endpoint)
        return self._parse(data, symbol)

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        """Alias for get_historical_candles for protocol compatibility."""
        return self.get_historical_candles(
            symbol, exchange, start_time, end_time, resolution
        )

    @staticmethod
    def _parse(data: dict, symbol: str) -> list[Candle]:
        inner = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(inner, dict):
            candles_raw = inner.get("candles", [])
        else:
            candles_raw = []

        candles = []
        for item in candles_raw:
            if isinstance(item, list) and len(item) >= 5:
                # item[0] is ISO timestamp string like '2023-11-20T00:00:00+05:30'
                try:
                    ts = datetime.fromisoformat(str(item[0]))
                except ValueError:
                    continue
                candles.append(
                    Candle(
                        symbol=symbol,
                        timestamp=ts,
                        open=Decimal(str(item[1])),
                        high=Decimal(str(item[2])),
                        low=Decimal(str(item[3])),
                        close=Decimal(str(item[4])),
                        volume=int(item[5]) if len(item) > 5 else 0,
                    )
                )
        return candles
