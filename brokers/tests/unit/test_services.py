"""Tests for application services."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.adapters.paper.gateway import PaperGateway
from brokers.domain import Side
from brokers.domain.enums import OrderType
from brokers.domain.exceptions import OrderRejectedError
from brokers.services.order_service import OrderService


class TestOrderService:
    def setup_method(self):
        gw = PaperGateway()
        self.service = OrderService(gw.orders)

    def test_place_order_success(self):
        resp = self.service.place_order("RELIANCE", "NSE", Side.BUY, 10)
        assert resp.success
        assert resp.order_id

    def test_place_order_validates_symbol(self):
        with pytest.raises(OrderRejectedError, match="symbol"):
            self.service.place_order("", "NSE", Side.BUY, 10)

    def test_place_order_validates_exchange(self):
        with pytest.raises(OrderRejectedError, match="exchange"):
            self.service.place_order("RELIANCE", "", Side.BUY, 10)

    def test_place_order_validates_quantity(self):
        with pytest.raises(OrderRejectedError, match="quantity"):
            self.service.place_order("RELIANCE", "NSE", Side.BUY, 0)

    def test_place_order_validates_limit_price(self):
        with pytest.raises(OrderRejectedError, match="price"):
            self.service.place_order(
                "RELIANCE",
                "NSE",
                Side.BUY,
                10,
                order_type=OrderType.LIMIT,
                price=Decimal("0"),
            )

    def test_place_order_validates_stop_trigger(self):
        with pytest.raises(OrderRejectedError, match="trigger_price"):
            self.service.place_order(
                "RELIANCE",
                "NSE",
                Side.BUY,
                10,
                order_type=OrderType.STOP_LOSS,
                trigger_price=Decimal("0"),
            )

    def test_cancel_order(self):
        resp = self.service.place_order("RELIANCE", "NSE", Side.BUY, 10)
        cancel = self.service.cancel_order(resp.order_id)
        assert cancel.success

    def test_cancel_empty_id_raises(self):
        with pytest.raises(OrderRejectedError, match="order_id"):
            self.service.cancel_order("")

    def test_get_order(self):
        resp = self.service.place_order("RELIANCE", "NSE", Side.BUY, 10)
        order = self.service.get_order(resp.order_id)
        assert order is not None

    def test_get_orderbook(self):
        self.service.place_order("RELIANCE", "NSE", Side.BUY, 10)
        self.service.place_order("TCS", "NSE", Side.SELL, 5)
        book = self.service.get_orderbook()
        assert len(book) == 2


class TestMarketDataService:
    def setup_method(self):
        from brokers.services.market_data_service import MarketDataService

        self.gw = PaperGateway()
        self.gw.set_quote("RELIANCE", Decimal("2500"))
        self.service = MarketDataService(self.gw.market_data, cache_ttl_seconds=10.0)

    def test_ltp(self):
        price = self.service.ltp("RELIANCE")
        assert price == Decimal("2500")

    def test_quote(self):
        q = self.service.quote("RELIANCE")
        assert q.symbol == "RELIANCE"
        assert q.ltp == Decimal("2500")

    def test_depth(self):
        d = self.service.depth("RELIANCE")
        assert d.symbol == "RELIANCE"

    def test_cache_hit(self):
        q1 = self.service.quote("RELIANCE")
        q2 = self.service.quote("RELIANCE")
        assert q1 is q2

    def test_invalidate(self):
        self.service.quote("RELIANCE")
        self.service.invalidate("RELIANCE")
        q2 = self.service.quote("RELIANCE")
        assert q2.ltp == Decimal("2500")


class TestPortfolioService:
    def setup_method(self):
        from brokers.services.portfolio_service import PortfolioService

        self.gw = PaperGateway()
        self.service = PortfolioService(self.gw.portfolio)

    def test_positions(self):
        assert self.service.positions() == []

    def test_holdings(self):
        assert self.service.holdings() == []

    def test_funds(self):
        bal = self.service.funds()
        assert bal.available_cash == Decimal("1000000.00")

    def test_trades(self):
        assert self.service.trades() == []

    def test_total_unrealized_pnl(self):
        pnl = self.service.total_unrealized_pnl()
        assert pnl == Decimal("0")

    def test_net_exposure(self):
        exposure = self.service.net_exposure()
        assert exposure == Decimal("0")


class TestInstrumentService:
    def setup_method(self):
        from brokers.services.instrument_service import InstrumentService

        self.gw = PaperGateway()
        self.service = InstrumentService(self.gw.instruments, auto_load=False)

    def test_search_empty(self):
        results = self.service.search("ZZZZNONEXISTENT")
        assert results == []

    def test_resolve_unknown(self):
        result = self.service.resolve("UNKNOWN")
        assert result is None
