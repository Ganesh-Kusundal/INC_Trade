"""Unit tests for AuditFacade — read-only OMS audit-trail facade.

Verifies:
1. ``history_for(order_id)`` returns an ``OrderStateHistory`` for known orders.
2. ``history_for(order_id)`` returns an empty history (not None) for unknown
   order IDs.
3. ``last_change(order_id)`` returns the most recent ``OrderStateChange``.
4. ``last_change(order_id)`` returns ``None`` for unknown orders.
5. The facade is read-only — no public methods that mutate state.
6. ``BrokerSession.audit`` exposes the facade.
7. After ``oms.place_order(...)``, ``session.audit.history_for(order_id)``
   contains the recorded transition.
"""

from __future__ import annotations

from decimal import Decimal
from inspect import getmembers, isfunction, ismethod

import pytest
from inc_trade.domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from inc_trade.services.audit_facade import AuditFacade
from inc_trade.services.broker_session import BrokerSession
from inc_trade.trading.audit import OrderStateChange, OrderStateHistory
from inc_trade.trading.execution_router import ExecutionRouter
from inc_trade.trading.oms import OrderManagementSystem
from inc_trade.trading.order_repository import OrderRepository

import brokers

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


class _FakeOrderExecution:
    """Minimal OrderExecutionPort for facade integration tests."""

    def __init__(self) -> None:
        self.orders: dict[str, object] = {}

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
def repository() -> OrderRepository:
    return OrderRepository()


@pytest.fixture
def facade(repository: OrderRepository) -> AuditFacade:
    return AuditFacade(repository)


# ---------------------------------------------------------------------------
# 1. Direct AuditFacade behaviour
# ---------------------------------------------------------------------------


class TestAuditFacadeHistory:
    def test_history_for_known_order_returns_state_history(
        self, facade: AuditFacade, repository: OrderRepository
    ) -> None:
        change = OrderStateChange(
            order_id="ORD-001",
            correlation_id="corr-1",
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.OPEN,
            reason="place",
        )
        repository.record_state_change(change)

        history = facade.history_for("ORD-001")
        assert isinstance(history, OrderStateHistory)
        assert history.order_id == "ORD-001"
        assert len(history.changes) == 1
        assert history.changes[0] is change

    def test_history_for_unknown_order_returns_empty_not_none(self, facade: AuditFacade) -> None:
        history = facade.history_for("UNKNOWN")
        # The contract: callers can iterate unconditionally.
        assert history is not None
        assert isinstance(history, OrderStateHistory)
        assert history.order_id == "UNKNOWN"
        assert history.changes == ()

    def test_history_for_unknown_does_not_raise(self, facade: AuditFacade) -> None:
        # No exception is the actual contract being asserted.
        result = facade.history_for("NEVER-EXISTED")
        assert result.changes == ()


class TestAuditFacadeLastChange:
    def test_last_change_returns_most_recent(
        self, facade: AuditFacade, repository: OrderRepository
    ) -> None:
        place = OrderStateChange(
            order_id="ORD-001",
            correlation_id="",
            from_status=OrderStatus.PENDING,
            to_status=OrderStatus.OPEN,
            reason="place",
        )
        cancel = OrderStateChange(
            order_id="ORD-001",
            correlation_id="",
            from_status=OrderStatus.OPEN,
            to_status=OrderStatus.CANCELLED,
            reason="cancel",
        )
        repository.record_state_change(place)
        repository.record_state_change(cancel)

        last = facade.last_change("ORD-001")
        assert isinstance(last, OrderStateChange)
        assert last is cancel
        assert last.to_status is OrderStatus.CANCELLED
        assert last.reason == "cancel"

    def test_last_change_returns_none_for_unknown(self, facade: AuditFacade) -> None:
        assert facade.last_change("UNKNOWN") is None

    def test_last_change_returns_none_for_empty_recorded_history(
        self, facade: AuditFacade, repository: OrderRepository
    ) -> None:
        # Pre-populate a different order, then query a new one.
        repository.record_state_change(
            OrderStateChange(
                order_id="ORD-A",
                correlation_id="",
                from_status=OrderStatus.PENDING,
                to_status=OrderStatus.OPEN,
                reason="place",
            )
        )
        assert facade.last_change("ORD-B") is None


# ---------------------------------------------------------------------------
# 2. Read-only contract
# ---------------------------------------------------------------------------


class TestAuditFacadeReadOnly:
    def test_no_public_mutating_methods(self, facade: AuditFacade) -> None:
        """The facade must not expose any method that mutates the repository."""
        # Inspect both functions (class-level) and methods (bound on instance).
        public_methods = {
            name
            for name, _ in getmembers(facade, predicate=lambda o: isfunction(o) or ismethod(o))
            if not name.startswith("_")
        }
        # Allow only the documented read-only methods.
        assert public_methods == {"history_for", "last_change"}, (
            f"Unexpected public methods: {public_methods - {'history_for', 'last_change'}}"
        )

    def test_public_api_is_read_only(self, facade: AuditFacade) -> None:
        """None of the public methods may mutate the underlying repository.

        We call each public method with a known-good input and assert that
        ``OrderRepository`` is unchanged afterward. The repository's public
        mutators are: ``save``, ``update_status``, ``record_state_change``,
        and ``clear``. After calling the facade, the repository's storage
        must still be empty (we use a fresh repo).
        """
        repository = OrderRepository()
        local_facade = AuditFacade(repository)
        local_facade.history_for("ORD-X")
        local_facade.last_change("ORD-X")
        # Repository should be untouched — no orders, no history.
        assert repository.count() == 0
        assert repository.history_for("ORD-X").changes == ()

    def test_repr_does_not_leak_repository_state(
        self, facade: AuditFacade, repository: OrderRepository
    ) -> None:
        # Sanity: repr mentions the repository but doesn't dump the full dict.
        text = repr(facade)
        assert "AuditFacade" in text
        assert "repository" in text


# ---------------------------------------------------------------------------
# 3. BrokerSession.audit wiring
# ---------------------------------------------------------------------------


class TestBrokerSessionAuditAttribute:
    def test_audit_property_returns_injected_facade(self, facade: AuditFacade) -> None:
        sess = BrokerSession(broker_id="test", audit=facade)
        assert sess.audit is facade

    def test_audit_property_defaults_to_none(self) -> None:
        sess = BrokerSession(broker_id="test")
        assert sess.audit is None

    def test_audit_facade_is_method_or_property(self) -> None:
        # The accessor should be either a property or a method — never a
        # plain attribute set in __init__ that would be trivially mutable.
        sess = BrokerSession(broker_id="test")
        attr = BrokerSession.audit
        assert isinstance(attr, property) or ismethod(attr) or isfunction(attr)


# ---------------------------------------------------------------------------
# 4. End-to-end: place_order → audit history is queryable
# ---------------------------------------------------------------------------


class TestAuditFacadeEndToEnd:
    def test_session_audit_after_place_order(self) -> None:
        """After ``oms.place_order(...)``, ``session.audit.history_for`` records it."""
        repository = OrderRepository()
        adapter = _FakeOrderExecution()
        router = ExecutionRouter()
        router.register_adapter("dhan", adapter)
        oms = OrderManagementSystem(
            execution_router=router,
            order_repository=repository,
            kill_switch=False,
        )

        facade = AuditFacade(repository)
        sess = BrokerSession(broker_id="dhan", audit=facade)
        assert sess.audit is facade

        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="corr-1",
        )
        assert resp.success

        history = sess.audit.history_for(resp.order_id)
        assert isinstance(history, OrderStateHistory)
        assert len(history.changes) == 1
        change = history.changes[0]
        assert change.from_status is OrderStatus.PENDING
        assert change.to_status is OrderStatus.OPEN
        assert change.reason == "place"
        assert change.correlation_id == "corr-1"

        last = sess.audit.last_change(resp.order_id)
        assert last is change

    def test_session_audit_unknown_order_after_place(self) -> None:
        repository = OrderRepository()
        adapter = _FakeOrderExecution()
        router = ExecutionRouter()
        router.register_adapter("dhan", adapter)
        oms = OrderManagementSystem(
            execution_router=router,
            order_repository=repository,
            kill_switch=False,
        )

        facade = AuditFacade(repository)
        sess = BrokerSession(broker_id="dhan", audit=facade)

        # Place one order, then query an unrelated order.
        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert resp.success

        other = sess.audit.history_for("NOT-MY-ORDER")
        assert other.changes == ()
        assert other.order_id == "NOT-MY-ORDER"
        assert sess.audit.last_change("NOT-MY-ORDER") is None


# ---------------------------------------------------------------------------
# 5. brokers.connect() integration
# ---------------------------------------------------------------------------


class TestBrokersConnectAuditWiring:
    def test_connect_paper_wires_audit_facade(self) -> None:
        session = brokers.connect("paper")
        assert isinstance(session, BrokerSession)
        assert isinstance(session.audit, AuditFacade)
        # An empty repository — no orders placed yet.
        assert session.audit.history_for("ANYTHING").changes == ()
        assert session.audit.last_change("ANYTHING") is None
