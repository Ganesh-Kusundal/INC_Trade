"""Upstox mutual funds adapter."""

from __future__ import annotations

from typing import Any

from brokers.upstox.mutual_funds.client import UpstoxMutualFundsClient


class UpstoxMutualFundsAdapter:
    def __init__(self, client: UpstoxMutualFundsClient) -> None:
        self._client = client

    def get_holdings(self) -> list[dict[str, Any]]:
        return self._client.get_holdings()

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.place_order(payload)
