"""Upstox expired instruments — expired option contract data.

API: GET /v2/options/expired-instruments — get expired option expiries
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxExpiredInstruments:
    """Expired instrument data for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_expiries(self, instrument_key: str) -> list[dict[str, Any]]:
        data = self._client.get(f"/v2/options/expired-instruments?instrument_key={instrument_key}")
        result = data.get("data", data) if isinstance(data, dict) else data
        return result if isinstance(result, list) else []

    def get_option_contract(self, instrument_key: str, expiry: str) -> dict[str, Any]:
        endpoint = f"/v2/options/contract?instrument_key={instrument_key}&expiry={expiry}"
        data = self._client.get(endpoint)
        return data.get("data", data) if isinstance(data, dict) else {}  # type: ignore[no-any-return]


__all__ = ["UpstoxExpiredInstruments"]
