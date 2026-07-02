"""Concurrent rapid duplicate fill tests.

Verifies that the OMS idempotency mechanisms prevent double-counting
when multiple trade events arrive in rapid succession — a common
production scenario during high-frequency partial fills.
"""

from __future__ import annotations

import threading
from decimal import Decimal

from application.oms.order_manager import OrderManager
from domain import Order, OrderStatus, OrderType, Side, Trade


def _make_order(quantity: int = 100, order_id: str = "ORD-001") -> Order:
    return Order(
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        status=OrderStatus.OPEN,
        price=Decimal("2500"),
    )


class TestConcurrentRapidFills:
    def test_concurrent_identical_fills_counted_once(self):
        om = OrderManager()
        order = _make_order(quantity=100)
        om._orders[order.order_id] = order

        trade = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=50,
            price=Decimal("2500"),
        )

        errors: list[Exception] = []

        def apply_trade():
            try:
                om.record_trade(trade)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=apply_trade) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors
        updated = om._orders[order.order_id]
        assert updated.filled_quantity == 50

    def test_concurrent_distinct_fills_all_applied(self):
        om = OrderManager()
        order = _make_order(quantity=100)
        om._orders[order.order_id] = order

        trades = [
            Trade(
                trade_id=f"T{i}",
                order_id=order.order_id,
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
                price=Decimal("2500"),
            )
            for i in range(5)
        ]

        errors: list[Exception] = []

        def apply_trade(t):
            try:
                om.record_trade(t)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=apply_trade, args=(t,)) for t in trades]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors
        updated = om._orders[order.order_id]
        assert updated.filled_quantity == 50
        assert updated.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED)

    def test_rapid_duplicate_then_unique_fill(self):
        om = OrderManager()
        order = _make_order(quantity=100)
        om._orders[order.order_id] = order

        t1 = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=30,
            price=Decimal("2500"),
        )
        om.record_trade(t1)
        om.record_trade(t1)
        om.record_trade(t1)

        t2 = Trade(
            trade_id="T2",
            order_id=order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=70,
            price=Decimal("2501"),
        )
        om.record_trade(t2)

        final = om._orders[order.order_id]
        assert final.filled_quantity == 100
        assert final.status == OrderStatus.FILLED

    def test_burst_fills_reach_filled_status(self):
        om = OrderManager()
        order = _make_order(quantity=50)
        om._orders[order.order_id] = order

        for i in range(10):
            trade = Trade(
                trade_id=f"T{i}",
                order_id=order.order_id,
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
                price=Decimal("2500"),
            )
            om.record_trade(trade)

        final = om._orders[order.order_id]
        assert final.filled_quantity >= 50
        assert final.status == OrderStatus.FILLED
