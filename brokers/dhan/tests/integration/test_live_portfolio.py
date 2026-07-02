"""Live integration tests for Dhan portfolio and account endpoints.

Tests funds(), positions(), holdings(), trades(), describe(), and capabilities()
against the live Dhan API.

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.factory import BrokerFactory

pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]
from brokers.dhan.gateway import BrokerGateway

# ---------------------------------------------------------------------------
# Skip guard — only run when .env.local has valid credentials
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLivePortfolio:
    """End-to-end portfolio and account endpoint tests against live Dhan API."""

    def test_funds_returns_balance(self, gateway: BrokerGateway):
        """funds() should return a Balance object with available_balance > 0."""
        balance = gateway.funds()
        assert balance is not None
        assert hasattr(balance, "available_balance")
        assert balance.available_balance > 0

    def test_funds_balance_schema(self, gateway: BrokerGateway):
        """Balance should have required fields: available_balance, used_margin, total_margin."""
        balance = gateway.funds()
        assert hasattr(balance, "available_balance")
        assert hasattr(balance, "used_margin")
        assert hasattr(balance, "total_margin")

    def test_positions_returns_list(self, gateway: BrokerGateway):
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

    def test_holdings_returns_list(self, gateway: BrokerGateway):
        """holdings() should return a list (can be empty) of Holding objects."""
        holdings = gateway.holdings()
        assert isinstance(holdings, list)
        # If holdings exist, verify schema
        if holdings:
            holding = holdings[0]
            assert hasattr(holding, "symbol")
            assert hasattr(holding, "exchange")
            assert hasattr(holding, "quantity")

    def test_trades_returns_list(self, gateway: BrokerGateway):
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

    def test_get_trade_book_returns_list(self, gateway: BrokerGateway):
        """get_trade_book() should return same result as trades()."""
        trade_book = gateway.get_trade_book()
        assert isinstance(trade_book, list)

    def test_describe_returns_metadata(self, gateway: BrokerGateway):
        """describe() should return dict with broker metadata."""
        desc = gateway.describe()
        assert isinstance(desc, dict)
        assert desc.get("broker") == "Dhan"
        assert "instruments_loaded" in desc
        assert "instrument_count" in desc

    def test_describe_instrument_count(self, gateway: BrokerGateway):
        """describe() should show instruments loaded with count > 0."""
        desc = gateway.describe()
        assert desc["instruments_loaded"] is True
        assert desc["instrument_count"] > 0

    def test_capabilities_returns_matrix(self, gateway: BrokerGateway):
        """capabilities() should return BrokerCapabilities object."""
        caps = gateway.capabilities()
        assert caps is not None
        # Verify it has expected capability flags
        assert hasattr(caps, "broker_id")
        assert hasattr(caps, "supports_live_market_data")
        assert hasattr(caps, "supports_place_order")
        assert caps.broker_id == "dhan"
