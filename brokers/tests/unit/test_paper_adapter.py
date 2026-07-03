"""Tests for the Paper trading adapter — in-memory broker for testing."""

from __future__ import annotations

from decimal import Decimal

from brokers.adapters.paper.gateway import PaperGateway
from brokers.domain import (
    Side,
)
from brokers.ports import BrokerGateway


class TestPaperGateway:
    def test_satisfies_protocol(self):
        gw = PaperGateway()
        # Use hasattr checks instead of isinstance for protocols with properties
        assert hasattr(gw, "broker_id")
        assert hasattr(gw, "capabilities")
        assert hasattr(gw, "orders")
        assert hasattr(gw, "market_data")
        assert hasattr(gw, "portfolio")
        assert hasattr(gw, "historical")
        assert hasattr(gw, "instruments")
        assert hasattr(gw, "auth")
        assert hasattr(gw, "streaming")
        assert hasattr(gw, "extensions")

    def test_place_order_returns_success(self):
        gw = PaperGateway()
        resp = gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
        assert resp.success
        assert resp.order_id

    def test_place_order_increments_id(self):
        gw = PaperGateway()
        r1 = gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
        r2 = gw.orders.place_order("TCS", "NSE", Side.SELL, 5)
        assert r1.order_id != r2.order_id

    def test_cancel_order(self):
        gw = PaperGateway()
        resp = gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
        cancel = gw.orders.cancel_order(resp.order_id)
        assert cancel.success

    def test_cancel_nonexistent_order(self):
        gw = PaperGateway()
        cancel = gw.orders.cancel_order("NONEXISTENT")
        assert not cancel.success

    def test_get_order(self):
        gw = PaperGateway()
        resp = gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
        order = gw.orders.get_order(resp.order_id)
        assert order is not None
        assert order.order_id == resp.order_id
        assert order.symbol == "RELIANCE"

    def test_get_orderbook(self):
        gw = PaperGateway()
        gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
        gw.orders.place_order("TCS", "NSE", Side.SELL, 5)
        book = gw.orders.get_orderbook()
        assert len(book) == 2

    def test_ltp(self):
        gw = PaperGateway()
        price = gw.market_data.ltp("RELIANCE")
        assert price > Decimal("0")

    def test_quote(self):
        gw = PaperGateway()
        q = gw.market_data.quote("RELIANCE")
        assert q.symbol == "RELIANCE"
        assert q.ltp > Decimal("0")

    def test_depth(self):
        gw = PaperGateway()
        d = gw.market_data.depth("RELIANCE")
        assert d.symbol == "RELIANCE"

    def test_positions_empty_initially(self):
        gw = PaperGateway()
        assert gw.portfolio.positions() == []

    def test_holdings_empty_initially(self):
        gw = PaperGateway()
        assert gw.portfolio.holdings() == []

    def test_funds_returns_balance(self):
        gw = PaperGateway()
        bal = gw.portfolio.funds()
        assert bal.available_cash > Decimal("0")

    def test_trades_empty_initially(self):
        gw = PaperGateway()
        assert gw.portfolio.trades() == []

    def test_instruments_search(self):
        gw = PaperGateway()
        results = gw.instruments.search("REL")
        assert len(results) >= 1

    def test_instruments_resolve(self):
        gw = PaperGateway()
        info = gw.instruments.resolve("RELIANCE", "NSE")
        assert info is not None
        assert info.symbol == "RELIANCE"

    def test_auth(self):
        gw = PaperGateway()
        assert gw.auth.is_authenticated()
        assert gw.auth.get_token()

    def test_close(self):
        gw = PaperGateway()
        gw.close()

    def test_custom_initial_balance(self):
        gw = PaperGateway(initial_cash=Decimal("100000.00"))
        bal = gw.portfolio.funds()
        assert bal.available_cash == Decimal("100000.00")

    def test_set_quote(self):
        gw = PaperGateway()
        gw.set_quote("RELIANCE", Decimal("3000.00"))
        assert gw.market_data.ltp("RELIANCE") == Decimal("3000.00")
