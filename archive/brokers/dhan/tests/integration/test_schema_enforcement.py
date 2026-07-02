"""Schema enforcement tests for Dhan broker endpoints.

Ensures all endpoints return data with the correct schema.
Catches broker API changes that break the contract.

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.factory import BrokerFactory
from brokers.dhan.gateway import BrokerGateway

pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestSchemaEnforcement:
    """Schema enforcement tests for all Dhan endpoint responses."""

    def test_quote_schema(self, gateway: BrokerGateway):
        """Quote must have: symbol, ltp, open, high, low, close, volume, change."""
        quote = gateway.quote("RELIANCE", "NSE")
        required_fields = ["symbol", "ltp", "open", "high", "low", "close", "volume", "change"]
        for field in required_fields:
            assert hasattr(quote, field), f"Quote missing field: {field}"
        # Type checks
        assert isinstance(quote.ltp, (int, float, Decimal))
        assert isinstance(quote.volume, (int, float))

    def test_market_depth_schema(self, gateway: BrokerGateway):
        """MarketDepth must have: bids (list), asks (list)."""
        depth = gateway.depth("RELIANCE", "NSE")
        assert hasattr(depth, "bids")
        assert hasattr(depth, "asks")
        assert isinstance(depth.bids, list)
        assert isinstance(depth.asks, list)
        # DepthLevel schema
        if depth.bids:
            level = depth.bids[0]
            assert hasattr(level, "price")
            assert hasattr(level, "quantity")
            assert hasattr(level, "orders")

    def test_balance_schema(self, gateway: BrokerGateway):
        """Balance must have: available_balance, used_margin, total_margin."""
        balance = gateway.funds()
        required_fields = ["available_balance", "used_margin", "total_margin"]
        for field in required_fields:
            assert hasattr(balance, field), f"Balance missing field: {field}"
        # Type checks
        assert isinstance(balance.available_balance, (int, float, Decimal))

    def test_order_schema(self, gateway: BrokerGateway):
        """Order must have: order_id, symbol, exchange, side, quantity, status."""
        orderbook = gateway.get_orderbook()
        if orderbook:
            order = orderbook[0]
            required_fields = ["order_id", "symbol", "exchange", "side", "quantity", "status"]
            for field in required_fields:
                assert hasattr(order, field), f"Order missing field: {field}"

    def test_position_schema(self, gateway: BrokerGateway):
        """Position must have: symbol, exchange, quantity, average_price."""
        positions = gateway.positions()
        if positions:
            pos = positions[0]
            required_fields = ["symbol", "exchange", "quantity", "average_price"]
            for field in required_fields:
                assert hasattr(pos, field), f"Position missing field: {field}"

    def test_holding_schema(self, gateway: BrokerGateway):
        """Holding must have: symbol, exchange, quantity."""
        holdings = gateway.holdings()
        if holdings:
            holding = holdings[0]
            required_fields = ["symbol", "exchange", "quantity"]
            for field in required_fields:
                assert hasattr(holding, field), f"Holding missing field: {field}"

    def test_trade_schema(self, gateway: BrokerGateway):
        """Trade must have: symbol, exchange, quantity, price."""
        trades = gateway.trades()
        if trades:
            trade = trades[0]
            required_fields = ["symbol", "exchange", "quantity", "price"]
            for field in required_fields:
                assert hasattr(trade, field), f"Trade missing field: {field}"

    def test_history_dataframe_schema(self, gateway: BrokerGateway):
        """history() DataFrame must have: timestamp, open, high, low, close, volume."""
        df = gateway.history("RELIANCE", "NSE", timeframe="1D", lookback_days=3)
        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            assert col in df.columns, f"History DataFrame missing column: {col}"

    def test_option_chain_schema(self, gateway: BrokerGateway):
        """OptionChain must have: spot, strikes."""
        chain = gateway.option_chain("NIFTY", "NFO")
        assert hasattr(chain, "spot")
        assert hasattr(chain, "strikes")
        assert chain.spot > 0
        assert isinstance(chain.strikes, (list, tuple))

    def test_future_chain_schema(self, gateway: BrokerGateway):
        """FutureChain must have: underlying, expiries, contracts."""
        chain = gateway.future_chain("NIFTY", "NFO")
        assert hasattr(chain, "underlying")
        assert hasattr(chain, "expiries")
        assert hasattr(chain, "contracts")
        assert chain.underlying
        assert isinstance(chain.expiries, (list, tuple))
        assert isinstance(chain.contracts, (list, tuple))

    def test_search_result_schema(self, gateway: BrokerGateway):
        """Search results must have: symbol, exchange, type, security_id."""
        results = gateway.search("RELIANCE")
        if results:
            result = results[0]
            required_fields = ["symbol", "exchange", "type", "security_id"]
            for field in required_fields:
                assert field in result, f"Search result missing field: {field}"

    def test_order_response_schema(self, gateway: BrokerGateway):
        """OrderResponse must have: success, message."""
        response = gateway.place_order(
            symbol="INVALID123",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="LIMIT",
            product_type="INTRADAY",
            price=Decimal("100"),
        )
        assert hasattr(response, "success")
        assert hasattr(response, "message")
        assert isinstance(response.success, bool)
