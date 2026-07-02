"""Upstox margin calculator client."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxMarginClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def calculate_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post_json(self._urls.margin_requirement_url(), payload)

    def get_brokerage(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post_json(self._urls.charges_brokerage_url(), payload)
