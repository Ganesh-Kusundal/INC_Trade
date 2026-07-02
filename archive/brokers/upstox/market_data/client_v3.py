"""Upstox V3 market data REST client (full quote snapshot, MTF positions)."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxMarketDataV3Client:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_full_quote(self, instrument_keys: list[str]) -> dict[str, Any]:
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {"instrument_key": ",".join(instrument_keys)}
        return self._http.get_json(self._urls.market_quote_full_v3_url(), params=params)

    def get_ltp_v3(self, instrument_keys: list[str]) -> dict[str, Any]:
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {"instrument_key": ",".join(instrument_keys)}
        return self._http.get_json(self._urls.market_quote_ltp_v3_url(), params=params)

    def get_option_greeks_v3(self, instrument_keys: list[str]) -> dict[str, Any]:
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {"instrument_key": ",".join(instrument_keys)}
        return self._http.get_json(self._urls.market_quote_option_greeks_v3_url(), params=params)

    def get_mtf_positions(self) -> list[dict[str, Any]]:
        body = self._http.get_json(self._urls.mtf_positions_v3_url())
        if not isinstance(body, dict):
            return []
        return body.get("data") if isinstance(body.get("data"), list) else []

    def get_funds_v3(self) -> dict[str, Any]:
        return self._http.get_json(self._urls.user_fund_margin_v3_url())
