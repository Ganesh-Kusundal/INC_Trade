"""Entity invariant tests — Hypothesis-based for Order and Position.

These tests verify the core invariants of the domain value objects:
- Order.with_status preserves all fields except status
- Order.with_fill preserves all fields except filled_quantity and avg_price
- Position.with_ltp preserves all fields except ltp and unrealized_pnl
- Position.with_fill correctly computes PnL, realized_pnl, and avg_price
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from domain.entities import Order, Position
from domain.types import OrderStatus, OrderType, ProductType, Side, Validity

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_order(**overrides) -> Order:
    defaults = {
        "order_id": "O-1001",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "side": Side.BUY,
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "filled_quantity": 0,
        "price": Decimal("2500"),
        "trigger_price": Decimal("0"),
        "status": OrderStatus.OPEN,
        "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "product_type": ProductType.INTRADAY,
        "validity": Validity.DAY,
        "avg_price": Decimal("0"),
        "reject_reason": "",
        "correlation_id": "corr-1",
    }
    defaults.update(overrides)
    return Order(**defaults)


def _make_position(**overrides) -> Position:
    defaults = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "quantity": 0,
        "avg_price": Decimal("0"),
        "ltp": Decimal("0"),
        "unrealized_pnl": Decimal("0"),
        "realized_pnl": Decimal("0"),
        "product_type": ProductType.INTRADAY,
        "correlation_id": None,
    }
    defaults.update(overrides)
    return Position(**defaults)


# ---------------------------------------------------------------------------
# Order invariant tests
# ---------------------------------------------------------------------------


class TestOrderWithStatus:
    """Order.with_status must preserve all fields and only change status."""

    def test_preserves_order_id(self):
        o = _make_order()
        result = o.with_status(OrderStatus.FILLED)
        assert result.order_id == o.order_id

    def test_preserves_symbol_and_exchange(self):
        o = _make_order()
        result = o.with_status(OrderStatus.CANCELLED)
        assert result.symbol == o.symbol
        assert result.exchange == o.exchange

    def test_preserves_side_and_order_type(self):
        o = _make_order(side=Side.SELL, order_type=OrderType.STOP_LOSS)
        result = o.with_status(OrderStatus.FILLED)
        assert result.side == Side.SELL
        assert result.order_type == OrderType.STOP_LOSS

    def test_preserves_quantity_and_price(self):
        o = _make_order(quantity=50, price=Decimal("1234.56"))
        result = o.with_status(OrderStatus.REJECTED)
        assert result.quantity == 50
        assert result.price == Decimal("1234.56")

    def test_preserves_timestamp(self):
        ts = datetime(2026, 6, 15, 10, 30, tzinfo=timezone.utc)
        o = _make_order(timestamp=ts)
        result = o.with_status(OrderStatus.FILLED)
        assert result.timestamp == ts

    def test_preserves_correlation_id(self):
        o = _make_order(correlation_id="abc-123")
        result = o.with_status(OrderStatus.FILLED)
        assert result.correlation_id == "abc-123"

    def test_changes_status(self):
        o = _make_order(status=OrderStatus.OPEN)
        result = o.with_status(OrderStatus.FILLED)
        assert result.status == OrderStatus.FILLED

    def test_returns_frozen_copy(self):
        o = _make_order()
        result = o.with_status(OrderStatus.FILLED)
        assert result is not o
        assert o.status == OrderStatus.OPEN  # original unchanged


class TestOrderWithFill:
    """Order.with_fill must update filled_quantity and avg_price, preserve rest."""

    def test_preserves_order_id(self):
        o = _make_order()
        result = o.with_fill(5, Decimal("2500"))
        assert result.order_id == o.order_id

    def test_preserves_symbol_exchange_side(self):
        o = _make_order()
        result = o.with_fill(5, Decimal("2500"))
        assert result.symbol == o.symbol
        assert result.exchange == o.exchange
        assert result.side == o.side

    def test_updates_filled_quantity(self):
        o = _make_order(quantity=10, filled_quantity=0)
        result = o.with_fill(5, Decimal("2500"))
        assert result.filled_quantity == 5

    def test_updates_avg_price(self):
        o = _make_order()
        result = o.with_fill(10, Decimal("2499.50"))
        assert result.avg_price == Decimal("2499.50")

    def test_preserves_price_and_status(self):
        o = _make_order(price=Decimal("2500"), status=OrderStatus.PARTIALLY_FILLED)
        result = o.with_fill(5, Decimal("2498"))
        assert result.price == Decimal("2500")
        assert result.status == OrderStatus.PARTIALLY_FILLED

    def test_preserves_trigger_price(self):
        o = _make_order(trigger_price=Decimal("2400"))
        result = o.with_fill(5, Decimal("2500"))
        assert result.trigger_price == Decimal("2400")


# ---------------------------------------------------------------------------
# Position invariant tests
# ---------------------------------------------------------------------------


class TestPositionWithLtp:
    """Position.with_ltp must update ltp and unrealized_pnl, preserve rest."""

    def test_preserves_symbol_and_exchange(self):
        p = _make_position(symbol="TCS", exchange="BSE")
        result = p.with_ltp(Decimal("3500"))
        assert result.symbol == "TCS"
        assert result.exchange == "BSE"

    def test_updates_ltp(self):
        p = _make_position()
        result = p.with_ltp(Decimal("2600"))
        assert result.ltp == Decimal("2600")

    def test_computes_unrealized_pnl_long(self):
        p = _make_position(quantity=10, avg_price=Decimal("2500"))
        result = p.with_ltp(Decimal("2600"))
        # unrealized = quantity * (ltp - avg_price) = 10 * 100 = 1000
        assert result.unrealized_pnl == Decimal("1000")

    def test_computes_unrealized_pnl_short(self):
        p = _make_position(quantity=-10, avg_price=Decimal("2500"))
        result = p.with_ltp(Decimal("2400"))
        # For short: unrealized = |quantity| * (avg_price - ltp) = 10 * 100 = 1000
        assert result.unrealized_pnl == Decimal("1000")

    def test_zero_quantity_zero_unrealized(self):
        p = _make_position(quantity=0)
        result = p.with_ltp(Decimal("9999"))
        assert result.unrealized_pnl == Decimal("0")

    def test_preserves_realized_pnl(self):
        p = _make_position(realized_pnl=Decimal("500"))
        result = p.with_ltp(Decimal("2600"))
        assert result.realized_pnl == Decimal("500")


class TestPositionWithFill:
    """Position.with_fill must correctly compute qty, avg_price, and realized PnL."""

    def test_open_new_long(self):
        p = _make_position()
        result = p.with_fill(10, Decimal("2500"))
        assert result.quantity == 10
        assert result.avg_price == Decimal("2500")
        assert result.realized_pnl == Decimal("0")

    def test_open_new_short(self):
        p = _make_position()
        result = p.with_fill(-10, Decimal("2500"))
        assert result.quantity == -10
        assert result.avg_price == Decimal("2500")
        assert result.realized_pnl == Decimal("0")

    def test_add_to_long(self):
        p = _make_position(quantity=10, avg_price=Decimal("2500"))
        result = p.with_fill(5, Decimal("2600"))
        assert result.quantity == 15
        # avg = (10*2500 + 5*2600) / 15 = 38000/15 = 2533.33...
        assert result.avg_price == (Decimal("25000") + Decimal("13000")) / Decimal("15")

    def test_close_long_partially(self):
        p = _make_position(quantity=10, avg_price=Decimal("2500"))
        result = p.with_fill(-5, Decimal("2600"))
        assert result.quantity == 5
        # realized = 5 * (2600 - 2500) = 500
        assert result.realized_pnl == Decimal("500")
        assert result.avg_price == Decimal("2500")

    def test_close_long_fully(self):
        p = _make_position(quantity=10, avg_price=Decimal("2500"))
        result = p.with_fill(-10, Decimal("2600"))
        assert result.quantity == 0
        assert result.realized_pnl == Decimal("1000")
        assert result.avg_price == Decimal("0")

    def test_realized_pnl_accumulates(self):
        p = _make_position(quantity=10, avg_price=Decimal("2500"), realized_pnl=Decimal("200"))
        result = p.with_fill(-5, Decimal("2600"))
        assert result.realized_pnl == Decimal("700")  # 200 + 500

    def test_short_cover(self):
        p = _make_position(quantity=-10, avg_price=Decimal("2500"))
        result = p.with_fill(10, Decimal("2400"))
        assert result.quantity == 0
        # For short: realized = |closed| * (avg - exit) = 10 * 100 = 1000
        assert result.realized_pnl == Decimal("1000")

    def test_overclose_long(self):
        """Selling more than held — net becomes short."""
        p = _make_position(quantity=5, avg_price=Decimal("2500"))
        result = p.with_fill(-10, Decimal("2600"))
        assert result.quantity == -5
        # closed = min(5, 10) = 5, realized = 5 * (2600-2500) = 500
        assert result.realized_pnl == Decimal("500")
        # new avg = exit price since we flipped
        assert result.avg_price == Decimal("2600")
