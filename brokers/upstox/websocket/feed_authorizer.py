"""Upstox V3 WebSocket feed authorizer + portfolio stream authorizer.

Mirrors Trade_J ``UpstoxFeedAuthorizer``.
"""

from __future__ import annotations

import json
from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxFeedAuthorizer:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def authorize_market_data_v2(self) -> str:
        body = self._http.get_json(self._urls.feed_authorize_v2_url())
        return _extract_authorized_url(body)

    def authorize_market_data_v3(self) -> str:
        body = self._http.get_json(self._urls.feed_authorize_v3_url())
        return _extract_authorized_url(body)

    def authorize_portfolio_stream(self, update_types: list[str] | None = None) -> str:
        types = update_types or ["order", "position", "holding", "gtt_order"]
        params = {"update_types": ",".join(types)}
        body = self._http.get_json(self._urls.portfolio_stream_authorize_url(), params=params)
        return _extract_authorized_url(body)


def _extract_authorized_url(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    data = body.get("data")
    if isinstance(data, dict):
        url = data.get("authorized_redirect_uri") or data.get("redirect_uri")
        if url:
            return str(url)
    return str(body.get("authorized_redirect_uri") or body.get("redirect_uri") or "")


def build_subscribe_payload(
    instrument_keys: list[str],
    mode: str,
    *,
    guid: str | None = None,
) -> dict[str, Any]:
    """Build the JSON-encoded subscribe payload that the V3 server expects
    in a binary WebSocket frame."""
    return {
        "guid": guid or "",
        "method": "sub",
        "data": {
            "mode": mode,
            "instrumentKeys": list(instrument_keys),
        },
    }


def encode_subscribe_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")
