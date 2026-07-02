"""Upstox fundamentals REST client."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxFundamentalsClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_financials(self, isin: str, statement: str = "P&L") -> dict[str, Any]:
        return self._http.get_json(self._urls.fundamentals_financials_url(isin, statement))

    def get_balance_sheet(self, isin: str) -> dict[str, Any]:
        return self.get_financials(isin, statement="balance_sheet")

    def get_pnl(self, isin: str) -> dict[str, Any]:
        return self.get_financials(isin, statement="P&L")

    def get_cash_flow(self, isin: str) -> dict[str, Any]:
        return self.get_financials(isin, statement="cash_flow")

    def get_ratios(self, isin: str) -> dict[str, Any]:
        return self.get_financials(isin, statement="ratios")
