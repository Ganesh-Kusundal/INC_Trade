"""Upstox futures adapter — implements ``FuturesProvider`` port."""

from __future__ import annotations

from typing import Any

from brokers.common.gateway_interfaces import FuturesProvider
from brokers.upstox.market_data.futures import UpstoxFuturesClient


class UpstoxFuturesAdapter(FuturesProvider):
    def __init__(self, client: UpstoxFuturesClient) -> None:
        self._client = client

    def get_contracts(self, underlying: str, exchange_segment: Any) -> list[Any]:
        return self._client.get_contracts(underlying, str(exchange_segment))

    def get_nearest_contract(self, underlying: str, exchange_segment: Any) -> Any:
        return self._client.get_nearest_contract(underlying, str(exchange_segment))

    def get_expiries(self, underlying: str, exchange_segment: Any) -> list[Any]:
        return self._client.get_expiries(underlying, str(exchange_segment))

    def is_commodity(self, underlying: str) -> bool:
        return self._client.is_commodity(underlying)
