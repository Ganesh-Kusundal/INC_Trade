"""Tests for Trade P&L calculator."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.upstox.market_data.trade_pnl import TradePnL, TradePnLCalculator


@pytest.fixture
def mock_portfolio_client():
    client = MagicMock()
    client.get_short_term_positions.return_value = [
        {
            "trading_symbol": "RELIANCE",
            "exchange": "NSE",
            "quantity": 10,
            "average_price": 2450.00,
            "last_price": 2500.00,
            "instrument_key": "NSE_EQ|INE002A01018",
        },
        {
            "trading_symbol": "TCS",
            "exchange": "NSE",
            "quantity": 5,
            "average_price": 3500.00,
            "last_price": 3450.00,
            "instrument_key": "NSE_EQ|INE467B01029",
        },
    ]
    return client


@pytest.fixture
def mock_market_data_client():
    client = MagicMock()
    client.get_ltp.return_value = {
        "status": "success",
        "data": {
            "NSE_EQ|INE002A01018": {"last_price": 2500.00},
            "NSE_EQ|INE467B01029": {"last_price": 3450.00},
        },
    }
    return client


class TestTradePnLCalculator:
    def test_calculate_all_pnl_returns_list(self, mock_portfolio_client, mock_market_data_client):
        calculator = TradePnLCalculator(mock_portfolio_client, mock_market_data_client)
        result = calculator.calculate_all_pnl()

        assert isinstance(result, list)
        assert len(result) == 2

    def test_pnl_calculation_profit(self, mock_portfolio_client, mock_market_data_client):
        calculator = TradePnLCalculator(mock_portfolio_client, mock_market_data_client)
        result = calculator.calculate_all_pnl()

        # RELIANCE: bought at 2450, current 2500, quantity 10
        reliance = next(p for p in result if p.symbol == "RELIANCE")
        assert reliance.quantity == 10
        assert reliance.average_price == Decimal("2450.00")
        assert reliance.current_price == Decimal("2500.00")
        assert reliance.unrealized_pnl == Decimal("500.00")  # (2500 - 2450) * 10
        assert reliance.pnl_percentage > 0

    def test_pnl_calculation_loss(self, mock_portfolio_client, mock_market_data_client):
        calculator = TradePnLCalculator(mock_portfolio_client, mock_market_data_client)
        result = calculator.calculate_all_pnl()

        # TCS: bought at 3500, current 3450, quantity 5
        tcs = next(p for p in result if p.symbol == "TCS")
        assert tcs.quantity == 5
        assert tcs.average_price == Decimal("3500.00")
        assert tcs.current_price == Decimal("3450.00")
        assert tcs.unrealized_pnl == Decimal("-250.00")  # (3450 - 3500) * 5
        assert tcs.pnl_percentage < 0

    def test_empty_positions(self, mock_market_data_client):
        mock_portfolio = MagicMock()
        mock_portfolio.get_short_term_positions.return_value = []

        calculator = TradePnLCalculator(mock_portfolio, mock_market_data_client)
        result = calculator.calculate_all_pnl()

        assert isinstance(result, list)
        assert len(result) == 0

    def test_zero_quantity_position_skipped(self, mock_market_data_client):
        mock_portfolio = MagicMock()
        mock_portfolio.get_short_term_positions.return_value = [
            {
                "trading_symbol": "RELIANCE",
                "exchange": "NSE",
                "quantity": 0,
                "average_price": 2450.00,
                "last_price": 2500.00,
            }
        ]

        calculator = TradePnLCalculator(mock_portfolio, mock_market_data_client)
        result = calculator.calculate_all_pnl()

        assert len(result) == 0

    def test_fallback_to_last_price_on_error(self, mock_portfolio_client):
        mock_market_data = MagicMock()
        mock_market_data.get_ltp.side_effect = Exception("API Error")

        calculator = TradePnLCalculator(mock_portfolio_client, mock_market_data)
        result = calculator.calculate_all_pnl()

        # Should fallback to last_price from position data
        assert len(result) == 2
        reliance = next(p for p in result if p.symbol == "RELIANCE")
        assert reliance.current_price == Decimal("2500.00")


class TestTradePnLDataclass:
    def test_trade_pnl_is_frozen(self):
        pnl = TradePnL(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            average_price=Decimal("2450.00"),
            current_price=Decimal("2500.00"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("500.00"),
            total_pnl=Decimal("500.00"),
            pnl_percentage=Decimal("2.04"),
        )

        # Verify frozen
        with pytest.raises(AttributeError):
            pnl.symbol = "TCS"

    def test_trade_pnl_fields(self):
        pnl = TradePnL(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            average_price=Decimal("2450.00"),
            current_price=Decimal("2500.00"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("500.00"),
            total_pnl=Decimal("500.00"),
            pnl_percentage=Decimal("2.04"),
        )

        assert pnl.symbol == "RELIANCE"
        assert pnl.exchange == "NSE"
        assert pnl.quantity == 10
        assert pnl.unrealized_pnl == Decimal("500.00")
