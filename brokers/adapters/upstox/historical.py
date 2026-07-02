"""Upstox historical data adapter — daily and intraday candles."""

from __future__ import annotations

import logging

from brokers.adapters.upstox.config import EXCHANGE_TO_SEGMENT
from brokers.adapters.upstox.http import UpstoxHttpClient

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

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        from_date: str,
        to_date: str,
        timeframe: str = "1D",
    ) -> list[dict]:
        segment = EXCHANGE_TO_SEGMENT.get(exchange.upper(), exchange)
        instrument_key = f"{segment}|{symbol}"
        interval = _INTERVAL_MAP.get(timeframe, timeframe)

        endpoint = (
            f"/v2/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"
        )
        data = self._client.get(endpoint)
        return self._parse(data)

    @staticmethod
    def _parse(data: dict) -> list[dict]:
        inner = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(inner, dict):
            candles_raw = inner.get("candles", [])
        else:
            candles_raw = []

        candles = []
        for item in candles_raw:
            if isinstance(item, list) and len(item) >= 5:
                candles.append(
                    {
                        "timestamp": str(item[0]),
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": int(item[5]) if len(item) > 5 else 0,
                    }
                )
            elif isinstance(item, dict):
                candles.append(
                    {
                        "timestamp": str(item.get("timestamp", "")),
                        "open": float(item.get("open", 0)),
                        "high": float(item.get("high", 0)),
                        "low": float(item.get("low", 0)),
                        "close": float(item.get("close", 0)),
                        "volume": int(item.get("volume", 0)),
                    }
                )
        return candles
