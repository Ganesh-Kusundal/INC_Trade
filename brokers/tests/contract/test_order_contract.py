"""Contract tests — OrderExecutionPort protocol compliance."""

from __future__ import annotations

import pytest
from brokers.domain import OrderResponse, Side
from brokers.ports.order_execution import OrderExecutionPort


class OrderContractTests:
    """Mixin-style contract tests for OrderExecutionPort."""

    def test_place_order_market(self, orders: OrderExecutionPort) -> None:
        resp = orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
        assert isinstance(resp, OrderResponse)

    def test_place_order_returns_order_id(self, orders: OrderExecutionPort) -> None:
        resp = orders.place_order("TCS", "NSE", Side.BUY, 5)
        if resp.success:
            assert len(resp.order_id) > 0

    def test_cancel_order(self, orders: OrderExecutionPort) -> None:
        resp = orders.cancel_order("TEST_ORDER")
        assert isinstance(resp, OrderResponse)

    def test_get_order(self, orders: OrderExecutionPort) -> None:
        from brokers.domain import Order

        order = orders.get_order("TEST_ORDER")
        assert order is None or isinstance(order, Order)

    def test_get_orderbook(self, orders: OrderExecutionPort) -> None:
        book = orders.get_orderbook()
        assert isinstance(book, list)

    def test_modify_order(self, orders: OrderExecutionPort) -> None:
        resp = orders.modify_order("TEST_ORDER", quantity=15)
        assert isinstance(resp, OrderResponse)


@pytest.mark.contract
class TestOrderContractConformance:
    """Base test class — override ``orders`` fixture for each broker."""

    @pytest.fixture
    def orders(self) -> OrderExecutionPort:
        pytest.skip("No concrete OrderExecutionPort fixture provided")

    def test_place_order_market(self, orders: OrderExecutionPort) -> None:
        OrderContractTests().test_place_order_market(orders)

    def test_place_order_returns_order_id(self, orders: OrderExecutionPort) -> None:
        OrderContractTests().test_place_order_returns_order_id(orders)

    def test_cancel_order(self, orders: OrderExecutionPort) -> None:
        OrderContractTests().test_cancel_order(orders)

    def test_get_order(self, orders: OrderExecutionPort) -> None:
        OrderContractTests().test_get_order(orders)

    def test_get_orderbook(self, orders: OrderExecutionPort) -> None:
        OrderContractTests().test_get_orderbook(orders)

    def test_modify_order(self, orders: OrderExecutionPort) -> None:
        OrderContractTests().test_modify_order(orders)


class TestDhanOrderContract(TestOrderContractConformance):
    @pytest.fixture
    def orders(self) -> OrderExecutionPort:
        pytest.skip("Dhan integration test — requires credentials")


class TestUpstoxOrderContract(TestOrderContractConformance):
    @pytest.fixture
    def orders(self) -> OrderExecutionPort:
        pytest.skip("Upstox integration test — requires credentials")


class TestPaperOrderContract(TestOrderContractConformance):
    @pytest.fixture
    def orders(self) -> OrderExecutionPort:
        from brokers.adapters.paper.gateway import PaperGateway

        gw = PaperGateway()
        return gw.orders
