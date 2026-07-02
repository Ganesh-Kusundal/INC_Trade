"""Upstox IPO REST client."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxIpoClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_ipo_data(self, status: str = "open") -> list[dict[str, Any]]:
        body = self._http.get_json(self._urls.ipo_url(), params={"status": status})
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            data = body.get("data")
            return data if isinstance(data, list) else []
        return []
