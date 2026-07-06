"""Contract tests — verify any portfolio adapter satisfies the PortfolioPort protocol."""

from __future__ import annotations

from decimal import Decimal

import pytest
from inc_trade.domain import Balance, Holding, Position, Trade
from inc_trade.ports import PortfolioPort


class _FakePortfolio:
    def positions(self) -> list[Position]:
        return []

    def holdings(self) -> list[Holding]:
        return []

    def funds(self) -> Balance:
        return Balance(available_cash=Decimal("50000.00"))

    def trades(self) -> list[Trade]:
        return []


@pytest.mark.contract
class TestPortfolioContract:
    def test_satisfies_protocol(self):
        adapter = _FakePortfolio()
        assert isinstance(adapter, PortfolioPort)

    def test_positions_returns_list(self):
        adapter = _FakePortfolio()
        result = adapter.positions()
        assert isinstance(result, list)

    def test_holdings_returns_list(self):
        adapter = _FakePortfolio()
        result = adapter.holdings()
        assert isinstance(result, list)

    def test_funds_returns_balance(self):
        adapter = _FakePortfolio()
        result = adapter.funds()
        assert isinstance(result, Balance)
        assert result.available_cash == Decimal("50000.00")

    def test_trades_returns_list(self):
        adapter = _FakePortfolio()
        result = adapter.trades()
        assert isinstance(result, list)
