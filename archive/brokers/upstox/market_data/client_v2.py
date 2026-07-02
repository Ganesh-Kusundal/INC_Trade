"""Upstox V2 market data REST client (LTP, quote, OHLC, order-book)."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxMarketDataV2Client:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_ltp(self, instrument_keys: list[str]) -> dict[str, Any]:
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {"instrument_key": ",".join(instrument_keys)}
        return self._http.get_json(self._urls.market_quote_ltp_url(), params=params)

    def get_quote(self, instrument_keys: list[str]) -> dict[str, Any]:
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {"instrument_key": ",".join(instrument_keys)}
        return self._http.get_json(self._urls.market_quote_full_url(), params=params)

    def get_ohlc(self, instrument_keys: list[str]) -> dict[str, Any]:
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {"instrument_key": ",".join(instrument_keys)}
        return self._http.get_json(self._urls.market_quote_ohlc_url(), params=params)

    def get_order_book(self, instrument_key: str) -> dict[str, Any]:
        params = {"instrument_key": instrument_key, "quote": "BEST_FIVE"}
        return self._http.get_json(self._urls.market_quote_order_book_url(), params=params)
