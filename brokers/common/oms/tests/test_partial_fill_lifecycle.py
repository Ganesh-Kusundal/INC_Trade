"""Partial fill order lifecycle tests.

Verifies the OMS correctly handles partial fills — a common production
scenario where an order is filled in multiple tranches rather than
all at once.
"""

from __future__ import annotations

from decimal import Decimal

from application.oms.order_manager import OrderManager
from domain import Order, OrderStatus, OrderType, Side, Trade


def _make_order(
    symbol: str = "RELIANCE",
    quantity: int = 100,
    order_id: str = "ORD-001",
) -> Order:
    return Order(
        order_id=order_id,
        symbol=symbol,
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        status=OrderStatus.OPEN,
        price=Decimal("2500"),
    )


class TestPartialFillLifecycle:
    def test_single_partial_fill_sets_partially_filled(self):
        om = OrderManager()
        order = _make_order(quantity=100)
        om._orders[order.order_id] = order

        trade = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=Side.BUY,
            quantity=40,
            price=Decimal("2500"),
        )
        om.record_trade(trade)

        updated = om._orders[order.order_id]
        assert updated.status == OrderStatus.PARTIALLY_FILLED
        assert updated.filled_quantity == 40

    def test_two_partial_fills_complete_order(self):
        om = OrderManager()
        order = _make_order(quantity=100)
        om._orders[order.order_id] = order

        t1 = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=Side.BUY,
            quantity=40,
            price=Decimal("2500"),
        )
        om.record_trade(t1)
        assert om._orders[order.order_id].status == OrderStatus.PARTIALLY_FILLED

        t2 = Trade(
            trade_id="T2",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=Side.BUY,
            quantity=60,
            price=Decimal("2501"),
        )
        om.record_trade(t2)
        final = om._orders[order.order_id]
        assert final.status == OrderStatus.FILLED
        assert final.filled_quantity == 100

    def test_three_tranche_partial_fills(self):
        om = OrderManager()
        order = _make_order(quantity=300)
        om._orders[order.order_id] = order

        for i, qty in enumerate([100, 100, 100], 1):
            trade = Trade(
                trade_id=f"T{i}",
                order_id=order.order_id,
                symbol=order.symbol,
                exchange=order.exchange,
                side=Side.BUY,
                quantity=qty,
                price=Decimal("2500"),
            )
            om.record_trade(trade)

        final = om._orders[order.order_id]
        assert final.status == OrderStatus.FILLED
        assert final.filled_quantity == 300

    def test_duplicate_partial_fill_is_idempotent(self):
        om = OrderManager()
        order = _make_order(quantity=100)
        om._orders[order.order_id] = order

        trade = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=Side.BUY,
            quantity=40,
            price=Decimal("2500"),
        )
        om.record_trade(trade)
        om.record_trade(trade)

        updated = om._orders[order.order_id]
        assert updated.filled_quantity == 40
        assert updated.status == OrderStatus.PARTIALLY_FILLED

    def test_partial_fill_records_filled_quantity(self):
        om = OrderManager()
        order = _make_order(quantity=100)
        om._orders[order.order_id] = order

        trade = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=Side.BUY,
            quantity=50,
            price=Decimal("2500"),
        )
        om.record_trade(trade)

        updated = om._orders[order.order_id]
        assert updated.filled_quantity == 50
        assert updated.status == OrderStatus.PARTIALLY_FILLED

    def test_partial_fill_then_cancel(self):
        om = OrderManager()
        order = _make_order(quantity=100)
        om._orders[order.order_id] = order

        trade = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=Side.BUY,
            quantity=30,
            price=Decimal("2500"),
        )
        om.record_trade(trade)
        assert om._orders[order.order_id].status == OrderStatus.PARTIALLY_FILLED

        om.cancel_order(order.order_id)
        assert om._orders[order.order_id].status == OrderStatus.CANCELLED

    def test_partial_fill_remaining_quantity(self):
        om = OrderManager()
        order = _make_order(quantity=100)
        om._orders[order.order_id] = order

        trade = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=Side.BUY,
            quantity=30,
            price=Decimal("2500"),
        )
        om.record_trade(trade)

        updated = om._orders[order.order_id]
        assert updated.filled_quantity == 30
        remaining = order.quantity - updated.filled_quantity
        assert remaining == 70
