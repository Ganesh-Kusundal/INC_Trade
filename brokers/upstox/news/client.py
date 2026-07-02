"""Upstox news REST client."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxNewsClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_news(
        self,
        category: str = "holdings",
        symbol: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        instrument_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"category": category}
        if instrument_keys and category == "instrument_keys":
            params["instrument_keys"] = ",".join(instrument_keys)
        if symbol:
            params["symbol"] = symbol
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        body = self._http.get_json(self._urls.news_url(), params=params)
        if isinstance(body, dict):
            data = body.get("data", {})
            if isinstance(data, dict):
                all_news = []
                for _key, items in data.items():
                    if isinstance(items, list):
                        all_news.extend(items)
                return all_news
            if isinstance(data, list):
                return data
        if isinstance(body, list):
            return body
        return []

    def get_news_for_instruments(self, instrument_keys: list[str]) -> dict[str, Any]:
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        return self._http.get_json(
            self._urls.news_url(),
            params={"category": "instrument_keys", "instrument_keys": ",".join(instrument_keys)},
        )
