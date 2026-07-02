"""Upstox mutual funds REST client."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxMutualFundsClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_holdings(self) -> list[dict[str, Any]]:
        body = self._http.get_json(self._urls.mutual_funds_holdings_url())
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            data = body.get("data")
            return data if isinstance(data, list) else []
        return []

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post_json(self._urls.mutual_funds_order_url(), payload)
