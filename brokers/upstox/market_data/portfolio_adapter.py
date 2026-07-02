"""Upstox portfolio adapter — implements ``PortfolioProvider`` port."""

from __future__ import annotations

from datetime import date
from typing import Any

from brokers.common.gateway_interfaces import PortfolioProvider
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.market_data.portfolio_client import UpstoxPortfolioClient
from domain import FundLimits, Holding, Position


class UpstoxPortfolioAdapter(PortfolioProvider):
    def __init__(self, client: UpstoxPortfolioClient) -> None:
        self._client = client

    def get_balance(self) -> Any:
        """Get account balance/fund limits."""
        from decimal import Decimal

        from domain import Balance

        funds = self._client.get_funds()
        data = funds.get("data", {}) if isinstance(funds, dict) else {}
        equity = data.get("equity", {}) if isinstance(data, dict) else {}

        available = equity.get("available_margin", equity.get("available_cash", 0))
        total = equity.get("net_margin", equity.get("net", 0))
        used = equity.get("used_margin", equity.get("used", 0))

        return Balance(
            available_balance=Decimal(str(available)),
            used_margin=Decimal(str(used)),
            total_margin=Decimal(str(total)),
        )

    def get_positions(self) -> list[Position]:
        rows = self._client.get_short_term_positions()
        return [UpstoxDomainMapper.to_position(r) for r in rows]

    def get_holdings(self) -> list[Holding]:
        rows = self._client.get_long_term_holdings()
        return [UpstoxDomainMapper.to_holding(r) for r in rows]

    def get_fund_limits(self) -> FundLimits:
        return UpstoxDomainMapper.to_fund_limits(self._client.get_funds())

    def get_profile(self) -> dict[str, Any]:
        return self._client.get_profile()

    def get_ledger(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        return []
