"""Upstox fundamentals — financial data (PnL, balance sheet, cash flow, ratios).

API: GET /v2/fundamentals/{isin}/pnl
     GET /v2/fundamentals/{isin}/balance_sheet
     GET /v2/fundamentals/{isin}/cash_flow
     GET /v2/fundamentals/{isin}/ratios
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxFundamentals:
    """Fundamental data retrieval for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_pnl(self, isin: str) -> dict[str, Any]:
        return self._get_financials(isin, "pnl")

    def get_balance_sheet(self, isin: str) -> dict[str, Any]:
        return self._get_financials(isin, "balance_sheet")

    def get_cash_flow(self, isin: str) -> dict[str, Any]:
        return self._get_financials(isin, "cash_flow")

    def get_ratios(self, isin: str) -> dict[str, Any]:
        return self._get_financials(isin, "ratios")

    def _get_financials(self, isin: str, statement: str) -> dict[str, Any]:
        data = self._client.get(f"/v2/fundamentals/{isin}/{statement}")
        return data.get("data", data) if isinstance(data, dict) else {}  # type: ignore[no-any-return]


__all__ = ["UpstoxFundamentals"]
