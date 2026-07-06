"""Tests for domain entities — frozen value objects."""

from __future__ import annotations

from decimal import Decimal

import pytest
from inc_trade.domain.entities import (
    Balance,
    DepthLevel,
    Holding,
    MarketDepth,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)
from inc_trade.domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)


class TestOrder:
    def test_create_minimal(self):
        order = Order(
            order_id="ORD001",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            status=OrderStatus.PENDING,
        )
        assert order.order_id == "ORD001"
        assert order.side is Side.BUY
        assert order.quantity == 10

    def test_frozen(self):
        order = Order(
            order_id="ORD001",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            status=OrderStatus.PENDING,
        )
        with pytest.raises(AttributeError):
            order.quantity = 20

    def test_equality(self):
        a = Order(
            order_id="ORD001",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            status=OrderStatus.PENDING,
        )
        b = Order(
            order_id="ORD001",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            status=OrderStatus.PENDING,
        )
        assert a == b

    def test_defaults(self):
        order = Order(
            order_id="ORD001",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            status=OrderStatus.PENDING,
        )
        assert order.price == Decimal("0")
        assert order.trigger_price == Decimal("0")
        assert order.order_type == OrderType.MARKET
        assert order.product_type == ProductType.INTRADAY
        assert order.validity == Validity.DAY
        assert order.filled_quantity == 0
        assert order.message == ""

    def test_with_price(self):
        order = Order(
            order_id="ORD002",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500.50"),
            order_type=OrderType.LIMIT,
            status=OrderStatus.OPEN,
        )
        assert order.price == Decimal("2500.50")
        assert order.order_type is OrderType.LIMIT


class TestQuote:
    def test_create(self):
        q = Quote(symbol="RELIANCE", ltp=Decimal("2500.00"))
        assert q.symbol == "RELIANCE"
        assert q.ltp == Decimal("2500.00")

    def test_frozen(self):
        q = Quote(symbol="RELIANCE", ltp=Decimal("2500.00"))
        with pytest.raises(AttributeError):
            q.ltp = Decimal("2600.00")

    def test_defaults(self):
        q = Quote(symbol="RELIANCE", ltp=Decimal("2500.00"))
        assert q.open == Decimal("0")
        assert q.high == Decimal("0")
        assert q.low == Decimal("0")
        assert q.close == Decimal("0")
        assert q.volume == 0
        assert q.exchange == ""


class TestMarketDepth:
    def test_create(self):
        bids = [DepthLevel(price=Decimal("2499"), quantity=100)]
        asks = [DepthLevel(price=Decimal("2501"), quantity=50)]
        depth = MarketDepth(symbol="RELIANCE", bids=bids, asks=asks)
        assert len(depth.bids) == 1
        assert len(depth.asks) == 1
        assert depth.bids[0].price == Decimal("2499")

    def test_frozen(self):
        depth = MarketDepth(symbol="RELIANCE", bids=[], asks=[])
        with pytest.raises(AttributeError):
            depth.symbol = "TCS"


class TestDepthLevel:
    def test_create(self):
        level = DepthLevel(price=Decimal("2500.00"), quantity=100)
        assert level.price == Decimal("2500.00")
        assert level.quantity == 100
        assert level.orders == 0


class TestTrade:
    def test_create(self):
        trade = Trade(
            trade_id="T001",
            order_id="ORD001",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500.00"),
        )
        assert trade.trade_id == "T001"
        assert trade.price == Decimal("2500.00")

    def test_frozen(self):
        trade = Trade(
            trade_id="T001",
            order_id="ORD001",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500.00"),
        )
        with pytest.raises(AttributeError):
            trade.quantity = 20


class TestPosition:
    def test_create(self):
        pos = Position(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            product_type=ProductType.INTRADAY,
        )
        assert pos.quantity == 10
        assert pos.product_type is ProductType.INTRADAY

    def test_defaults(self):
        pos = Position(symbol="RELIANCE", exchange="NSE", quantity=10)
        assert pos.average_price == Decimal("0")
        assert pos.realized_pnl == Decimal("0")
        assert pos.unrealized_pnl == Decimal("0")


class TestHolding:
    def test_create(self):
        h = Holding(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=100,
            average_price=Decimal("2400.00"),
        )
        assert h.quantity == 100
        assert h.average_price == Decimal("2400.00")

    def test_frozen(self):
        h = Holding(symbol="RELIANCE", exchange="NSE", quantity=100)
        with pytest.raises(AttributeError):
            h.quantity = 200


class TestBalance:
    def test_create(self):
        b = Balance(available_cash=Decimal("50000.00"))
        assert b.available_cash == Decimal("50000.00")

    def test_defaults(self):
        b = Balance(available_cash=Decimal("50000.00"))
        assert b.utilized_margin == Decimal("0")
        assert b.total_margin == Decimal("0")


class TestOrderResponse:
    def test_success(self):
        resp = OrderResponse(order_id="ORD001", success=True)
        assert resp.success
        assert resp.order_id == "ORD001"

    def test_failure(self):
        resp = OrderResponse.fail("Insufficient margin")
        assert not resp.success
        assert resp.message == "Insufficient margin"
        assert resp.order_id == ""

    def test_frozen(self):
        resp = OrderResponse(order_id="ORD001", success=True)
        with pytest.raises(AttributeError):
            resp.success = False

    def test_ok_classmethod(self):
        resp = OrderResponse.ok("ORD002", OrderStatus.OPEN)
        assert resp.success
        assert resp.order_id == "ORD002"
        assert resp.status == OrderStatus.OPEN

    def test_ok_default_status(self):
        resp = OrderResponse.ok("ORD003")
        assert resp.success
        assert resp.status == OrderStatus.PENDING

    def test_live_orders_disabled(self):
        resp = OrderResponse.live_orders_disabled()
        assert not resp.success
        assert resp.error_code == "LIVE_ORDERS_DISABLED"

    def test_already_executed(self):
        resp = OrderResponse.already_executed("ORD004")
        assert not resp.success
        assert resp.order_id == "ORD004"
        assert resp.error_code == "IDEMPOTENCY_CONFLICT"
