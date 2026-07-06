"""Upstox historical data adapter — daily and intraday candles."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from brokers.config.endpoints import _UpstoxUrls
from brokers.domain.entities import Candle
from brokers.ports.http_client_port import HttpClientPort

from brokers.adapters.upstox.config import _INTERVAL_MAP
from brokers.adapters.upstox.instruments import UpstoxInstruments, resolve_upstox_instrument_key
from brokers.adapters.upstox.mapper import unwrap_data

logger = logging.getLogger(__name__)


class UpstoxHistorical:
    def __init__(
        self,
        client: HttpClientPort,
        *,
        urls: _UpstoxUrls,
        instruments: UpstoxInstruments | None = None,
    ):
        self._client = client
        self._urls = urls
        self._instruments = instruments

    def _instrument_key(self, symbol: str, exchange: str) -> str:
        return resolve_upstox_instrument_key(symbol, exchange, self._instruments)

    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        instrument_key = self._instrument_key(symbol, exchange)
        interval = _INTERVAL_MAP.get(resolution, resolution)

        from_date = start_time.strftime("%Y-%m-%d")
        to_date = end_time.strftime("%Y-%m-%d")

        endpoint = f"/v2/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"
        try:
            data = self._client.get(endpoint)
            return self._parse(data, symbol)
        except Exception as exc:
            logger.warning("Historical fetch failed for %s: %s", symbol, exc)
            return []

    def get_intraday_candles_v3(
        self,
        symbol: str,
        exchange: str,
        unit: str,
        interval: int,
        to_date: str,
    ) -> list[Candle]:
        instrument_key = self._instrument_key(symbol, exchange)
        url = self._urls.intraday_candle_v3_url(instrument_key, unit, interval, to_date)
        try:
            data = self._client.get(url)
            return self._parse(data, symbol)
        except Exception as exc:
            logger.warning("V3 intraday fetch failed for %s: %s", symbol, exc)
            return []

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        """Alias for get_historical_candles for protocol compatibility."""
        return self.get_historical_candles(symbol, exchange, start_time, end_time, resolution)

    @staticmethod
    def _parse(data: dict[str, Any], symbol: str) -> list[Candle]:
        inner = unwrap_data(data, default=data)
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
