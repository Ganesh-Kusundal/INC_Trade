"""Dhan historical data adapter — daily and intraday candles."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from brokers.adapters.dhan.config import ENDPOINTS
from brokers.adapters.dhan.http import DhanHttpClient
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.invariants import assert_valid_dhan_payload
from brokers.domain.entities import Candle

logger = logging.getLogger(__name__)

_TIMEFRAME_MAP = {
    "1m": 1,
    "1M": 1,
    "1": 1,
    "5m": 5,
    "5M": 5,
    "5": 5,
    "15m": 15,
    "15M": 15,
    "15": 15,
    "25m": 25,
    "25": 25,
    "60m": 60,
    "60M": 60,
    "60": 60,
    "1D": "1D",
    "D": "1D",
    "DAY": "1D",
}


class DhanHistorical:
    def __init__(self, client: DhanHttpClient, resolver: DhanInstrumentResolver):
        self._client = client
        self._resolver = resolver

    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        ref = self._resolver.resolve(symbol, exchange)
        interval = _TIMEFRAME_MAP.get(resolution, resolution)

        from_date = start_time.strftime("%Y-%m-%d")
        to_date = end_time.strftime("%Y-%m-%d")

        if interval == "1D":
            payload = {
                "securityId": ref.security_id_str(),
                "exchangeSegment": ref.exchange_segment,
                "instrument": ref.instrument_type,
                "expiryCode": 0,
                "oi": True,
                "fromDate": from_date,
                "toDate": to_date,
            }
        else:
            payload = {
                "securityId": ref.security_id_str(),
                "exchangeSegment": ref.exchange_segment,
                "instrument": ref.instrument_type,
                "interval": str(interval),
                "oi": True,
                "fromDate": f"{from_date} 09:15:00",
                "toDate": f"{to_date} 15:30:00",
            }

        assert_valid_dhan_payload(payload, context="historical.get_historical_candles")
        data = self._client.post(ENDPOINTS["historical"], json=payload)
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
        return self.get_historical_candles(symbol, exchange, start_time, end_time, resolution)

    @staticmethod
    def _parse(data: dict, symbol: str) -> list[Candle]:
        raw = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(raw, dict) and "data" in raw:
            raw = raw["data"]
        if not isinstance(raw, (list, dict)):
            return []
        if isinstance(raw, dict):
            # Dhan sometimes returns column arrays instead of row dicts for chart data
            if "start_Time" in raw and "open" in raw:
                # Columnar format
                times = raw.get("start_Time", [])
                opens = raw.get("open", [])
                highs = raw.get("high", [])
                lows = raw.get("low", [])
                closes = raw.get("close", [])
                vols = raw.get("volume", [])
                
                candles = []
                for i in range(len(times)):
                    try:
                        ts = datetime.fromtimestamp(times[i], tz=ZoneInfo("Asia/Kolkata"))
                    except Exception:
                        continue
                    candles.append(
                        Candle(
                            symbol=symbol,
                            timestamp=ts,
                            open=Decimal(str(opens[i])),
                            high=Decimal(str(highs[i])),
                            low=Decimal(str(lows[i])),
                            close=Decimal(str(closes[i])),
                            volume=int(vols[i]) if i < len(vols) else 0,
                        )
                    )
                return candles
            raw = [raw]

        candles = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            ts_raw = item.get("timestamp") or item.get("date", "")
            if isinstance(ts_raw, (int, float)):
                ts = datetime.fromtimestamp(ts_raw, tz=ZoneInfo("Asia/Kolkata"))
            else:
                try:
                    ts = datetime.fromisoformat(str(ts_raw))
                except Exception:
                    continue
            candles.append(
                Candle(
                    symbol=symbol,
                    timestamp=ts,
                    open=Decimal(str(item.get("open", 0))),
                    high=Decimal(str(item.get("high", 0))),
                    low=Decimal(str(item.get("low", 0))),
                    close=Decimal(str(item.get("close", 0))),
                    volume=int(item.get("volume", 0)),
                )
            )
        return candles
