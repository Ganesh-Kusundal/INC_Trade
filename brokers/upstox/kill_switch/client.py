"""Upstox kill switch REST client."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxKillSwitchClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_status(self) -> dict[str, Any]:
        return self._http.get_json(self._urls.kill_switch_url())

    def set_status(self, updates: list[dict[str, str]]) -> dict[str, Any]:
        payload = {"kill_switch_status": updates}
        return self._http.put_json(self._urls.kill_switch_url(), payload)
