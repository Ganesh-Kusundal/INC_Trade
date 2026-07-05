"""Tests for ExecutionRouter — account-based order routing to broker adapters."""

from __future__ import annotations

from decimal import Decimal

import pytest

from inc_trade.domain.entities import Order, OrderResponse
from inc_trade.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from inc_trade.domain.exceptions import BrokerError
from inc_trade.ports.order_execution import OrderExecutionPort
from brokers.trading.execution_router import ExecutionRouter


class _FakeOrderExecution:
    """Minimal OrderExecutionPort implementation for testing."""

    def __init__(self, broker_id: str = "dhan") -> None:
        self.broker_id = broker_id
        self.orders: list[Order] = []
        self.last_place_args = None

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
        self.last_place_args = dict(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
        )
        order_id = f"{self.broker_id}-{len(self.orders) + 1:04d}"
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
        self.orders.append(order)
        return OrderResponse(order_id=order_id, success=True, status=OrderStatus.OPEN)

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> OrderResponse:
        return OrderResponse(order_id=order_id, success=True)

    def cancel_order(self, order_id: str) -> OrderResponse:
        return OrderResponse(order_id=order_id, success=True)

    def get_order(self, order_id: str) -> Order | None:
        for o in self.orders:
            if o.order_id == order_id:
                return o
        return None

    def get_orderbook(self) -> list[Order]:
        return list(self.orders)


@pytest.fixture
def dhan_adapter() -> _FakeOrderExecution:
    return _FakeOrderExecution(broker_id="dhan")


@pytest.fixture
def upstox_adapter() -> _FakeOrderExecution:
    return _FakeOrderExecution(broker_id="upstox")


@pytest.fixture
def router(dhan_adapter, upstox_adapter) -> ExecutionRouter:
    r = ExecutionRouter()
    r.register_adapter("dhan", dhan_adapter)
    r.register_adapter("upstox", upstox_adapter)
    return r


class TestExecutionRouter:
    """Comprehensive test suite for ExecutionRouter."""

    # ── Adapter Management ─────────────────────────────────────────────

    def test_register_and_route(self, router, dhan_adapter):
        """Registered adapter can be routed by account_id."""
        adapter = router.route("dhan/default")
        assert adapter is dhan_adapter

    def test_route_multiple_brokers(self, router, dhan_adapter, upstox_adapter):
        """Correct adapter returned for each broker."""
        assert router.route("dhan/default") is dhan_adapter
        assert router.route("upstox/default") is upstox_adapter

    def test_route_unknown_account_raises(self, router):
        """Unknown account_id raises BrokerError with helpful message."""
        with pytest.raises(BrokerError, match="No execution adapter registered"):
            router.route("unknown/default")

    def test_route_invalid_account_format(self, router):
        """Invalid account_id format (no '/') raises BrokerError."""
        with pytest.raises(BrokerError, match="Invalid account_id format"):
            router.route("invalid-format")

    def test_unregister_adapter(self, router):
        """Unregistered adapter is no longer available."""
        router.unregister_adapter("upstox")
        assert "upstox" not in router.registered_brokers
        with pytest.raises(BrokerError):
            router.route("upstox/default")

    def test_unregister_unknown_returns_false(self, router):
        """Unregistering unknown broker returns False (not error)."""
        result = router.unregister_adapter("nonexistent")
        assert result is False

    def test_registered_brokers_list(self, router):
        """registered_brokers returns list of registered broker IDs."""
        brokers = router.registered_brokers
        assert "dhan" in brokers
        assert "upstox" in brokers

    # ── Place Order Routing ────────────────────────────────────────────

    def test_place_order_routes_to_dhan(self, router, dhan_adapter):
        """Place order routes to the correct broker adapter."""
        resp = router.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        assert resp.success
        assert dhan_adapter.last_place_args is not None
        assert dhan_adapter.last_place_args["symbol"] == "RELIANCE"

    def test_place_order_routes_to_upstox(self, router, upstox_adapter):
        """Place order routes to Upstox when account is upstox/default."""
        resp = router.place_order(
            account_id="upstox/default",
            symbol="TCS",
            exchange="NSE",
            side=Side.SELL,
            quantity=5,
        )
        assert resp.success
        assert upstox_adapter.last_place_args is not None
        assert upstox_adapter.last_place_args["symbol"] == "TCS"

    def test_place_order_passes_all_args(self, router, dhan_adapter):
        """All order parameters are passed through to adapter."""
        router.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=Decimal("2500"),
            product_type=ProductType.DELIVERY,
            validity=Validity.DAY,
            trigger_price=Decimal("0"),
        )
        args = dhan_adapter.last_place_args
        assert args["symbol"] == "RELIANCE"
        assert args["exchange"] == "NSE"
        assert args["side"] is Side.BUY
        assert args["quantity"] == 10
        assert args["order_type"] is OrderType.LIMIT
        assert args["price"] == Decimal("2500")
        assert args["product_type"] is ProductType.DELIVERY
        assert args["validity"] is Validity.DAY

    # ── Modify/Cancel/Get Routing ──────────────────────────────────────

    def test_modify_order_routes_correctly(self, router):
        """Modify order routes to correct broker."""
        resp = router.modify_order(
            account_id="dhan/default",
            order_id="ORD-001",
            quantity=15,
        )
        assert resp.success

    def test_cancel_order_routes_correctly(self, router):
        """Cancel order routes to correct broker."""
        resp = router.cancel_order(
            account_id="dhan/default",
            order_id="ORD-001",
        )
        assert resp.success

    def test_get_order_routes_correctly(self, router, dhan_adapter):
        """Get order routes to correct broker."""
        # Place an order first so it exists
        router.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        order = router.get_order("dhan/default", "dhan-0001")
        assert order is not None
        assert order.symbol == "RELIANCE"

    def test_get_orderbook_routes_correctly(self, router):
        """Get order book routes to correct broker."""
        router.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
        )
        orders = router.get_orderbook("dhan/default")
        assert len(orders) == 1

    # ── Edge Cases ─────────────────────────────────────────────────────

    def test_empty_router_raises_on_route(self):
        """Router with no adapters raises BrokerError."""
        r = ExecutionRouter()
        with pytest.raises(BrokerError):
            r.route("dhan/default")

    def test_constructor_accepts_adapters_dict(self, dhan_adapter):
        """Router can be constructed with initial adapters."""
        r = ExecutionRouter(adapters={"dhan": dhan_adapter})
        assert r.route("dhan/default") is dhan_adapter

    def test_repr(self, router):
        """__repr__ shows registered brokers."""
        rep = repr(router)
        assert "ExecutionRouter" in rep
        assert "dhan" in rep
