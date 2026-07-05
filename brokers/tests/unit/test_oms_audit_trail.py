"""Tests for OMS audit trail — every order state transition is recorded.

Verifies:
1. ``place_order`` records PENDING -> <broker status> transition.
2. ``cancel_order`` records <current> -> CANCELLED transition.
3. Failed place records PENDING -> REJECTED.
4. Audit history is queryable via ``repository.history_for(order_id)``.
5. ``OrderStateHistory.append`` is immutable (returns a new instance).
6. ``OrderStateChangeEvent`` is published on the event bus for each transition.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from inc_trade.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from inc_trade.domain.events import EVENT_ORDER_STATE_CHANGE, OrderStateChangeEvent
from inc_trade.trading.audit import OrderStateChange, OrderStateHistory
from inc_trade.trading.execution_router import ExecutionRouter
from inc_trade.trading.oms import OrderManagementSystem
from inc_trade.trading.order_repository import OrderRepository


class _FakeOrderExecution:
    """Minimal OrderExecutionPort for audit-trail tests."""

    def __init__(self) -> None:
        self.orders: dict[str, object] = {}
        self.fail_next = False
        self.fail_message = ""

    def place_order(
        self,
        symbol: str = "",
        exchange: str = "NSE",
        side: Side = Side.BUY,
        quantity: int = 1,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
    ) -> object:
        from inc_trade.domain.entities import Order, OrderResponse

        if self.fail_next:
            self.fail_next = False
            return OrderResponse(
                order_id="BROKER-FAIL",
                success=False,
                status=OrderStatus.REJECTED,
                message=self.fail_message,
            )
        order_id = f"BROKER-{len(self.orders) + 1:04d}"
        self.orders[order_id] = Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            status=OrderStatus.OPEN,
            price=price,
        )
        return OrderResponse(order_id=order_id, success=True, status=OrderStatus.OPEN)

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> object:
        from inc_trade.domain.entities import OrderResponse

        return OrderResponse(order_id=order_id, success=True)

    def cancel_order(self, order_id: str) -> object:
        from inc_trade.domain.entities import OrderResponse

        return OrderResponse(order_id=order_id, success=True, status=OrderStatus.CANCELLED)

    def get_order(self, order_id: str) -> object | None:
        return self.orders.get(order_id)

    def get_orderbook(self) -> list[object]:
        return list(self.orders.values())


@pytest.fixture
def adapter() -> _FakeOrderExecution:
    return _FakeOrderExecution()


@pytest.fixture
def router(adapter: _FakeOrderExecution) -> ExecutionRouter:
    r = ExecutionRouter()
    r.register_adapter("dhan", adapter)
    return r


@pytest.fixture
def repository() -> OrderRepository:
    return OrderRepository()


@pytest.fixture
def oms(router: ExecutionRouter, repository: OrderRepository) -> OrderManagementSystem:
    return OrderManagementSystem(
        execution_router=router,
        order_repository=repository,
        kill_switch=False,
    )


class TestPlaceOrderAuditTrail:
    """Successful place records PENDING -> OPEN transition."""

    def test_place_records_pending_to_open(
        self, oms: OrderManagementSystem, repository: OrderRepository
    ) -> None:
        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="corr-001",
        )
        assert resp.success
        history = repository.history_for(resp.order_id)
        assert history.order_id == resp.order_id
        assert len(history.changes) == 1
        change = history.changes[0]
        assert change.from_status is OrderStatus.PENDING
        assert change.to_status is OrderStatus.OPEN
        assert change.reason == "place"
        assert change.correlation_id == "corr-001"

    def test_place_failed_records_pending_to_rejected(
        self,
        oms: OrderManagementSystem,
        repository: OrderRepository,
        adapter: _FakeOrderExecution,
    ) -> None:
        adapter.fail_next = True
        adapter.fail_message = "Insufficient margin"
        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        # The fake returns an order_id even on failure, so the order is
        # saved and the audit trail should record the rejection transition.
        assert not resp.success
        assert resp.order_id
        history = repository.history_for(resp.order_id)
        assert len(history.changes) == 1
        change = history.changes[0]
        assert change.from_status is OrderStatus.PENDING
        assert change.to_status is OrderStatus.REJECTED
        assert change.reason == "reject"


class TestCancelOrderAuditTrail:
    """Cancel records <current> -> CANCELLED transition."""

    def test_cancel_records_transition_to_cancelled(
        self, oms: OrderManagementSystem, repository: OrderRepository
    ) -> None:
        place_resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert place_resp.success

        cancel_resp = oms.cancel_order("dhan/default", place_resp.order_id)
        assert cancel_resp.success

        history = repository.history_for(place_resp.order_id)
        # 1 place + 1 cancel = 2 transitions
        assert len(history.changes) == 2
        cancel_change = history.changes[1]
        assert cancel_change.to_status is OrderStatus.CANCELLED
        assert cancel_change.reason == "cancel"


class TestModifyOrderAuditTrail:
    """Modify records a transition with reason=modify."""

    def test_modify_records_modify_reason(
        self, oms: OrderManagementSystem, repository: OrderRepository
    ) -> None:
        place_resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert place_resp.success

        modify_resp = oms.modify_order(
            account_id="dhan/default",
            order_id=place_resp.order_id,
            quantity=15,
        )
        assert modify_resp.success

        history = repository.history_for(place_resp.order_id)
        # 1 place + 1 modify = 2 transitions
        assert len(history.changes) == 2
        modify_change = history.changes[1]
        assert modify_change.reason == "modify"


class TestAuditHistoryImmutability:
    """OrderStateHistory.append returns a new instance."""

    def test_append_returns_new_instance(self) -> None:
        history = OrderStateHistory(order_id="ORD-001")
        change = OrderStateChange(
            order_id="ORD-001",
            correlation_id="corr-1",
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.OPEN,
            reason="place",
        )
        new_history = history.append(change)
        # Original unchanged
        assert len(history.changes) == 0
        # New instance has the appended change
        assert new_history is not history
        assert len(new_history.changes) == 1
        assert new_history.changes[0] is change

    def test_history_is_frozen(self) -> None:
        history = OrderStateHistory(order_id="ORD-001")
        with pytest.raises((FrozenInstanceError, AttributeError)):
            history.changes = ()  # type: ignore[misc]

    def test_change_is_frozen(self) -> None:
        change = OrderStateChange(
            order_id="ORD-001",
            correlation_id="corr-1",
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.OPEN,
            reason="place",
        )
        with pytest.raises((FrozenInstanceError, AttributeError)):
            change.reason = "other"  # type: ignore[misc]

    def test_append_rejects_mismatched_order_id(self) -> None:
        history = OrderStateHistory(order_id="ORD-001")
        change = OrderStateChange(
            order_id="ORD-002",
            correlation_id="",
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.OPEN,
            reason="place",
        )
        with pytest.raises(ValueError, match="order_id"):
            history.append(change)

    def test_last_change_returns_none_for_empty(self) -> None:
        history = OrderStateHistory(order_id="ORD-001")
        assert history.last_change() is None

    def test_last_change_returns_most_recent(self) -> None:
        change1 = OrderStateChange(
            order_id="ORD-001",
            correlation_id="",
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.OPEN,
            reason="place",
        )
        change2 = OrderStateChange(
            order_id="ORD-001",
            correlation_id="",
            from_status=OrderStatus.OPEN,
            to_status=OrderStatus.CANCELLED,
            reason="cancel",
        )
        history = OrderStateHistory(order_id="ORD-001").append(change1).append(change2)
        assert history.last_change() is change2

    def test_transitions_from_filters_by_status(self) -> None:
        change1 = OrderStateChange(
            order_id="ORD-001",
            correlation_id="",
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.OPEN,
            reason="place",
        )
        change2 = OrderStateChange(
            order_id="ORD-001",
            correlation_id="",
            from_status=OrderStatus.OPEN,
            to_status=OrderStatus.CANCELLED,
            reason="cancel",
        )
        history = OrderStateHistory(order_id="ORD-001").append(change1).append(change2)
        from_open = history.transitions_from(OrderStatus.OPEN)
        assert len(from_open) == 1
        assert from_open[0] is change2
        from_pending = history.transitions_from(OrderStatus.PENDING)
        assert len(from_pending) == 1
        assert from_pending[0] is change1


class TestOrderStateChangeEventPublication:
    """Every transition publishes an OrderStateChangeEvent on the event bus."""

    def test_place_publishes_state_change_event(self) -> None:
        from inc_trade.infrastructure.event_bus import EventBus

        adapter = _FakeOrderExecution()
        router = ExecutionRouter()
        router.register_adapter("dhan", adapter)
        repository = OrderRepository()
        event_bus = EventBus()
        received: list[object] = []
        event_bus.subscribe(EVENT_ORDER_STATE_CHANGE, lambda e: received.append(e))

        oms = OrderManagementSystem(
            execution_router=router,
            order_repository=repository,
            kill_switch=False,
            event_bus=event_bus,
        )

        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="corr-100",
        )
        assert resp.success
        assert len(received) == 1
        event = received[0]
        assert isinstance(event, OrderStateChangeEvent)
        assert event.order_id == resp.order_id
        assert event.from_status == "PENDING"
        assert event.to_status == "OPEN"
        assert event.reason == "place"
        assert event.correlation_id == "corr-100"

    def test_cancel_publishes_state_change_event(self) -> None:
        from inc_trade.infrastructure.event_bus import EventBus

        adapter = _FakeOrderExecution()
        router = ExecutionRouter()
        router.register_adapter("dhan", adapter)
        repository = OrderRepository()
        event_bus = EventBus()
        received: list[object] = []
        event_bus.subscribe(EVENT_ORDER_STATE_CHANGE, lambda e: received.append(e))

        oms = OrderManagementSystem(
            execution_router=router,
            order_repository=repository,
            kill_switch=False,
            event_bus=event_bus,
        )

        place_resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        oms.cancel_order("dhan/default", place_resp.order_id)

        # 1 place + 1 cancel = 2 state change events
        assert len(received) == 2
        cancel_event = received[1]
        assert isinstance(cancel_event, OrderStateChangeEvent)
        assert cancel_event.to_status == "CANCELLED"
        assert cancel_event.reason == "cancel"


class TestRepositoryHistoryFor:
    """history_for returns empty history for unknown order IDs."""

    def test_history_for_unknown_returns_empty(self, repository: OrderRepository) -> None:
        history = repository.history_for("UNKNOWN")
        assert history.order_id == "UNKNOWN"
        assert history.changes == ()

    def test_record_then_query(self, repository: OrderRepository) -> None:
        change = OrderStateChange(
            order_id="ORD-007",
            correlation_id="corr-7",
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.OPEN,
            reason="place",
        )
        repository.record_state_change(change)
        history = repository.history_for("ORD-007")
        assert len(history.changes) == 1
        assert history.changes[0] is change
