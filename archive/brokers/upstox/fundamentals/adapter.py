"""Upstox fundamentals adapter."""

from __future__ import annotations

from typing import Any

from brokers.upstox.fundamentals.client import UpstoxFundamentalsClient


class UpstoxFundamentalsAdapter:
    def __init__(self, client: UpstoxFundamentalsClient) -> None:
        self._client = client

    def get_pnl(self, isin: str) -> dict[str, Any]:
        return self._client.get_pnl(isin)

    def get_balance_sheet(self, isin: str) -> dict[str, Any]:
        return self._client.get_balance_sheet(isin)

    def get_cash_flow(self, isin: str) -> dict[str, Any]:
        return self._client.get_cash_flow(isin)

    def get_ratios(self, isin: str) -> dict[str, Any]:
        return self._client.get_ratios(isin)
