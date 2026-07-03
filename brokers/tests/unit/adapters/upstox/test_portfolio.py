"""Unit tests for Upstox portfolio adapter."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from brokers.adapters.upstox.portfolio import UpstoxPortfolio
from brokers.domain import Balance, Holding, Position, Trade


class TestUpstoxPortfolio:
    def setup_method(self):
        self.client = MagicMock()
        self.urls = MagicMock()
        self.portfolio = UpstoxPortfolio(self.client, self.urls)

    def test_positions_returns_mapped_list(self):
        self.client.get.return_value = {
            "data": [
                {"trading_symbol": "RELIANCE", "exchange": "NSE", "net_quantity": 10}
            ]
        }
        result = self.portfolio.positions()
        assert len(result) == 1
        assert isinstance(result[0], Position)
        assert result[0].symbol == "RELIANCE"
        self.client.get.assert_called_once_with(self.urls.positions_url())

    def test_positions_empty_data(self):
        self.client.get.return_value = {"data": []}
        result = self.portfolio.positions()
        assert result == []

    def test_positions_missing_data_key(self):
        self.client.get.return_value = {}
        result = self.portfolio.positions()
        assert result == []

    def test_holdings_returns_mapped_list(self):
        self.client.get.return_value = {
            "data": [
                {"trading_symbol": "INFY", "exchange": "NSE", "quantity": 50}
            ]
        }
        result = self.portfolio.holdings()
        assert len(result) == 1
        assert isinstance(result[0], Holding)
        assert result[0].symbol == "INFY"
        self.client.get.assert_called_once_with(self.urls.holdings_url())

    def test_holdings_empty_data(self):
        self.client.get.return_value = {"data": []}
        result = self.portfolio.holdings()
        assert result == []

    def test_holdings_missing_data_key(self):
        self.client.get.return_value = {}
        result = self.portfolio.holdings()
        assert result == []

    def test_funds_returns_balance(self):
        self.client.get.return_value = {
            "data": {
                "equity": {
                    "available_margin": "50000.00",
                    "used_margin": "10000.00",
                    "net_margin": "60000.00",
                }
            }
        }
        result = self.portfolio.funds()
        assert isinstance(result, Balance)
        assert result.available_cash == Decimal("50000.00")
        self.client.get.assert_called_once_with(self.urls.funds_url())

    def test_trades_returns_mapped_list(self):
        self.client.get.return_value = {
            "data": [
                {
                    "trade_id": "T1",
                    "order_id": "O1",
                    "trading_symbol": "TCS",
                    "exchange": "NSE",
                    "transaction_type": "BUY",
                    "quantity": 10,
                    "average_price": "3500.00",
                }
            ]
        }
        result = self.portfolio.trades()
        assert len(result) == 1
        assert isinstance(result[0], Trade)
        assert result[0].trade_id == "T1"
        self.client.get.assert_called_once_with(self.urls.trades_for_day_url())

    def test_trades_empty_data(self):
        self.client.get.return_value = {"data": []}
        result = self.portfolio.trades()
        assert result == []

    def test_trades_missing_data_key(self):
        self.client.get.return_value = {}
        result = self.portfolio.trades()
        assert result == []
