"""Unit tests for OMS metrics instrumentation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from inc_trade.domain.enums import OrderType, Side
from inc_trade.trading.execution_router import ExecutionRouter
from inc_trade.trading.oms import OrderManagementSystem
from inc_trade.trading.order_repository import OrderRepository


@pytest.fixture
def oms() -> OrderManagementSystem:
    router = ExecutionRouter()
    repo = OrderRepository()
    return OrderManagementSystem(
        execution_router=router,
        order_repository=repo,
        kill_switch=False,
    )


class TestOMSMetrics:
    def test_initial_metrics_zero(self, oms: OrderManagementSystem) -> None:
        m = oms.metrics()
        assert m["orders_placed"] == 0
        assert m["orders_rejected"] == 0
        assert m["cancellations"] == 0

    def test_successful_order_increments_placed(self, oms: OrderManagementSystem) -> None:
        # Register a mock broker
        broker = MagicMock()
        broker.place_order.return_value = MagicMock(
            order_id="ORD-1", success=True, status=MagicMock(value="open")
        )
        oms._router.register_adapter("test", broker)

        oms.place_order(
            account_id="test/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        m = oms.metrics()
        assert m["orders_placed"] == 1
        assert m["orders_rejected"] == 0

    def test_kill_switch_increments(self, oms: OrderManagementSystem) -> None:
        oms.kill_switch = True
        result = oms.place_order(
            account_id="test/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert result.success is False
        m = oms.metrics()
        assert m["orders_kill_switched"] == 1

    def test_validation_failure_increments(self, oms: OrderManagementSystem) -> None:
        with pytest.raises(Exception):
            oms.place_order(
                account_id="test/default",
                symbol="",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
            )
        m = oms.metrics()
        assert m["validation_failures"] == 1

    def test_idempotency_hit_increments(self, oms: OrderManagementSystem) -> None:
        broker = MagicMock()
        broker.place_order.return_value = MagicMock(
            order_id="ORD-1", success=True, status=MagicMock(value="open")
        )
        oms._router.register_adapter("test", broker)
        # First call
        oms.place_order(
            account_id="test/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="corr-1",
        )
        # Second call with same correlation_id
        oms.place_order(
            account_id="test/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="corr-1",
        )
        m = oms.metrics()
        assert m["idempotency_hits"] == 1
        # broker should have been called only once
        assert broker.place_order.call_count == 1

    def test_cancellation_increments(self, oms: OrderManagementSystem) -> None:
        broker = MagicMock()
        broker.place_order.return_value = MagicMock(
            order_id="ORD-1", success=True, status=MagicMock(value="open")
        )
        broker.cancel_order.return_value = MagicMock(order_id="ORD-1", success=True)
        oms._router.register_adapter("test", broker)
        oms.place_order(
            account_id="test/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        oms.cancel_order(account_id="test/default", order_id="ORD-1")
        m = oms.metrics()
        assert m["cancellations"] == 1

    def test_modification_increments(self, oms: OrderManagementSystem) -> None:
        broker = MagicMock()
        broker.place_order.return_value = MagicMock(
            order_id="ORD-1", success=True, status=MagicMock(value="open")
        )
        broker.modify_order.return_value = MagicMock(order_id="ORD-1", success=True)
        oms._router.register_adapter("test", broker)
        oms.place_order(
            account_id="test/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        oms.modify_order(account_id="test/default", order_id="ORD-1", quantity=20)
        m = oms.metrics()
        assert m["modifications"] == 1

    def test_broker_error_increments(self, oms: OrderManagementSystem) -> None:
        broker = MagicMock()
        broker.place_order.side_effect = RuntimeError("broker down")
        oms._router.register_adapter("test", broker)
        with pytest.raises(RuntimeError):
            oms.place_order(
                account_id="test/default",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
            )
        m = oms.metrics()
        assert m["broker_errors"] == 1

    def test_metrics_snapshot_is_copy(self, oms: OrderManagementSystem) -> None:
        m1 = oms.metrics()
        m1["orders_placed"] = 999
        m2 = oms.metrics()
        assert m2["orders_placed"] != 999
