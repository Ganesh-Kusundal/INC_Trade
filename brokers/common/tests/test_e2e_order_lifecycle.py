"""E2E order lifecycle test skeleton.

These tests require live broker credentials and are marked with
``@pytest.mark.live`` so they are skipped by default. Run with:

    pytest -m live brokers/common/tests/test_e2e_order_lifecycle.py

The tests verify the full place → status → modify → cancel flow
against a real broker API.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from domain import Order, OrderStatus, OrderType, Side

LIVE = pytest.mark.skipif(
    not os.environ.get("TRADEX_LIVE_TESTS"),
    reason="Set TRADEX_LIVE_TESTS=1 and configure broker credentials to run live E2E tests",
)


@LIVE
class TestDhanE2EOrderLifecycle:
    @pytest.fixture()
    def dhan_gateway(self):
        from brokers.dhan.factory import BrokerFactory

        factory = BrokerFactory()
        return factory.create()

    def test_place_status_cancel_flow(self, dhan_gateway):
        from domain import OrderRequest

        request = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=1,
            price=Decimal("2000"),
            product_type="CNC",
        )
        response = dhan_gateway.place_order(request)
        assert response.success, f"Place failed: {response.error}"
        assert response.order_id

        orders = dhan_gateway.get_orderbook()
        placed = [o for o in orders if o.order_id == response.order_id]
        assert len(placed) == 1
        assert placed[0].status in (OrderStatus.OPEN, OrderStatus.TRANSIT)

        cancel_response = dhan_gateway.cancel_order(response.order_id)
        assert cancel_response.success

    def test_modify_order_lifecycle(self, dhan_gateway):
        from domain import OrderRequest

        request = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=1,
            price=Decimal("2000"),
            product_type="CNC",
        )
        response = dhan_gateway.place_order(request)
        assert response.success

        modified = dhan_gateway.orders.modify_order(
            response.order_id,
            price=Decimal("2001"),
        )
        assert isinstance(modified, Order)

        dhan_gateway.cancel_order(response.order_id)


@LIVE
class TestUpstoxE2EOrderLifecycle:
    @pytest.fixture()
    def upstox_gateway(self):
        from brokers.upstox.factory import UpstoxBrokerFactory

        factory = UpstoxBrokerFactory()
        return factory.create()

    def test_place_status_cancel_flow(self, upstox_gateway):
        from domain import OrderRequest

        request = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=1,
            price=Decimal("2000"),
            product_type="D",
        )
        response = upstox_gateway.place_order(request)
        assert response.success, f"Place failed: {response.error}"

        orders = upstox_gateway.get_orderbook()
        placed = [o for o in orders if o.order_id == response.order_id]
        assert len(placed) == 1

        upstox_gateway.cancel_order(response.order_id)
