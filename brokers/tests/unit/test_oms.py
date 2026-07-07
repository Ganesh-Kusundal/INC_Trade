"""Tests for OrderManagementSystem — order lifecycle orchestration."""

from __future__ import annotations

from decimal import Decimal

import pytest
from brokers.domain.entities import Order, OrderResponse
from brokers.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from brokers.domain.exceptions import ValidationError
from brokers.trading.execution_router import ExecutionRouter
from brokers.trading.oms import OrderManagementSystem
from brokers.trading.order_repository import OrderRepository


class _FakeOrderExecution:
    """Minimal OrderExecutionPort for testing OMS."""

    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}
        self.fail_next = False
        self.fail_message = ""

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
    ) -> OrderResponse:
        if self.fail_next:
            self.fail_next = False
            return OrderResponse.fail(self.fail_message, error_code="BROKER_ERROR")
        order_id = f"BROKER-{len(self.orders) + 1:04d}"
        order = Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            status=OrderStatus.OPEN,
            price=price,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
        )
        self.orders[order_id] = order
        return OrderResponse(order_id=order_id, success=True, status=OrderStatus.OPEN)

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> OrderResponse:
        if order_id not in self.orders:
            return OrderResponse.fail(f"Order {order_id} not found")
        return OrderResponse(order_id=order_id, success=True)

    def cancel_order(self, order_id: str) -> OrderResponse:
        if order_id not in self.orders:
            return OrderResponse.fail(f"Order {order_id} not found")
        self.orders[order_id] = Order(
            order_id=order_id,
            symbol=self.orders[order_id].symbol,
            exchange=self.orders[order_id].exchange,
            side=self.orders[order_id].side,
            quantity=self.orders[order_id].quantity,
            status=OrderStatus.CANCELLED,
            price=self.orders[order_id].price,
        )
        return OrderResponse(order_id=order_id, success=True, status=OrderStatus.CANCELLED)

    def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    def get_orderbook(self) -> list[Order]:
        return list(self.orders.values())


@pytest.fixture
def adapter() -> _FakeOrderExecution:
    return _FakeOrderExecution()


@pytest.fixture
def router(adapter) -> ExecutionRouter:
    r = ExecutionRouter()
    r.register_adapter("dhan", adapter)
    return r


@pytest.fixture
def repository() -> OrderRepository:
    return OrderRepository()


@pytest.fixture
def oms(router, repository) -> OrderManagementSystem:
    return OrderManagementSystem(
        execution_router=router,
        order_repository=repository,
        kill_switch=False,
    )


class TestOrderManagementSystem:
    """Comprehensive test suite for OrderManagementSystem."""

    # ── Basic Order Placement ──────────────────────────────────────────

    def test_place_order_success(self, oms):
        """Successful order returns OrderResponse with order_id."""
        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert resp.success
        assert resp.order_id
        assert resp.order_id.startswith("BROKER-")

    def test_place_order_saves_to_repository(self, oms, repository):
        """Order is saved in repository after successful placement."""
        oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        # Repository should have the order
        assert repository.count() > 0
        saved_orders = repository.get_by_account("dhan/default")
        assert len(saved_orders) == 1
        assert saved_orders[0].symbol == "RELIANCE"

    # ── Validation ─────────────────────────────────────────────────────

    def test_place_order_validates_symbol(self, oms):
        """Empty symbol raises ValidationError."""
        with pytest.raises(ValidationError, match="symbol"):
            oms.place_order(
                account_id="dhan/default",
                symbol="",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
            )

    def test_place_order_validates_exchange(self, oms):
        """Empty exchange raises ValidationError."""
        with pytest.raises(ValidationError, match="exchange"):
            oms.place_order(
                account_id="dhan/default",
                symbol="RELIANCE",
                exchange="",
                side=Side.BUY,
                quantity=10,
            )

    def test_place_order_validates_quantity(self, oms):
        """Zero quantity raises ValidationError."""
        with pytest.raises(ValidationError, match="quantity"):
            oms.place_order(
                account_id="dhan/default",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=0,
            )

    def test_place_order_validates_negative_quantity(self, oms):
        """Negative quantity raises ValidationError."""
        with pytest.raises(ValidationError, match="quantity"):
            oms.place_order(
                account_id="dhan/default",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=-5,
            )

    def test_place_order_limit_requires_price(self, oms):
        """LIMIT order with zero price raises ValidationError."""
        with pytest.raises(ValidationError, match="price"):
            oms.place_order(
                account_id="dhan/default",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
                order_type=OrderType.LIMIT,
                price=Decimal("0"),
            )

    def test_place_order_stop_requires_trigger(self, oms):
        """STOP_LOSS order with zero trigger_price raises ValidationError."""
        with pytest.raises(ValidationError, match="trigger_price"):
            oms.place_order(
                account_id="dhan/default",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
                order_type=OrderType.STOP_LOSS,
                price=Decimal("2500"),
                trigger_price=Decimal("0"),
            )

    # ── Kill Switch ────────────────────────────────────────────────────

    def test_place_order_kill_switch_blocks(self, router, repository):
        """Kill switch blocks order placement."""
        oms = OrderManagementSystem(
            execution_router=router,
            order_repository=repository,
            kill_switch=True,
        )
        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert not resp.success
        assert "kill switch" in resp.message.lower() or "disabled" in resp.message.lower()

    def test_kill_switch_dynamic_toggle(self, oms):
        """Kill switch can be toggled at runtime."""
        assert oms.kill_switch is False

        oms.kill_switch = True
        assert oms.kill_switch is True
        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert not resp.success

        oms.kill_switch = False
        assert oms.kill_switch is False
        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert resp.success

    # ── Idempotency ────────────────────────────────────────────────────

    def test_place_order_idempotency(self, oms):
        """Same correlation_id returns cached response."""
        resp1 = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="corr-001",
        )
        assert resp1.success

        resp2 = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="corr-001",
        )
        # Should be the same order
        assert resp2.order_id == resp1.order_id
        assert not resp2.success  # Idempotency conflict

    def test_place_order_idempotency_different_keys(self, oms):
        """Different correlation_ids are treated as separate orders."""
        resp1 = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="corr-001",
        )
        resp2 = oms.place_order(
            account_id="dhan/default",
            symbol="TCS",
            exchange="NSE",
            side=Side.SELL,
            quantity=5,
            correlation_id="corr-002",
        )
        assert resp1.order_id != resp2.order_id
        assert resp1.success
        assert resp2.success

    def test_place_order_without_correlation_id(self, oms):
        """Orders without correlation_id are not cached for idempotency."""
        resp1 = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        resp2 = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        # No correlation_id means no idempotency — each is a new order
        assert resp1.success
        assert resp2.success

    # ── Cancel & Modify ────────────────────────────────────────────────

    def test_cancel_order(self, oms, adapter):
        """Cancel delegated to correct broker adapter."""
        # Place first
        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert resp.success

        # Cancel
        cancel_resp = oms.cancel_order("dhan/default", resp.order_id)
        assert cancel_resp.success

    def test_cancel_order_empty_id(self, oms):
        """Cancelling with empty order_id returns failure (not exception)."""
        resp = oms.cancel_order("dhan/default", "")
        assert not resp.success
        assert "required" in resp.message.lower()

    def test_modify_order(self, oms, adapter):
        """Modify delegated to correct broker adapter."""
        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert resp.success

        modify_resp = oms.modify_order(
            account_id="dhan/default",
            order_id=resp.order_id,
            quantity=15,
        )
        assert modify_resp.success

    def test_modify_order_empty_id(self, oms):
        """Modifying with empty order_id returns failure."""
        resp = oms.modify_order("dhan/default", "")
        assert not resp.success
        assert "required" in resp.message.lower()

    # ── Get Order ──────────────────────────────────────────────────────

    def test_get_order_from_repository(self, oms):
        """Get order checks local repository first (fast path)."""
        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        order = oms.get_order("dhan/default", resp.order_id)
        assert order is not None
        assert order.order_id == resp.order_id
        assert order.symbol == "RELIANCE"

    def test_get_orderbook(self, oms):
        """Get orderbook returns all orders from broker."""
        oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        oms.place_order(
            account_id="dhan/default",
            symbol="TCS",
            exchange="NSE",
            side=Side.SELL,
            quantity=5,
        )
        orders = oms.get_orderbook("dhan/default")
        assert len(orders) == 2

    def test_get_active_orders(self, oms):
        """get_active_orders returns non-terminal orders from repository."""
        oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        active = oms.get_active_orders("dhan/default")
        assert len(active) == 1
        assert active[0].symbol == "RELIANCE"

    # ── Multi-Broker Routing ───────────────────────────────────────────

    def test_multi_broker_routing(self):
        """OMS routes to correct broker based on account_id."""
        dhan_adapter = _FakeOrderExecution()
        upstox_adapter = _FakeOrderExecution()

        router = ExecutionRouter()
        router.register_adapter("dhan", dhan_adapter)
        router.register_adapter("upstox", upstox_adapter)

        repo = OrderRepository()
        oms = OrderManagementSystem(execution_router=router, order_repository=repo)

        # Place on Dhan
        dhan_resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert dhan_resp.success
        assert dhan_resp.order_id.startswith("BROKER-")

        # Place on Upstox
        upstox_resp = oms.place_order(
            account_id="upstox/default",
            symbol="TCS",
            exchange="NSE",
            side=Side.SELL,
            quantity=5,
        )
        assert upstox_resp.success
        assert upstox_resp.order_id.startswith("BROKER-")

        # Verify they went to different adapters
        assert len(dhan_adapter.orders) == 1
        assert len(upstox_adapter.orders) == 1

    # ── Error Handling ─────────────────────────────────────────────────

    def test_place_order_broker_failure(self, oms, adapter):
        """Broker failure returns failed OrderResponse (not exception)."""
        adapter.fail_next = True
        adapter.fail_message = "Insufficient margin"
        resp = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert not resp.success
        assert "margin" in resp.message.lower()

    def test_place_order_unknown_account(self, oms):
        """Unknown account raises BrokerError."""
        with pytest.raises(Exception):
            oms.place_order(
                account_id="unknown/default",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
            )

    # ── Thread Safety ──────────────────────────────────────────────────

    def test_thread_safety(self):
        """Concurrent order placement from multiple threads is safe."""
        import threading

        adapter = _FakeOrderExecution()
        router = ExecutionRouter()
        router.register_adapter("dhan", adapter)
        repo = OrderRepository()
        oms = OrderManagementSystem(execution_router=router, order_repository=repo)

        errors = []

        def place_order(idx: int) -> None:
            try:
                oms.place_order(
                    account_id="dhan/default",
                    symbol="RELIANCE",
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=10,
                    correlation_id=f"corr-{idx:04d}",
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=place_order, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert repo.count() == 30
        assert len(adapter.orders) == 30

    # ── Representatation ───────────────────────────────────────────────

    def test_repr(self, oms):
        """__repr__ shows OMS state."""
        rep = repr(oms)
        assert "OrderManagementSystem" in rep
        assert "kill_switch" in rep
