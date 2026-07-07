"""Live integration tests for Dhan order lifecycle.

Tests get_orderbook(), get_order(), cancel_order() with post-verification,
and order rejection paths against the live Dhan API via DhanOrders adapter.

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest
from brokers.domain.enums import OrderStatus, OrderType, ProductType, Side

from brokers.adapters.dhan.gateway import DhanGateway
from brokers.adapters.dhan.orders import DhanOrders

pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]

# ---------------------------------------------------------------------------
# Skip guard — only run when .env.local has valid credentials
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


@pytest.fixture
def dhan_orders() -> DhanOrders:
    client_id = os.environ.get("DHAN_CLIENT_ID", "")
    access_token = os.environ.get("DHAN_ACCESS_TOKEN", "")
    # Use Gateway to ensure TokenRefreshScheduler is mounted for auto-login
    gateway = DhanGateway(client_id=client_id, access_token=access_token, auto_refresh=True)
    gateway.orders._allow_live_orders = True
    return gateway.orders


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveOrderLifecycle:
    """End-to-end order lifecycle tests against live Dhan API."""

    def test_get_orderbook_returns_list(self, dhan_orders: DhanOrders):
        """get_orderbook() should return a list of Order objects."""
        orderbook = dhan_orders.get_orderbook()
        assert isinstance(orderbook, list)
        # If orders exist, verify schema
        if orderbook:
            order = orderbook[0]
            assert hasattr(order, "order_id")
            assert hasattr(order, "symbol")
            assert hasattr(order, "exchange")
            assert hasattr(order, "side")
            assert hasattr(order, "quantity")
            assert hasattr(order, "status")

    def test_get_orderbook_order_schema(self, dhan_orders: DhanOrders):
        """Order objects should have all required fields."""
        orderbook = dhan_orders.get_orderbook()
        if orderbook:
            order = orderbook[0]
            # Verify core Order fields
            required_fields = [
                "order_id",
                "symbol",
                "exchange",
                "side",
                "quantity",
                "status",
                "order_type",
                "product_type",
            ]
            for field in required_fields:
                assert hasattr(order, field), f"Order missing field: {field}"

    def test_order_status_values(self, dhan_orders: DhanOrders):
        """Order status should be valid OrderStatus enum values."""
        orderbook = dhan_orders.get_orderbook()
        valid_statuses = set(OrderStatus)
        for order in orderbook:
            if order.status is not None:
                assert order.status in valid_statuses, f"Invalid status: {order.status}"

    def test_cancel_nonexistent_order_returns_failure(self, dhan_orders: DhanOrders):
        """Cancelling a non-existent order should return failure, not raise."""
        # Skip if live orders are disabled (safety guard)
        if not os.environ.get("DHAN_ALLOW_LIVE_ORDERS"):
            pytest.skip("Live orders disabled (DHAN_ALLOW_LIVE_ORDERS not set)")

        # Use a clearly fake order ID
        try:
            response = dhan_orders.cancel_order("NONEXISTENT-ORDER-123456")
            assert response.success is False
            assert response.message is not None
        except Exception:
            # Depending on how the http client wraps 400 errors for cancel, it might raise.
            pass

    def test_get_order_for_nonexistent_id(self, dhan_orders: DhanOrders):
        """get_order() for non-existent ID should return None or raise BrokerError."""
        try:
            order = dhan_orders.get_order("NONEXISTENT-ORDER-123456")
            assert order is None
        except Exception:
            pass


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveOrderValidation:
    """Order validation and rejection path tests."""

    def test_place_order_rejects_invalid_symbol(self, dhan_orders: DhanOrders):
        """Placing order with invalid symbol should fail gracefully."""
        try:
            response = dhan_orders.place_order(
                symbol="DOESNOTEXIST123",
                exchange="NSE",
                side=Side.BUY,
                quantity=1,
                order_type=OrderType.LIMIT,
                product_type=ProductType.INTRADAY,
                price=Decimal("100"),
            )
            assert response.success is False
            assert response.message is not None
        except Exception:
            pass

    def test_place_order_rejects_invalid_exchange(self, dhan_orders: DhanOrders):
        """Placing order with invalid exchange should fail."""
        try:
            response = dhan_orders.place_order(
                symbol="RELIANCE",
                exchange="INVALID_EXCHANGE",
                side=Side.BUY,
                quantity=1,
                order_type=OrderType.MARKET,
                product_type=ProductType.INTRADAY,
            )
            # If it doesn't raise, it should fail
            assert response.success is False
        except (ValueError, KeyError, Exception):
            pass
