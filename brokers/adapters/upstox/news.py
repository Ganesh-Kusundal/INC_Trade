"""Upstox news adapter — fetches market and instrument news."""

from __future__ import annotations

import logging
from typing import Any

from inc_trade.config.endpoints import _UpstoxUrls
from inc_trade.domain.entities import NewsItem
from inc_trade.ports.http_client_port import HttpClientPort

logger = logging.getLogger(__name__)


def _parse_news_item(raw: dict[str, Any]) -> NewsItem:
    ts = raw.get("timestamp") or raw.get("date") or raw.get("published_at")
    from datetime import datetime

    parsed_ts: datetime | None = None
    if isinstance(ts, str):
        try:
            parsed_ts = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            pass
    elif isinstance(ts, (int, float)):
        try:
            parsed_ts = datetime.fromtimestamp(ts)
        except (ValueError, OSError):
            pass

    return NewsItem(
        headline=str(raw.get("headline", "") or raw.get("title", "")),
        summary=str(raw.get("summary", "") or raw.get("description", "")),
        source=str(raw.get("source", "")),
        timestamp=parsed_ts,
    )


class UpstoxNews:
    """News adapter implementing news retrieval for Upstox."""

    def __init__(self, client: HttpClientPort, urls: _UpstoxUrls) -> None:
        self._client = client
        self._urls = urls

    def get_news(
        self,
        category: str = "holdings",
        symbol: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        instrument_keys: list[str] | None = None,
    ) -> list[NewsItem]:
        params: dict[str, Any] = {"category": category}
        if instrument_keys and category == "instrument_keys":
            params["instrument_keys"] = ",".join(instrument_keys)
        if symbol:
            params["symbol"] = symbol
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        try:
            body = self._client.get(self._urls.news_url(), params=params)
            all_raw: list[dict[str, Any]] = []
            if isinstance(body, dict):
                data = body.get("data", {})
                if isinstance(data, dict):
                    for _key, items in data.items():
                        if isinstance(items, list):
                            all_raw.extend(i for i in items if isinstance(i, dict))
                elif isinstance(data, list):
                    all_raw = [i for i in data if isinstance(i, dict)]
            elif isinstance(body, list):
                all_raw = [i for i in body if isinstance(i, dict)]
            return [_parse_news_item(item) for item in all_raw]
        except Exception as exc:
            logger.warning("Failed to fetch Upstox news: %s", exc)
        return []
