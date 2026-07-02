"""Upstox portfolio REST client (positions, holdings, funds, profile, MTF)."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxPortfolioClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_short_term_positions(self) -> list[dict[str, Any]]:
        body = self._http.get_json(self._urls.positions_url())
        return _data_list(body)

    def get_long_term_holdings(self) -> list[dict[str, Any]]:
        body = self._http.get_json(self._urls.holdings_url())
        return _data_list(body)

    def get_funds(self) -> dict[str, Any]:
        return self._http.get_json(self._urls.funds_url())

    def get_profile(self) -> dict[str, Any]:
        return self._http.get_json(self._urls.profile_url())

    def convert_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.put_json(self._urls.convert_position_url(), payload)


def _data_list(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    return data if isinstance(data, list) else []
