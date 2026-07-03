"""Upstox WebSocket feed authorizer — obtains authorized WS URLs from REST API."""

from __future__ import annotations

from typing import Any

from brokers.adapters.upstox.urls import resolve_upstox_urls
from brokers.ports.http_client_port import HttpClientPort


def _extract_authorized_url(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    data = body.get("data")
    if isinstance(data, dict):
        url = data.get("authorized_redirect_uri") or data.get("redirect_uri")
        if url:
            return str(url)
    return str(body.get("authorized_redirect_uri") or body.get("redirect_uri") or "")


class UpstoxFeedAuthorizer:
    """Authorize market-data and portfolio WebSocket feeds via Upstox REST API."""

    def __init__(
        self,
        http_client: HttpClientPort,
        *,
        environment: str = "LIVE",
    ) -> None:
        self._http = http_client
        self._urls = resolve_upstox_urls(environment)

    def authorize_market_data_v2(self) -> str:
        body = self._http.get(self._urls.feed_authorize_v2_url())
        return _extract_authorized_url(body)

    def authorize_market_data_v3(self) -> str:
        body = self._http.get(self._urls.feed_authorize_v3_url())
        return _extract_authorized_url(body)

    def authorize_portfolio_stream(self, update_types: list[str] | None = None) -> str:
        types = update_types or ["order", "position", "holding", "gtt_order"]
        params = {"update_types": ",".join(types)}
        body = self._http.get(self._urls.portfolio_stream_authorize_url(), params=params)
        return _extract_authorized_url(body)
