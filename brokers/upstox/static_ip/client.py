"""Upstox static IP REST client."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxStaticIpClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_static_ip(self) -> dict[str, str]:
        return self._http.get_json(self._urls.static_ip_url())

    def set_static_ip(self, primary: str, secondary: str | None = None) -> dict[str, str]:
        payload: dict[str, Any] = {"ip": primary}
        if secondary:
            payload["secondary_ip"] = secondary
        return self._http.put_json(self._urls.static_ip_url(), payload)
