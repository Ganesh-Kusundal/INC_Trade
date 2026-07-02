"""REF-006: Gateway contract compliance suite.

Abstract test class that all MarketDataGateway implementations must pass.
Each broker adapter provides a ``gateway`` fixture, and these tests verify
that the returned object conforms to the MarketDataGateway v1.0 contract.

Usage per broker:
    @pytest.fixture
    def gateway():
        return PaperGateway()

    class TestPaperGatewayContract(GatewayContractSuite):
        pass
"""

from __future__ import annotations

from abc import ABC
from decimal import Decimal

import pandas as pd
import pytest

from brokers.common.gateway import BrokerCapabilities, MarketDataGateway
from domain.entities import (
    Balance,
    FutureChain,
    Holding,
    MarketDepth,
    OptionChain,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)


class GatewayContractSuite(ABC):
    """Abstract contract tests for MarketDataGateway implementations.

    Subclasses MUST provide a ``gateway`` fixture that returns an instance
    of their broker's MarketDataGateway.
    """

    @pytest.fixture
    def gateway(self) -> MarketDataGateway:
        raise NotImplementedError("Subclass must provide 'gateway' fixture")

    # -------------------------------------------------------------------
    # Market Data contracts
    # -------------------------------------------------------------------

    def test_history_returns_dataframe(self, gateway: MarketDataGateway):
        df = gateway.history("RELIANCE")
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_history_has_required_columns(self, gateway: MarketDataGateway):
        df = gateway.history("RELIANCE")
        for col in ("open", "high", "low", "close", "volume"):
            assert col in df.columns, f"Missing column: {col}"

    def test_ltp_returns_decimal(self, gateway: MarketDataGateway):
        ltp = gateway.ltp("RELIANCE")
        assert isinstance(ltp, Decimal)

    def test_quote_returns_quote(self, gateway: MarketDataGateway):
        q = gateway.quote("RELIANCE")
        assert isinstance(q, Quote)
        assert q.symbol == "RELIANCE"

    def test_depth_returns_market_depth(self, gateway: MarketDataGateway):
        d = gateway.depth("RELIANCE")
        assert isinstance(d, MarketDepth)
        assert d.symbol == "RELIANCE"

    def test_option_chain_returns_option_chain(self, gateway: MarketDataGateway):
        chain = gateway.option_chain("NIFTY")
        assert isinstance(chain, OptionChain)

    def test_future_chain_returns_future_chain(self, gateway: MarketDataGateway):
        chain = gateway.future_chain("NIFTY")
        assert isinstance(chain, FutureChain)

    # -------------------------------------------------------------------
    # Trading contracts
    # -------------------------------------------------------------------

    def test_place_order_returns_order_response(self, gateway: MarketDataGateway):
        resp = gateway.place_order(
            symbol="RELIANCE",
            side="BUY",
            quantity=1,
            price=Decimal("0"),
            order_type="MARKET",
        )
        assert isinstance(resp, OrderResponse)

    def test_cancel_order_returns_order_response(self, gateway: MarketDataGateway):
        """REF-002: cancel_order must return OrderResponse, not bool."""
        resp = gateway.cancel_order("NONEXISTENT-123")
        assert isinstance(resp, OrderResponse)
        assert resp.success is False  # nonexistent order

    def test_get_orderbook_returns_list(self, gateway: MarketDataGateway):
        orders = gateway.get_orderbook()
        assert isinstance(orders, list)
        assert all(isinstance(o, Order) for o in orders)

    def test_get_trade_book_returns_list(self, gateway: MarketDataGateway):
        trades = gateway.get_trade_book()
        assert isinstance(trades, list)
        assert all(isinstance(t, Trade) for t in trades)

    # -------------------------------------------------------------------
    # Portfolio contracts
    # -------------------------------------------------------------------

    def test_positions_returns_list(self, gateway: MarketDataGateway):
        positions = gateway.positions()
        assert isinstance(positions, list)
        assert all(isinstance(p, Position) for p in positions)

    def test_holdings_returns_list(self, gateway: MarketDataGateway):
        holdings = gateway.holdings()
        assert isinstance(holdings, list)
        assert all(isinstance(h, Holding) for h in holdings)

    def test_funds_returns_balance(self, gateway: MarketDataGateway):
        balance = gateway.funds()
        assert isinstance(balance, Balance)

    def test_trades_returns_list(self, gateway: MarketDataGateway):
        trades = gateway.trades()
        assert isinstance(trades, list)

    # -------------------------------------------------------------------
    # Lifecycle contracts
    # -------------------------------------------------------------------

    def test_capabilities_returns_broker_capabilities(self, gateway: MarketDataGateway):
        cap = gateway.capabilities()
        assert isinstance(cap, BrokerCapabilities)

    def test_describe_returns_dict(self, gateway: MarketDataGateway):
        desc = gateway.describe()
        assert isinstance(desc, dict)
        assert "name" in desc

    def test_close_does_not_raise(self, gateway: MarketDataGateway):
        # close() must not raise — it's called during teardown
        gateway.close()


# ---------------------------------------------------------------------------
# PaperGateway conformance (inline, no separate file needed)
# ---------------------------------------------------------------------------


class TestPaperGatewayContract(GatewayContractSuite):
    """PaperGateway passes the full MarketDataGateway contract."""

    @pytest.fixture
    def gateway(self):
        from brokers.paper.paper_gateway import PaperGateway

        return PaperGateway()
