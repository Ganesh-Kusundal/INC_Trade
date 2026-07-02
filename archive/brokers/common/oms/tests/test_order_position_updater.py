"""Tests for OrderPositionUpdater collaborator.

Tests cover:
- Partial fill handling
- Full fill handling
- Average price computation (VWAP)
- Multiple sequential trades
- Edge cases (zero quantity, overfill protection)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.oms.order_position_updater import OrderPositionUpdater
from domain import Order, Trade
from domain.types import OrderStatus, OrderType, ProductType, Side


@pytest.fixture
def updater() -> OrderPositionUpdater:
    """Fresh OrderPositionUpdater instance."""
    return OrderPositionUpdater()


@pytest.fixture
def sample_order() -> Order:
    """Sample order for testing."""
    return Order(
        order_id="OM-test-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
        price=Decimal("0"),
        product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
    )


# ── Partial Fill Handling ──────────────────────────────────────────────────


class TestPartialFillHandling:
    """Test partial fill scenarios."""

    def test_single_partial_fill(self, updater: OrderPositionUpdater, sample_order: Order) -> None:
        """Single partial fill should update order correctly."""
        trade = Trade(
            trade_id="T1",
            order_id=sample_order.order_id,
            symbol=sample_order.symbol,
            exchange=sample_order.exchange,
            side=sample_order.side,
            quantity=30,
            price=Decimal("100"),
        )
        updated = updater.apply_trade(sample_order, trade)

        assert updated.filled_quantity == 30
        assert updated.avg_price == Decimal("100")
        assert updated.status == OrderStatus.PARTIALLY_FILLED

    def test_multiple_partial_fills(
        self, updater: OrderPositionUpdater, sample_order: Order
    ) -> None:
        """Multiple partial fills should accumulate correctly."""
        order = sample_order

        # First fill: 30 shares @ 100
        trade1 = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=30,
            price=Decimal("100"),
        )
        order = updater.apply_trade(order, trade1)
        assert order.filled_quantity == 30
        assert order.status == OrderStatus.PARTIALLY_FILLED

        # Second fill: 20 shares @ 105
        trade2 = Trade(
            trade_id="T2",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=20,
            price=Decimal("105"),
        )
        order = updater.apply_trade(order, trade2)
        assert order.filled_quantity == 50
        assert order.status == OrderStatus.PARTIALLY_FILLED


# ── Full Fill Handling ─────────────────────────────────────────────────────


class TestFullFillHandling:
    """Test full fill scenarios."""

    def test_single_full_fill(self, updater: OrderPositionUpdater, sample_order: Order) -> None:
        """Single trade filling entire order should mark as FILLED."""
        trade = Trade(
            trade_id="T1",
            order_id=sample_order.order_id,
            symbol=sample_order.symbol,
            exchange=sample_order.exchange,
            side=sample_order.side,
            quantity=100,
            price=Decimal("100"),
        )
        updated = updater.apply_trade(sample_order, trade)

        assert updated.filled_quantity == 100
        assert updated.status == OrderStatus.FILLED

    def test_partial_then_full_fill(
        self, updater: OrderPositionUpdater, sample_order: Order
    ) -> None:
        """Partial fill followed by completing fill should mark as FILLED."""
        order = sample_order

        # Partial: 70 shares
        trade1 = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=70,
            price=Decimal("100"),
        )
        order = updater.apply_trade(order, trade1)
        assert order.status == OrderStatus.PARTIALLY_FILLED

        # Complete: remaining 30 shares
        trade2 = Trade(
            trade_id="T2",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=30,
            price=Decimal("102"),
        )
        order = updater.apply_trade(order, trade2)
        assert order.filled_quantity == 100
        assert order.status == OrderStatus.FILLED

    def test_overfill_marks_as_filled(
        self, updater: OrderPositionUpdater, sample_order: Order
    ) -> None:
        """Overfill (more than order quantity) should still mark as FILLED."""
        trade = Trade(
            trade_id="T1",
            order_id=sample_order.order_id,
            symbol=sample_order.symbol,
            exchange=sample_order.exchange,
            side=sample_order.side,
            quantity=110,  # More than order quantity (100)
            price=Decimal("100"),
        )
        updated = updater.apply_trade(sample_order, trade)

        assert updated.filled_quantity == 110
        assert updated.status == OrderStatus.FILLED


# ── Average Price Computation ──────────────────────────────────────────────


class TestAveragePriceComputation:
    """Test VWAP-style average price computation."""

    def test_first_trade_avg_price(
        self, updater: OrderPositionUpdater, sample_order: Order
    ) -> None:
        """First trade should set avg_price to trade price."""
        trade = Trade(
            trade_id="T1",
            order_id=sample_order.order_id,
            symbol=sample_order.symbol,
            exchange=sample_order.exchange,
            side=sample_order.side,
            quantity=50,
            price=Decimal("100"),
        )
        updated = updater.apply_trade(sample_order, trade)
        assert updated.avg_price == Decimal("100")

    def test_weighted_avg_price_two_trades(
        self, updater: OrderPositionUpdater, sample_order: Order
    ) -> None:
        """Two trades should compute weighted average correctly."""
        order = sample_order

        # First: 50 @ 100
        trade1 = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=50,
            price=Decimal("100"),
        )
        order = updater.apply_trade(order, trade1)

        # Second: 50 @ 200
        trade2 = Trade(
            trade_id="T2",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=50,
            price=Decimal("200"),
        )
        order = updater.apply_trade(order, trade2)

        # Expected: (50*100 + 50*200) / 100 = 150
        assert order.avg_price == Decimal("150")

    def test_weighted_avg_price_three_trades(
        self, updater: OrderPositionUpdater, sample_order: Order
    ) -> None:
        """Three trades should compute weighted average correctly."""
        order = sample_order

        # 30 @ 100
        trade1 = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=30,
            price=Decimal("100"),
        )
        order = updater.apply_trade(order, trade1)

        # 30 @ 200
        trade2 = Trade(
            trade_id="T2",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=30,
            price=Decimal("200"),
        )
        order = updater.apply_trade(order, trade2)

        # 40 @ 150
        trade3 = Trade(
            trade_id="T3",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=40,
            price=Decimal("150"),
        )
        order = updater.apply_trade(order, trade3)

        # Expected: (30*100 + 30*200 + 40*150) / 100 = 150
        assert order.avg_price == Decimal("150")

    def test_avg_price_with_existing_fill(self, updater: OrderPositionUpdater) -> None:
        """Applying trade to order with existing fill should compute correctly."""
        order = Order(
            order_id="OM-test-2",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
            filled_quantity=50,
            avg_price=Decimal("100"),
            status=OrderStatus.PARTIALLY_FILLED,
        )

        trade = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=50,
            price=Decimal("200"),
        )
        updated = updater.apply_trade(order, trade)

        # Expected: (50*100 + 50*200) / 100 = 150
        assert updated.avg_price == Decimal("150")


# ── Edge Cases ─────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_quantity_trade(self, updater: OrderPositionUpdater, sample_order: Order) -> None:
        """Zero quantity trade should not change fill state."""
        trade = Trade(
            trade_id="T1",
            order_id=sample_order.order_id,
            symbol=sample_order.symbol,
            exchange=sample_order.exchange,
            side=sample_order.side,
            quantity=0,
            price=Decimal("100"),
        )
        updated = updater.apply_trade(sample_order, trade)

        assert updated.filled_quantity == 0
        assert updated.avg_price == Decimal("0")

    def test_returns_new_order_instance(
        self, updater: OrderPositionUpdater, sample_order: Order
    ) -> None:
        """apply_trade should return new Order instance (immutability)."""
        trade = Trade(
            trade_id="T1",
            order_id=sample_order.order_id,
            symbol=sample_order.symbol,
            exchange=sample_order.exchange,
            side=sample_order.side,
            quantity=10,
            price=Decimal("100"),
        )
        updated = updater.apply_trade(sample_order, trade)

        assert updated is not sample_order
        assert sample_order.filled_quantity == 0  # Original unchanged

    def test_small_quantity_fill(self, updater: OrderPositionUpdater, sample_order: Order) -> None:
        """Very small fill (1 share) should work correctly."""
        trade = Trade(
            trade_id="T1",
            order_id=sample_order.order_id,
            symbol=sample_order.symbol,
            exchange=sample_order.exchange,
            side=sample_order.side,
            quantity=1,
            price=Decimal("100"),
        )
        updated = updater.apply_trade(sample_order, trade)

        assert updated.filled_quantity == 1
        assert updated.status == OrderStatus.PARTIALLY_FILLED

    def test_decimal_precision(self, updater: OrderPositionUpdater, sample_order: Order) -> None:
        """Average price should maintain decimal precision."""
        trade = Trade(
            trade_id="T1",
            order_id=sample_order.order_id,
            symbol=sample_order.symbol,
            exchange=sample_order.exchange,
            side=sample_order.side,
            quantity=3,
            price=Decimal("100.123"),
        )
        updated = updater.apply_trade(sample_order, trade)

        assert updated.avg_price == Decimal("100.123")
