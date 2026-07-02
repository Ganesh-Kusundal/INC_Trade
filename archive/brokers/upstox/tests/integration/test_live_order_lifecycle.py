"""Live integration tests for Upstox order lifecycle.

Tests get_orderbook(), get_order(), cancel_order() with post-verification,
and order rejection paths against the live Upstox API.

These tests require a valid .env.upstox with UPSTOX_API_KEY and UPSTOX_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.upstox.tests.integration.conftest import skip_live
from domain import OrderStatus


@skip_live
class TestLiveOrderLifecycle:
    """End-to-end order lifecycle tests against live Upstox API."""

    def test_get_orderbook_returns_list(self, gateway):
        """get_orderbook() should return a list of Order objects."""
        orderbook = gateway.get_orderbook()
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

    def test_get_orderbook_order_schema(self, gateway):
        """Order objects should have all required fields."""
        orderbook = gateway.get_orderbook()
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

    def test_order_status_values(self, gateway):
        """Order status should be valid OrderStatus enum values."""
        orderbook = gateway.get_orderbook()
        valid_statuses = {
            OrderStatus.OPEN,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.MODIFIED,
            OrderStatus.TRIGGER_PENDING,
        }
        for order in orderbook:
            if order.status is not None:
                assert order.status in valid_statuses, f"Invalid status: {order.status}"

    def test_cancel_nonexistent_order_returns_failure(self, gateway):
        """Cancelling a non-existent order should return failure, not raise."""
        # Skip if live orders are disabled (safety guard)
        import os
        if not os.environ.get("UPSTOX_ALLOW_LIVE_ORDERS"):
            pytest.skip("Live orders disabled (UPSTOX_ALLOW_LIVE_ORDERS not set)")

        # Use a clearly fake order ID
        response = gateway.cancel_order("NONEXISTENT-ORDER-123456")
        assert response.success is False
        assert response.message is not None

    def test_get_order_for_nonexistent_id(self, gateway):
        """get_order() for non-existent ID should return None."""
        order = gateway.get_order("NONEXISTENT-ORDER-123456")
        assert order is None


@skip_live
class TestLiveOrderValidation:
    """Order validation and rejection path tests."""

    def test_place_order_rejects_invalid_symbol(self, gateway):
        """Placing order with invalid symbol should fail gracefully."""
        response = gateway.place_order(
            symbol="DOESNOTEXIST123",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="LIMIT",
            product_type="INTRADAY",
            price=Decimal("100"),
        )
        assert response.success is False
        assert response.message is not None

    def test_place_order_rejects_invalid_exchange(self, gateway):
        """Placing order with invalid exchange should fail."""
        try:
            response = gateway.place_order(
                symbol="RELIANCE",
                exchange="INVALID_EXCHANGE",
                side="BUY",
                quantity=1,
                order_type="MARKET",
                product_type="INTRADAY",
            )
            # If it doesn't raise, it should fail
            assert response.success is False
        except (ValueError, KeyError):
            # Raising for invalid exchange is also acceptable
            pass

    def test_place_order_rejects_zero_quantity(self, gateway):
        """Placing order with zero quantity should fail."""
        response = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=0,
            order_type="MARKET",
            product_type="INTRADAY",
        )
        assert response.success is False

    def test_place_order_rejects_negative_quantity(self, gateway):
        """Placing order with negative quantity should fail."""
        response = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=-10,
            order_type="MARKET",
            product_type="INTRADAY",
        )
        assert response.success is False
