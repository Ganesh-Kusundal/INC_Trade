"""Tests for immutable canonical domain objects."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from domain import (
    Balance,
    DepthLevel,
    Holding,
    Order,
    OrderStatus,
    OrderType,
    Position,
    Quote,
    Side,
    Trade,
)


class TestOrderImmutable:
    def test_order_is_frozen(self):
        o = Order(
            order_id="O1",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
        )
        with pytest.raises(FrozenInstanceError):
            o.status = OrderStatus.FILLED

    def test_with_status_returns_new_instance(self):
        o = Order(
            order_id="O1",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
        )
        o2 = o.with_status(OrderStatus.FILLED)
        assert o2 is not o
        assert o.status == OrderStatus.OPEN
        assert o2.status == OrderStatus.FILLED

    def test_with_fill_returns_new_instance(self):
        o = Order(
            order_id="O1",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
        )
        o2 = o.with_fill(10, Decimal("2500"))
        assert o2 is not o
        assert o.filled_quantity == 0
        assert o.avg_price == Decimal("0")
        assert o2.filled_quantity == 10
        assert o2.avg_price == Decimal("2500")


class TestPositionImmutable:
    def test_position_is_frozen(self):
        p = Position(symbol="RELIANCE", exchange="NSE")
        with pytest.raises(FrozenInstanceError):
            p.quantity = 10

    def test_with_ltp_updates_unrealized_pnl(self):
        p = Position(symbol="RELIANCE", exchange="NSE", quantity=10, avg_price=Decimal("2500"))
        p2 = p.with_ltp(Decimal("2600"))
        assert p2 is not p
        assert p2.ltp == Decimal("2600")
        assert p2.unrealized_pnl == Decimal("1000")
        assert p.unrealized_pnl == Decimal("0")

    def test_with_fill_new_long_position(self):
        p = Position(symbol="RELIANCE", exchange="NSE")
        p2 = p.with_fill(10, Decimal("2500"))
        assert p2.quantity == 10
        assert p2.avg_price == Decimal("2500")
        assert p2.realized_pnl == Decimal("0")

    def test_with_fill_same_side_weighted_average(self):
        p = Position(symbol="RELIANCE", exchange="NSE", quantity=10, avg_price=Decimal("100"))
        p2 = p.with_fill(10, Decimal("120"))
        assert p2.quantity == 20
        assert p2.avg_price == Decimal("110")
        assert p2.realized_pnl == Decimal("0")

    def test_with_fill_partial_close_realizes_pnl(self):
        p = Position(symbol="RELIANCE", exchange="NSE", quantity=10, avg_price=Decimal("100"))
        p2 = p.with_fill(-5, Decimal("120"))
        assert p2.quantity == 5
        assert p2.avg_price == Decimal("100")
        assert p2.realized_pnl == Decimal("100")

    def test_with_fill_full_close(self):
        p = Position(symbol="RELIANCE", exchange="NSE", quantity=10, avg_price=Decimal("100"))
        p2 = p.with_fill(-10, Decimal("120"))
        assert p2.quantity == 0
        assert p2.avg_price == Decimal("0")
        assert p2.realized_pnl == Decimal("200")

    def test_with_fill_side_flip(self):
        p = Position(symbol="RELIANCE", exchange="NSE", quantity=10, avg_price=Decimal("100"))
        p2 = p.with_fill(-25, Decimal("120"))
        assert p2.quantity == -15
        assert p2.avg_price == Decimal("120")
        assert p2.realized_pnl == Decimal("200")

    def test_with_fill_short_position(self):
        p = Position(symbol="RELIANCE", exchange="NSE", quantity=-10, avg_price=Decimal("100"))
        p2 = p.with_fill(-10, Decimal("90"))
        assert p2.quantity == -20
        assert p2.avg_price == Decimal("95")

    def test_with_fill_short_close(self):
        p = Position(symbol="RELIANCE", exchange="NSE", quantity=-10, avg_price=Decimal("100"))
        p2 = p.with_fill(10, Decimal("90"))
        assert p2.quantity == 0
        assert p2.realized_pnl == Decimal("100")


class TestTradeImmutable:
    def test_trade_is_frozen(self):
        t = Trade(
            trade_id="T1",
            order_id="O1",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        with pytest.raises(FrozenInstanceError):
            t.price = Decimal("100")


class TestQuoteImmutable:
    def test_quote_is_frozen(self):
        q = Quote(symbol="RELIANCE")
        with pytest.raises(FrozenInstanceError):
            q.ltp = Decimal("100")


class TestDepthLevelImmutable:
    def test_depth_level_is_frozen(self):
        d = DepthLevel(price=Decimal("100"), quantity=10)
        with pytest.raises(FrozenInstanceError):
            d.quantity = 20


class TestHoldingImmutable:
    def test_holding_is_frozen(self):
        h = Holding(symbol="RELIANCE", exchange="NSE")
        with pytest.raises(FrozenInstanceError):
            h.quantity = 10


class TestBalanceImmutable:
    def test_balance_is_frozen(self):
        b = Balance(available_balance=Decimal("100000"))
        with pytest.raises(FrozenInstanceError):
            b.available_balance = Decimal("0")
