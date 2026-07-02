"""Upstox market intelligence adapter — implements ``MarketIntelligencePort``."""

from __future__ import annotations

from typing import Any

from brokers.common.gateway_interfaces import MarketIntelligencePort
from brokers.upstox.market_intelligence.client import UpstoxMarketIntelligenceClient


class UpstoxMarketIntelligenceAdapter(MarketIntelligencePort):
    def __init__(self, client: UpstoxMarketIntelligenceClient) -> None:
        self._client = client

    def get_pcr(
        self,
        instrument_key: str,
        expiry: str,
        date: str,
        bucket_interval: int = 1,
    ) -> dict[str, Any]:
        return self._client.get_pcr(instrument_key, expiry, date, bucket_interval)

    def get_max_pain(
        self,
        instrument_key: str,
        expiry: str,
        date: str,
        bucket_interval: int = 1,
    ) -> dict[str, Any]:
        return self._client.get_max_pain(instrument_key, expiry, date, bucket_interval)

    def get_oi(self, instrument_key: str, expiry: str, date: str) -> dict[str, Any]:
        return self._client.get_oi(instrument_key, expiry, date)

    def get_fii_flow(
        self, data_type: str = "NSE_FO|INDEX_FUTURES", interval: str = "1D"
    ) -> dict[str, Any]:
        return self._client.get_fii_flow(data_type, interval)

    def get_dii_flow(self, interval: str = "1D") -> dict[str, Any]:
        return self._client.get_dii_flow(interval)

    def get_smartlist(
        self,
        kind: str,
        asset_type: str = "INDEX",
        category: str = "TOP_TRADED",
    ) -> dict[str, Any]:
        if kind == "futures":
            return self._client.get_smartlist_futures(asset_type, category)
        return self._client.get_smartlist_options(asset_type, category)
