"""Dhan historical data adapter — daily and intraday candles."""

from __future__ import annotations

import logging
from datetime import datetime

from brokers.adapters.dhan.config import ENDPOINTS
from brokers.adapters.dhan.http import DhanHttpClient
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.invariants import assert_valid_dhan_payload

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

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        from_date: str,
        to_date: str,
        timeframe: str = "1D",
    ) -> list[dict]:
        ref = self._resolver.resolve(symbol, exchange)
        interval = _TIMEFRAME_MAP.get(timeframe, timeframe)

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

        assert_valid_dhan_payload(payload, context="historical.get_candles")
        data = self._client.post(ENDPOINTS["historical"], json=payload)
        return self._parse(data)

    @staticmethod
    def _parse(data: dict) -> list[dict]:
        raw = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(raw, dict) and "data" in raw:
            raw = raw["data"]
        if not isinstance(raw, (list, dict)):
            return []
        if isinstance(raw, dict):
            raw = [raw]

        candles = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            ts = item.get("timestamp") or item.get("date", "")
            if isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts).isoformat()
            candles.append(
                {
                    "timestamp": str(ts),
                    "open": float(item.get("open", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "close": float(item.get("close", 0)),
                    "volume": int(item.get("volume", 0)),
                }
            )
        return candles
