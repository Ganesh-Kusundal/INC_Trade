"""Upstox V3 historical candle client.

Supports custom intervals: minutes (1-300), hours (1-5), days, weeks, months.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)


class UpstoxHistoricalV3Client:
    def __init__(self, http_client: Any, url_resolver: Any = None) -> None:
        self._http = http_client
        self._urls = url_resolver
        self._base_url = "https://api.upstox.com/v3" if url_resolver is None else None

    def _get_base_url(self) -> str:
        if self._urls is not None:
            return self._urls._v3()
        return self._base_url

    def get_candles(
        self,
        instrument_key: str,
        unit: str,
        interval: str,
        to_date: date,
        from_date: date | None = None,
    ) -> dict[str, Any]:
        """Fetch historical candles using V3 API.

        Args:
            instrument_key: e.g., 'NSE_EQ|INE002A01018' (will be URL-encoded)
            unit: 'minutes', 'hours', 'days', 'weeks', 'months'
            interval: '1', '5', '15', '30', '60' etc.
            to_date: End date
            from_date: Start date (optional)
        """
        # URL-encode the instrument key (contains pipe character)
        encoded_key = quote(instrument_key, safe="")
        base = self._get_base_url()
        url = f"{base}/historical-candle/{encoded_key}/{unit}/{interval}/{to_date.isoformat()}"
        if from_date:
            url += f"/{from_date.isoformat()}"

        logger.debug("Fetching historical candles: %s", url)
        return self._http.get_json(url)

    def get_intraday_candles(
        self,
        instrument_key: str,
        unit: str,
        interval: str,
        to_date: date,
    ) -> dict[str, Any]:
        """Fetch intraday candles using V3 API."""
        encoded_key = quote(instrument_key, safe="")
        base = self._get_base_url()
        url = f"{base}/intraday-candle/{encoded_key}/{unit}/{interval}/{to_date.isoformat()}"
        return self._http.get_json(url)
