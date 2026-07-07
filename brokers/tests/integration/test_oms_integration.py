"""Integration tests for OrderManagementSystem with paper broker adapters.

Tests the full order lifecycle (place → modify → cancel), idempotency,
kill switch, event publishing, get_orderbook, and get_active_orders.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from brokers.domain.enums import OrderStatus, OrderType, Side
from brokers.domain.events import (
    OrderCancelledEvent,
    OrderModifiedEvent,
    OrderPlacedEvent,
    OrderRejectedEvent,
)
from brokers.trading.execution_router import ExecutionRouter
from brokers.trading.oms import OrderManagementSystem
from brokers.trading.order_repository import OrderRepository

from brokers.adapters.paper.gateway import PaperGateway


class _RecordingEventBus:
    """Event bus that records all published events for test assertions."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def publish(self, event: Any) -> None:
        self.events.append(event)


@pytest.fixture
def paper_gateway() -> PaperGateway:
    """PaperGateway for order execution."""
    return PaperGateway()


@pytest.fixture
def execution_router(paper_gateway: PaperGateway) -> ExecutionRouter:
    """ExecutionRouter with paper gateway registered."""
    router = ExecutionRouter()
    router.register_adapter("paper", paper_gateway.orders)
    return router


@pytest.fixture
def order_repository() -> OrderRepository:
    """Empty OrderRepository."""
    return OrderRepository()


@pytest.fixture
def event_bus() -> _RecordingEventBus:
    """Recording event bus for event assertions."""
    return _RecordingEventBus()


@pytest.fixture
def oms(
    execution_router: ExecutionRouter,
    order_repository: OrderRepository,
    event_bus: _RecordingEventBus,
) -> OrderManagementSystem:
    """OrderManagementSystem wired with paper adapters and event bus."""
    return OrderManagementSystem(
        execution_router=execution_router,
        order_repository=order_repository,
        event_bus=event_bus,
    )


_ACCOUNT = "paper/default"


@pytest.mark.integration
class TestOMSOrderLifecycle:
    """Tests for the complete order lifecycle: place → modify → cancel."""

    def test_place_order(self, oms: OrderManagementSystem):
        resp = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert resp.success is True
        assert resp.order_id != ""
        assert resp.status == OrderStatus.OPEN

    def test_place_order_with_correlation_id(self, oms: OrderManagementSystem):
        resp = oms.place_order(
            account_id=_ACCOUNT,
            symbol="TCS",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            order_type=OrderType.LIMIT,
            price=Decimal("3500.00"),
            correlation_id="corr-123",
        )
        assert resp.success is True
        assert resp.order_id != ""

    def test_place_and_cancel_order(self, oms: OrderManagementSystem):
        placed = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert placed.success

        cancelled = oms.cancel_order(account_id=_ACCOUNT, order_id=placed.order_id)
        assert cancelled.success is True
        assert cancelled.status == OrderStatus.CANCELLED

    def test_place_and_modify_order(self, oms: OrderManagementSystem):
        placed = oms.place_order(
            account_id=_ACCOUNT,
            symbol="INFY",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=Decimal("1800.00"),
        )
        assert placed.success

        modified = oms.modify_order(
            account_id=_ACCOUNT,
            order_id=placed.order_id,
            quantity=15,
            price=Decimal("1820.00"),
        )
        assert modified.success is True

    def test_cancel_nonexistent_order(self, oms: OrderManagementSystem):
        resp = oms.cancel_order(account_id=_ACCOUNT, order_id="NONEXISTENT")
        assert resp.success is False

    def test_modify_nonexistent_order(self, oms: OrderManagementSystem):
        resp = oms.modify_order(
            account_id=_ACCOUNT,
            order_id="NONEXISTENT",
            quantity=10,
        )
        assert resp.success is False

    def test_cancel_with_empty_order_id(self, oms: OrderManagementSystem):
        resp = oms.cancel_order(account_id=_ACCOUNT, order_id="")
        assert resp.success is False

    def test_modify_with_empty_order_id(self, oms: OrderManagementSystem):
        resp = oms.modify_order(account_id=_ACCOUNT, order_id="")
        assert resp.success is False


@pytest.mark.integration
class TestOMSIdempotency:
    """Tests for idempotency via correlation_id."""

    def test_idempotency_cache_prevents_duplicates(self, oms: OrderManagementSystem):
        first = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="dup-123",
        )
        assert first.success is True

        second = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="dup-123",
        )
        assert second.success is False
        assert "already executed" in second.message.lower()

    def test_different_correlation_ids_allowed(self, oms: OrderManagementSystem):
        first = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="corr-a",
        )
        assert first.success

        second = oms.place_order(
            account_id=_ACCOUNT,
            symbol="TCS",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            correlation_id="corr-b",
        )
        assert second.success

    def test_idempotency_metrics(self, oms: OrderManagementSystem):
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="metrics-123",
        )
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="metrics-123",
        )
        m = oms.metrics()
        assert m["idempotency_hits"] == 1

    def test_clear_idempotency_cache(self, oms: OrderManagementSystem):
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="clear-test",
        )
        oms.clear_idempotency_cache()
        second = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="clear-test",
        )
        # After clearing cache, same correlation_id should succeed
        assert second.success is True


@pytest.mark.integration
class TestOMSKillSwitch:
    """Tests for kill switch functionality."""

    def test_kill_switch_blocks_order(self, oms: OrderManagementSystem):
        oms.kill_switch = True
        resp = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert resp.success is False
        assert resp.error_code == "KILL_SWITCH_ACTIVE"

    def test_kill_switch_metrics(self, oms: OrderManagementSystem):
        oms.kill_switch = True
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        m = oms.metrics()
        assert m["orders_kill_switched"] == 1

    def test_kill_switch_disabled_allows_orders(self, oms: OrderManagementSystem):
        oms.kill_switch = True
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        m_before = oms.metrics()["orders_placed"]

        oms.kill_switch = False
        resp = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert resp.success is True

    def test_kill_switch_property(self, oms: OrderManagementSystem):
        assert oms.kill_switch is False
        oms.kill_switch = True
        assert oms.kill_switch is True
        oms.kill_switch = False
        assert oms.kill_switch is False


@pytest.mark.integration
class TestOMSEventPublishing:
    """Tests for event publishing through the event bus."""

    def test_order_placed_event(self, oms: OrderManagementSystem, event_bus: _RecordingEventBus):
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        placed_events = [e for e in event_bus.events if isinstance(e, OrderPlacedEvent)]
        assert len(placed_events) == 1
        assert placed_events[0].symbol == "RELIANCE"
        assert placed_events[0].quantity == 10

    def test_order_cancelled_event(self, oms: OrderManagementSystem, event_bus: _RecordingEventBus):
        placed = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        oms.cancel_order(account_id=_ACCOUNT, order_id=placed.order_id)
        cancelled_events = [e for e in event_bus.events if isinstance(e, OrderCancelledEvent)]
        assert len(cancelled_events) == 1
        assert cancelled_events[0].order_id == placed.order_id

    def test_order_modified_event(self, oms: OrderManagementSystem, event_bus: _RecordingEventBus):
        placed = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        oms.modify_order(
            account_id=_ACCOUNT,
            order_id=placed.order_id,
            quantity=15,
        )
        modified_events = [e for e in event_bus.events if isinstance(e, OrderModifiedEvent)]
        assert len(modified_events) == 1

    def test_order_rejected_event_no_events_for_kill_switch(
        self, oms: OrderManagementSystem, event_bus: _RecordingEventBus
    ):
        """When kill switch is active, no event is published (early return)."""
        oms.kill_switch = True
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        rejected_events = [e for e in event_bus.events if isinstance(e, OrderRejectedEvent)]
        assert len(rejected_events) == 0


@pytest.mark.integration
class TestOMSOrderQueries:
    """Tests for get_orderbook, get_active_orders, and get_order."""

    def test_get_orderbook(self, oms: OrderManagementSystem):
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="TCS",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
        )
        book = oms.get_orderbook(account_id=_ACCOUNT)
        assert len(book) == 2

    def test_get_active_orders(self, oms: OrderManagementSystem):
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        placed = oms.place_order(
            account_id=_ACCOUNT,
            symbol="TCS",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
        )
        oms.cancel_order(account_id=_ACCOUNT, order_id=placed.order_id)
        active = oms.get_active_orders(account_id=_ACCOUNT)
        assert len(active) == 1
        assert active[0].symbol == "RELIANCE"

    def test_get_order_by_id(self, oms: OrderManagementSystem):
        placed = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        order = oms.get_order(account_id=_ACCOUNT, order_id=placed.order_id)
        assert order is not None
        assert order.order_id == placed.order_id
        assert order.symbol == "RELIANCE"

    def test_get_nonexistent_order(self, oms: OrderManagementSystem):
        order = oms.get_order(account_id=_ACCOUNT, order_id="NONEXISTENT")
        assert order is None

    def test_order_repository_contains_order(
        self, oms: OrderManagementSystem, order_repository: OrderRepository
    ):
        placed = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert placed.order_id in order_repository


@pytest.mark.integration
class TestOMSValidation:
    """Tests for basic validation in place_order."""

    def test_validate_empty_symbol_raises(self, oms: OrderManagementSystem):
        with pytest.raises(Exception):
            oms.place_order(
                account_id=_ACCOUNT,
                symbol="",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
            )

    def test_validate_negative_quantity_raises(self, oms: OrderManagementSystem):
        with pytest.raises(Exception):
            oms.place_order(
                account_id=_ACCOUNT,
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=-1,
            )

    def test_validation_failure_metrics(self, oms: OrderManagementSystem):
        with pytest.raises(Exception):
            oms.place_order(
                account_id=_ACCOUNT,
                symbol="",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
            )
        m = oms.metrics()
        assert m["validation_failures"] == 1


@pytest.mark.integration
class TestOMSMetrics:
    """Tests for OMS metrics tracking."""

    def test_metrics_placed_and_rejected(self, oms: OrderManagementSystem):
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        m = oms.metrics()
        assert m["orders_placed"] == 1
        assert m["orders_rejected"] == 0

    def test_metrics_cancel_and_modify(self, oms: OrderManagementSystem):
        placed = oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        oms.cancel_order(account_id=_ACCOUNT, order_id=placed.order_id)
        m = oms.metrics()
        assert m["cancellations"] == 1

    def test_metrics_snapshot_isolation(self, oms: OrderManagementSystem):
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        snap = oms.metrics()
        oms.place_order(
            account_id=_ACCOUNT,
            symbol="TCS",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
        )
        # Snapshot should reflect state at time of capture
        assert snap["orders_placed"] == 1
        assert oms.metrics()["orders_placed"] == 2


@pytest.mark.integration
class TestOMSRepresentation:
    """Tests for string representation."""

    def test_repr(self, oms: OrderManagementSystem):
        rep = repr(oms)
        assert "OrderManagementSystem" in rep
        assert "paper" in rep
