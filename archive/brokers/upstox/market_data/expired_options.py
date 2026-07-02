"""Upstox expired instruments client (Plus plan)."""

from __future__ import annotations

from datetime import date
from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxExpiredInstrumentsClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_expiries(self, instrument_key: str) -> list[str]:
        body = self._http.get_json(
            self._urls.expired_expiries_url(),
            params={"instrument_key": instrument_key},
        )
        if isinstance(body, list):
            return [str(x) for x in body]
        if isinstance(body, dict):
            data = body.get("data")
            return [str(x) for x in data] if isinstance(data, list) else []
        return []

    def get_option_contract(self, instrument_key: str, expiry: str) -> dict[str, Any]:
        return self._http.get_json(
            self._urls.expired_option_contract_url(),
            params={"instrument_key": instrument_key, "expiry_date": expiry},
        )

    def get_historical_candle(
        self,
        expired_instrument_key: str,
        interval: str,
        to_date: date,
        from_date: date,
    ) -> dict[str, Any]:
        return self._http.get_json(
            self._urls.expired_historical_candle_url(
                expired_instrument_key, interval, to_date.isoformat(), from_date.isoformat()
            )
        )
