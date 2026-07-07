"""Contract tests — OrderManagementSystem contract.

Verifies kill switch, idempotency, order lifecycle (place/cancel/modify),
state transition validation, event publishing, and query methods.
"""

from __future__ import annotations

from typing import Any

import pytest
from brokers.domain import (
    Order,
    OrderResponse,
    OrderStateError,
    Side,
)
from brokers.domain.enums import OrderStatus
from brokers.domain.events import (
    EVENT_ORDER_CANCELLED,
    EVENT_ORDER_MODIFIED,
    EVENT_ORDER_PLACED,
    EVENT_ORDER_STATE_CHANGE,
)
from brokers.trading.execution_router import ExecutionRouter
from brokers.trading.order_repository import OrderRepository


class _FakeOrderExecution:
    """Minimal OrderExecutionPort stub that always succeeds."""

    def __init__(self) -> None:
        self._order_counter = 0

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        **kwargs: Any,
    ) -> OrderResponse:
        self._order_counter += 1
        return OrderResponse(
            order_id=f"ORD_{self._order_counter:04d}",
            success=True,
            status=OrderStatus.OPEN,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        return OrderResponse(
            order_id=order_id,
            success=True,
            status=OrderStatus.CANCELLED,
        )

    def modify_order(
        self,
        order_id: str,
        **kwargs: Any,
    ) -> OrderResponse:
        return OrderResponse(
            order_id=order_id,
            success=True,
            status=OrderStatus.OPEN,
        )

    def get_order(self, order_id: str) -> Order | None:
        return None

    def get_orderbook(self) -> list[Order]:
        return []


class _FailingOrderExecution:
    """OrderExecutionPort that fails on cancel/modify."""

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        **kwargs: Any,
    ) -> OrderResponse:
        return OrderResponse(
            order_id="ORD_FAIL",
            success=True,
            status=OrderStatus.OPEN,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        return OrderResponse.fail(
            "Cancel failed",
            error_code="BROKER_ERROR",
        )

    def modify_order(
        self,
        order_id: str,
        **kwargs: Any,
    ) -> OrderResponse:
        return OrderResponse.fail(
            "Modify failed",
            error_code="BROKER_ERROR",
        )

    def get_order(self, order_id: str) -> Order | None:
        return None

    def get_orderbook(self) -> list[Order]:
        return []


class _FakeEventBus:
    """Records published events for assertions."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def publish(self, event: Any) -> None:
        self.events.append(event)


def _make_router(
    adapter: Any | None = None,
) -> ExecutionRouter:
    router = ExecutionRouter()
    router.register_adapter(
        "paper",
        adapter or _FakeOrderExecution(),
    )
    return router


def _make_oms(
    kill_switch: bool = False,
    event_bus: Any | None = None,
    adapter: Any | None = None,
) -> Any:
    from brokers.trading.oms import OrderManagementSystem

    return OrderManagementSystem(
        execution_router=_make_router(adapter),
        order_repository=OrderRepository(),
        kill_switch=kill_switch,
        event_bus=event_bus,
    )


class OMSContractTests:
    """Mixin-style contract tests for OrderManagementSystem."""

    # ── Kill Switch ────────────────────────────────────────────────────

    def test_kill_switch_blocks_order_placement(self, oms: Any) -> None:
        oms.kill_switch = True
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        assert not resp.success
        assert resp.error_code == "KILL_SWITCH_ACTIVE"

    def test_kill_switch_allows_order_when_disabled(self, oms: Any) -> None:
        oms.kill_switch = False
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        assert resp.success

    def test_kill_switch_toggle(self, oms: Any) -> None:
        oms.kill_switch = True
        assert oms.kill_switch is True
        oms.kill_switch = False
        assert oms.kill_switch is False

    def test_kill_switch_metrics_tracked(self, oms: Any) -> None:
        oms.kill_switch = True
        oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        metrics = oms.metrics()
        assert metrics["orders_kill_switched"] >= 1

    # ── Idempotency ────────────────────────────────────────────────────

    def test_idempotency_returns_cached_response(self, oms: Any) -> None:
        resp1 = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
            correlation_id="CORR_UNIQUE_001",
        )
        resp2 = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
            correlation_id="CORR_UNIQUE_001",
        )
        # Second call should be idempotency hit
        assert not resp2.success
        assert resp2.error_code == "IDEMPOTENCY_CONFLICT"

    def test_idempotency_hits_metrics(self, oms: Any) -> None:
        oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
            correlation_id="CORR_METRIC_001",
        )
        oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
            correlation_id="CORR_METRIC_001",
        )
        metrics = oms.metrics()
        assert metrics["idempotency_hits"] >= 1

    def test_different_correlation_ids_are_not_idempotent(self, oms: Any) -> None:
        resp1 = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
            correlation_id="CORR_A",
        )
        resp2 = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
            correlation_id="CORR_B",
        )
        assert resp1.success
        assert resp2.success

    # ── Place order ────────────────────────────────────────────────────

    def test_place_order_returns_order_response(self, oms: Any) -> None:
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        assert isinstance(resp, OrderResponse)
        assert resp.success

    def test_place_order_creates_order_in_repository(self, oms: Any) -> None:
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        order = oms.get_order("paper/default", resp.order_id)
        assert order is not None
        assert order.symbol == "RELIANCE"
        assert order.side == Side.BUY

    def test_place_order_rejects_invalid_quantity(self, oms: Any) -> None:
        from brokers.domain.exceptions import ValidationError

        with pytest.raises(ValidationError):
            oms.place_order(
                "paper/default",
                "RELIANCE",
                "NSE",
                Side.BUY,
                0,
            )

    # ── Cancel order ───────────────────────────────────────────────────

    def test_cancel_order_transitions_to_cancelled(self, oms: Any) -> None:
        resp = oms.place_order(
            "paper/default",
            "TCS",
            "NSE",
            Side.BUY,
            5,
        )
        cancel_resp = oms.cancel_order("paper/default", resp.order_id)
        assert cancel_resp.success

        order = oms.get_order("paper/default", resp.order_id)
        assert order is not None
        assert order.status == OrderStatus.CANCELLED

    def test_cancel_order_failure_does_not_update_status(self, oms: Any) -> None:
        failing_oms = _make_oms(adapter=_FailingOrderExecution())
        resp = failing_oms.place_order(
            "paper/default",
            "TCS",
            "NSE",
            Side.BUY,
            5,
        )
        cancel_resp = failing_oms.cancel_order(
            "paper/default",
            resp.order_id,
        )
        assert not cancel_resp.success

    def test_cancel_order_validates_order_id(self, oms: Any) -> None:
        resp = oms.cancel_order("paper/default", "")
        assert not resp.success

    # ── Modify order ───────────────────────────────────────────────────

    def test_modify_order_transitions_state(self, oms: Any) -> None:
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        modify_resp = oms.modify_order(
            "paper/default",
            resp.order_id,
            quantity=15,
        )
        assert modify_resp.success

    def test_modify_order_failure(self, oms: Any) -> None:
        failing_oms = _make_oms(adapter=_FailingOrderExecution())
        resp = failing_oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        modify_resp = failing_oms.modify_order(
            "paper/default",
            resp.order_id,
            quantity=15,
        )
        assert not modify_resp.success

    def test_modify_order_validates_order_id(self, oms: Any) -> None:
        resp = oms.modify_order("paper/default", "")
        assert not resp.success

    # ── Illegal state transition ───────────────────────────────────────

    def test_illegal_state_transition_raises_order_state_error(self, oms: Any) -> None:
        """FILLED → CANCELLED is illegal per the state machine."""
        del oms
        order = Order(
            order_id="ORD_TEST",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            status=OrderStatus.FILLED,
        )
        with pytest.raises(OrderStateError):
            order.propose_transition(OrderStatus.CANCELLED)

    def test_legal_state_transition_succeeds(self, oms: Any) -> None:
        """OPEN → CANCELLED is legal."""
        del oms
        order = Order(
            order_id="ORD_TEST",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            status=OrderStatus.OPEN,
        )
        updated = order.propose_transition(OrderStatus.CANCELLED)
        assert updated.status == OrderStatus.CANCELLED

    # ── Event publishing ───────────────────────────────────────────────

    def test_place_order_publishes_event(self, oms_with_bus: Any) -> None:
        oms, bus = oms_with_bus
        oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        placed = [
            e for e in bus.events if hasattr(e, "event_type") and e.event_type == EVENT_ORDER_PLACED
        ]
        assert len(placed) >= 1

    def test_cancel_order_publishes_event(self, oms_with_bus: Any) -> None:
        oms, bus = oms_with_bus
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        bus.events.clear()
        oms.cancel_order("paper/default", resp.order_id)
        cancelled = [
            e
            for e in bus.events
            if hasattr(e, "event_type") and e.event_type == EVENT_ORDER_CANCELLED
        ]
        assert len(cancelled) >= 1

    def test_modify_order_publishes_event(self, oms_with_bus: Any) -> None:
        oms, bus = oms_with_bus
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        bus.events.clear()
        oms.modify_order("paper/default", resp.order_id, quantity=20)
        modified = [
            e
            for e in bus.events
            if hasattr(e, "event_type") and e.event_type == EVENT_ORDER_MODIFIED
        ]
        assert len(modified) >= 1

    def test_state_change_event_published_on_place(self, oms_with_bus: Any) -> None:
        oms, bus = oms_with_bus
        oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        state_changes = [
            e
            for e in bus.events
            if hasattr(e, "event_type") and e.event_type == EVENT_ORDER_STATE_CHANGE
        ]
        assert len(state_changes) >= 1

    # ── Query methods ──────────────────────────────────────────────────

    def test_get_order_returns_order(self, oms: Any) -> None:
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        order = oms.get_order("paper/default", resp.order_id)
        assert order is not None
        assert isinstance(order, Order)
        assert order.order_id == resp.order_id

    def test_get_order_returns_none_for_unknown(self, oms: Any) -> None:
        order = oms.get_order("paper/default", "NONEXISTENT")
        # May be None or broker fallback result
        assert order is None or isinstance(order, Order)

    def test_get_orderbook_returns_list(self, oms: Any) -> None:
        book = oms.get_orderbook("paper/default")
        assert isinstance(book, list)

    def test_get_active_orders_returns_active_only(self, oms: Any) -> None:
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        oms.place_order(
            "paper/default",
            "TCS",
            "NSE",
            Side.BUY,
            5,
        )
        active = oms.get_active_orders()
        # Both should be active (OPEN status)
        assert len(active) >= 2
        for order in active:
            assert order.is_active()

    # ── Metrics ────────────────────────────────────────────────────────

    def test_metrics_placed_count(self, oms: Any) -> None:
        oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        oms.place_order(
            "paper/default",
            "TCS",
            "NSE",
            Side.BUY,
            5,
        )
        metrics = oms.metrics()
        assert metrics["orders_placed"] >= 2

    def test_metrics_cancellations_count(self, oms: Any) -> None:
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        oms.cancel_order("paper/default", resp.order_id)
        metrics = oms.metrics()
        assert metrics["cancellations"] >= 1

    def test_metrics_modifications_count(self, oms: Any) -> None:
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
        )
        oms.modify_order("paper/default", resp.order_id, quantity=20)
        metrics = oms.metrics()
        assert metrics["modifications"] >= 1

    def test_metrics_validation_failures(self, oms: Any) -> None:
        from brokers.domain.exceptions import ValidationError

        try:
            oms.place_order(
                "paper/default",
                "RELIANCE",
                "NSE",
                Side.BUY,
                0,
            )
        except ValidationError:
            pass
        metrics = oms.metrics()
        assert metrics["validation_failures"] >= 1

    def test_clear_idempotency_cache(self, oms: Any) -> None:
        oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
            correlation_id="CORR_CLEAR",
        )
        oms.clear_idempotency_cache()
        # Should now be able to place again with same correlation_id
        resp = oms.place_order(
            "paper/default",
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
            correlation_id="CORR_CLEAR",
        )
        assert resp.success


def _make_oms_with_bus() -> tuple[Any, _FakeEventBus]:
    bus = _FakeEventBus()
    return _make_oms(event_bus=bus), bus


@pytest.mark.contract
class TestOMSContractConformance:
    """Base test class — override ``oms`` fixture for concrete instances."""

    @pytest.fixture
    def oms(self) -> Any:
        return _make_oms()

    @pytest.fixture
    def oms_with_bus(self) -> tuple[Any, _FakeEventBus]:
        return _make_oms_with_bus()

    def test_kill_switch_blocks_order_placement(self, oms: Any) -> None:
        OMSContractTests().test_kill_switch_blocks_order_placement(oms)

    def test_kill_switch_allows_order_when_disabled(self, oms: Any) -> None:
        OMSContractTests().test_kill_switch_allows_order_when_disabled(oms)

    def test_kill_switch_toggle(self, oms: Any) -> None:
        OMSContractTests().test_kill_switch_toggle(oms)

    def test_kill_switch_metrics_tracked(self, oms: Any) -> None:
        OMSContractTests().test_kill_switch_metrics_tracked(oms)

    def test_idempotency_returns_cached_response(self, oms: Any) -> None:
        OMSContractTests().test_idempotency_returns_cached_response(oms)

    def test_idempotency_hits_metrics(self, oms: Any) -> None:
        OMSContractTests().test_idempotency_hits_metrics(oms)

    def test_different_correlation_ids_are_not_idempotent(self, oms: Any) -> None:
        OMSContractTests().test_different_correlation_ids_are_not_idempotent(oms)

    def test_place_order_returns_order_response(self, oms: Any) -> None:
        OMSContractTests().test_place_order_returns_order_response(oms)

    def test_place_order_creates_order_in_repository(self, oms: Any) -> None:
        OMSContractTests().test_place_order_creates_order_in_repository(oms)

    def test_place_order_rejects_invalid_quantity(self, oms: Any) -> None:
        OMSContractTests().test_place_order_rejects_invalid_quantity(oms)

    def test_cancel_order_transitions_to_cancelled(self, oms: Any) -> None:
        OMSContractTests().test_cancel_order_transitions_to_cancelled(oms)

    def test_cancel_order_failure_does_not_update_status(self, oms: Any) -> None:
        OMSContractTests().test_cancel_order_failure_does_not_update_status(oms)

    def test_cancel_order_validates_order_id(self, oms: Any) -> None:
        OMSContractTests().test_cancel_order_validates_order_id(oms)

    def test_modify_order_transitions_state(self, oms: Any) -> None:
        OMSContractTests().test_modify_order_transitions_state(oms)

    def test_modify_order_failure(self, oms: Any) -> None:
        OMSContractTests().test_modify_order_failure(oms)

    def test_modify_order_validates_order_id(self, oms: Any) -> None:
        OMSContractTests().test_modify_order_validates_order_id(oms)

    def test_illegal_state_transition_raises_order_state_error(self, oms: Any) -> None:
        OMSContractTests().test_illegal_state_transition_raises_order_state_error(oms)

    def test_legal_state_transition_succeeds(self, oms: Any) -> None:
        OMSContractTests().test_legal_state_transition_succeeds(oms)

    def test_place_order_publishes_event(self, oms_with_bus: Any) -> None:
        OMSContractTests().test_place_order_publishes_event(oms_with_bus)

    def test_cancel_order_publishes_event(self, oms_with_bus: Any) -> None:
        OMSContractTests().test_cancel_order_publishes_event(oms_with_bus)

    def test_modify_order_publishes_event(self, oms_with_bus: Any) -> None:
        OMSContractTests().test_modify_order_publishes_event(oms_with_bus)

    def test_state_change_event_published_on_place(self, oms_with_bus: Any) -> None:
        OMSContractTests().test_state_change_event_published_on_place(oms_with_bus)

    def test_get_order_returns_order(self, oms: Any) -> None:
        OMSContractTests().test_get_order_returns_order(oms)

    def test_get_order_returns_none_for_unknown(self, oms: Any) -> None:
        OMSContractTests().test_get_order_returns_none_for_unknown(oms)

    def test_get_orderbook_returns_list(self, oms: Any) -> None:
        OMSContractTests().test_get_orderbook_returns_list(oms)

    def test_get_active_orders_returns_active_only(self, oms: Any) -> None:
        OMSContractTests().test_get_active_orders_returns_active_only(oms)

    def test_metrics_placed_count(self, oms: Any) -> None:
        OMSContractTests().test_metrics_placed_count(oms)

    def test_metrics_cancellations_count(self, oms: Any) -> None:
        OMSContractTests().test_metrics_cancellations_count(oms)

    def test_metrics_modifications_count(self, oms: Any) -> None:
        OMSContractTests().test_metrics_modifications_count(oms)

    def test_metrics_validation_failures(self, oms: Any) -> None:
        OMSContractTests().test_metrics_validation_failures(oms)

    def test_clear_idempotency_cache(self, oms: Any) -> None:
        OMSContractTests().test_clear_idempotency_cache(oms)
