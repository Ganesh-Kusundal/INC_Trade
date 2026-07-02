"""Upstox market status + holidays client."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxMarketStatusClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_market_status(self, exchange: str = "NSE") -> dict[str, Any]:
        return self._http.get_json(self._urls.market_status_url(exchange))

    def get_market_status_all(self) -> dict[str, Any]:
        return self._http.get_json(self._urls.market_status_url(""))

    def get_holidays(self) -> list[dict[str, Any]]:
        body = self._http.get_json(self._urls.market_holidays_url())
        if not isinstance(body, list):
            return (
                body.get("data")
                if isinstance(body, dict) and isinstance(body.get("data"), list)
                else []
            )
        return body
