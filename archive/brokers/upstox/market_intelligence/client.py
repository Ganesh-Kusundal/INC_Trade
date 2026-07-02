"""Upstox market intelligence REST client (PCR / MaxPain / OI / FII / DII / Smartlist).

Mirrors Trade_J ``UpstoxMarketDataRestClient`` market-intelligence section.
"""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxMarketIntelligenceClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_pcr(
        self, instrument_key: str, expiry: str, date: str, bucket_interval: int = 1
    ) -> dict[str, Any]:
        return self._http.get_json(
            self._urls.pcr_url(),
            params={
                "instrument_key": instrument_key,
                "expiry": expiry,
                "date": date,
                "bucket_interval": bucket_interval,
            },
        )

    def get_max_pain(
        self, instrument_key: str, expiry: str, date: str, bucket_interval: int = 1
    ) -> dict[str, Any]:
        return self._http.get_json(
            self._urls.max_pain_url(),
            params={
                "instrument_key": instrument_key,
                "expiry": expiry,
                "date": date,
                "bucket_interval": bucket_interval,
            },
        )

    def get_oi(self, instrument_key: str, expiry: str, date: str) -> dict[str, Any]:
        return self._http.get_json(
            self._urls.oi_url(),
            params={"instrument_key": instrument_key, "expiry": expiry, "date": date},
        )

    def get_fii_flow(
        self, data_type: str = "NSE_FO|INDEX_FUTURES", interval: str = "1D"
    ) -> dict[str, Any]:
        return self._http.get_json(
            self._urls.fii_url(),
            params={"data_type": data_type, "interval": interval},
        )

    def get_dii_flow(self, interval: str = "1D") -> dict[str, Any]:
        return self._http.get_json(
            self._urls.dii_url(),
            params={"data_type": "NSE_EQ|CASH", "interval": interval},
        )

    def get_smartlist_futures(
        self,
        asset_type: str = "INDEX",
        category: str = "TOP_TRADED",
        page_number: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        return self._http.get_json(
            self._urls.smartlist_futures_url(),
            params={
                "asset_type": asset_type,
                "category": category,
                "page_number": page_number,
                "page_size": page_size,
            },
        )

    def get_smartlist_options(
        self,
        asset_type: str = "INDEX",
        category: str = "TOP_TRADED",
        page_number: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        return self._http.get_json(
            self._urls.smartlist_options_url(),
            params={
                "asset_type": asset_type,
                "category": category,
                "page_number": page_number,
                "page_size": page_size,
            },
        )


def _data_list(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    return data if isinstance(data, list) else []
