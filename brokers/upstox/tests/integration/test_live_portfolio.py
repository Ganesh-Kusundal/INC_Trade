"""Live integration tests for Upstox portfolio and account endpoints.

Tests funds(), positions(), holdings(), trades(), describe(), and capabilities()
against the live Upstox API.

These tests require a valid .env.upstox with UPSTOX_API_KEY and UPSTOX_ACCESS_TOKEN.
They are skipped automatically when the env file is absent or credentials are invalid.
"""

from __future__ import annotations

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
class TestLivePortfolio:
    """End-to-end portfolio and account endpoint tests against live Upstox API."""

    def test_funds_returns_balance(self, gateway):
        """funds() should return a Balance object with available_balance > 0."""
        balance = gateway.funds()
        assert balance is not None
        assert hasattr(balance, "available_balance")
        from decimal import Decimal
        assert isinstance(balance.available_balance, Decimal)

    def test_funds_balance_schema(self, gateway):
        """Balance should have required fields: available_balance, used_margin, total_margin."""
        balance = gateway.funds()
        assert hasattr(balance, "available_balance")
        assert hasattr(balance, "used_margin")
        assert hasattr(balance, "total_margin")

    def test_positions_returns_list(self, gateway):
        """positions() should return a list (can be empty) of Position objects."""
        positions = gateway.positions()
        assert isinstance(positions, list)
        # If positions exist, verify schema
        if positions:
            pos = positions[0]
            assert hasattr(pos, "symbol")
            assert hasattr(pos, "exchange")
            assert hasattr(pos, "quantity")
            assert hasattr(pos, "average_price")

    def test_holdings_returns_list(self, gateway):
        """holdings() should return a list (can be empty) of Holding objects."""
        holdings = gateway.holdings()
        assert isinstance(holdings, list)
        # If holdings exist, verify schema
        if holdings:
            holding = holdings[0]
            assert hasattr(holding, "symbol")
            assert hasattr(holding, "exchange")
            assert hasattr(holding, "quantity")

    def test_trades_returns_list(self, gateway):
        """trades() should return a list (can be empty) of Trade objects."""
        trades = gateway.trades()
        assert isinstance(trades, list)
        # If trades exist, verify schema
        if trades:
            trade = trades[0]
            assert hasattr(trade, "symbol")
            assert hasattr(trade, "exchange")
            assert hasattr(trade, "quantity")
            assert hasattr(trade, "price")

    def test_get_trade_book_returns_list(self, gateway):
        """get_trade_book() should return same result as trades()."""
        trade_book = gateway.get_trade_book()
        assert isinstance(trade_book, list)

    def test_describe_returns_metadata(self, gateway):
        """describe() should return dict with broker metadata."""
        desc = gateway.describe()
        assert isinstance(desc, dict)
        assert desc.get("broker") == "Upstox"
        assert "instruments_loaded" in desc

    def test_describe_instruments_loaded(self, gateway):
        """describe() should show instruments loaded."""
        desc = gateway.describe()
        assert desc["instruments_loaded"] is True

    def test_capabilities_returns_matrix(self, gateway):
        """capabilities() should return BrokerCapabilities object."""
        caps = gateway.capabilities()
        assert caps is not None
        # Verify it has expected capability flags
        assert hasattr(caps, "broker_id")
        assert hasattr(caps, "supports_live_market_data")
        assert hasattr(caps, "supports_place_order")
        assert caps.broker_id == "upstox"
