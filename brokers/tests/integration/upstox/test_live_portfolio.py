"""Live integration tests — portfolio endpoints."""

from __future__ import annotations

from decimal import Decimal

from brokers.tests.integration.upstox.conftest import skip_live


@skip_live
class TestLivePortfolio:
    def test_funds_returns_balance(self, gateway):
        balance = gateway.portfolio.funds()
        assert balance is not None
        assert isinstance(balance.available_cash, Decimal)

    def test_positions_returns_list(self, gateway):
        positions = gateway.portfolio.positions()
        assert isinstance(positions, list)

    def test_holdings_returns_list(self, gateway):
        holdings = gateway.portfolio.holdings()
        assert isinstance(holdings, list)

    def test_trades_returns_list(self, gateway):
        trades = gateway.portfolio.trades()
        assert isinstance(trades, list)

    def test_connection_status(self, gateway):
        status = gateway.get_connection_status()
        assert "market_data_ws" in status
        assert "portfolio_stream" in status
