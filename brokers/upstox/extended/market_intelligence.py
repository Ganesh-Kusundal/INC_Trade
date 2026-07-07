"""Upstox market intelligence — PCR, max pain, OI, FII/DII flow.

API: GET /v2/market-intelligence/pcr
     GET /v2/market-intelligence/max-pain
     GET /v2/market-intelligence/oi
     GET /v2/market-intelligence/fii-dii
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxMarketIntelligence:
    """Market intelligence data for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_pcr(self, instrument_key: str = "") -> dict[str, Any]:
        endpoint = "/v2/market-intelligence/pcr"
        if instrument_key:
            endpoint += f"?instrument_key={instrument_key}"
        return self._get(endpoint)

    def get_max_pain(self, instrument_key: str = "") -> dict[str, Any]:
        endpoint = "/v2/market-intelligence/max-pain"
        if instrument_key:
            endpoint += f"?instrument_key={instrument_key}"
        return self._get(endpoint)

    def get_oi(self, instrument_key: str = "") -> dict[str, Any]:
        endpoint = "/v2/market-intelligence/oi"
        if instrument_key:
            endpoint += f"?instrument_key={instrument_key}"
        return self._get(endpoint)

    def get_fii_dii(self) -> dict[str, Any]:
        return self._get("/v2/market-intelligence/fii-dii")

    def _get(self, endpoint: str) -> dict[str, Any]:
        data = self._client.get(endpoint)
        return data.get("data", data) if isinstance(data, dict) else {}  # type: ignore[no-any-return]


__all__ = ["UpstoxMarketIntelligence"]
