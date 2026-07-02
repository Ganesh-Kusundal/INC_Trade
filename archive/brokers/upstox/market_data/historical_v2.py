"""Upstox V2 historical candle client.

Mirrors Trade_J ``UpstoxHistoricalDataRestClient``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxHistoricalV2Client:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_candles(
        self,
        instrument_key: str,
        interval: str,
        to_date: date,
        from_date: date | None = None,
        unit: str | None = None,
    ) -> dict[str, Any]:
        from_date_str = from_date.isoformat() if from_date else None
        url = self._urls.historical_candle_url(
            instrument_key=instrument_key,
            interval=interval,
            to_date=to_date.isoformat(),
            from_date=from_date_str,
        )
        params: dict[str, Any] = {}
        if unit:
            params["unit"] = unit
        return self._http.get_json(url, params=params)
