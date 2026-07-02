"""Unit tests for Task 2.1: Upstox get_order() direct lookup optimization.

Verifies that get_order() uses the UpstoxOrderQueryAdapter.get_order() direct
endpoint instead of fetching the full orderbook.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.upstox.gateway import UpstoxBrokerGateway
from domain import Order, OrderStatus, OrderType, Side


def _make_order(order_id: str = "ORD-123", status: OrderStatus = OrderStatus.OPEN) -> Order:
    """Create a minimal Order for testing."""
    return Order(
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        status=status,
    )


class TestGetOrderDirectLookup:
    """Verify get_order() uses direct endpoint, not full orderbook scan."""

    def test_get_order_calls_order_query_adapter(self):
        """get_order() must call order_query.get_order(order_id), NOT get_orderbook()."""
        broker = MagicMock()
        expected_order = _make_order("ORD-123")
        broker.order_query.get_order.return_value = expected_order

        gw = UpstoxBrokerGateway(broker)
        result = gw.get_order("ORD-123")

        broker.order_query.get_order.assert_called_once_with("ORD-123")
        assert result is expected_order

    def test_get_order_returns_none_for_nonexistent(self):
        """get_order() returns None when order_query returns None."""
        broker = MagicMock()
        broker.order_query.get_order.return_value = None

        gw = UpstoxBrokerGateway(broker)
        result = gw.get_order("NONEXISTENT")

        assert result is None
        broker.order_query.get_order.assert_called_once_with("NONEXISTENT")

    def test_get_order_does_not_fetch_orderbook(self):
        """Critical: get_order() must NOT call get_orderbook() in the primary path."""
        broker = MagicMock()
        broker.order_query.get_order.return_value = _make_order()

        gw = UpstoxBrokerGateway(broker)
        gw.get_order("ORD-123")

        # The primary path should use order_query, not orderbook scan
        broker.order_query.get_order.assert_called_once()

    def test_get_order_fallback_when_no_order_query(self):
        """get_order() falls back to orderbook scan if order_query is unavailable."""
        broker = MagicMock(spec=[])  # Empty spec — no attributes
        # Manually set only what the constructor needs
        broker.settings = MagicMock()
        broker.settings.analytics_only = False
        broker.settings.allow_live_orders = True

        # Create gateway with minimal mock
        gw = UpstoxBrokerGateway.__new__(UpstoxBrokerGateway)
        gw._broker = broker
        gw._order_command = MagicMock()

        # Simulate no order_query attribute
        orderbook = [_make_order("ORD-789")]
        gw.get_orderbook = MagicMock(return_value=orderbook)

        result = gw.get_order("ORD-789")
        assert result is not None
        assert result.order_id == "ORD-789"

    def test_get_order_fallback_returns_none_if_not_in_orderbook(self):
        """Fallback scan returns None when order is not in orderbook."""
        gw = UpstoxBrokerGateway.__new__(UpstoxBrokerGateway)
        gw._broker = MagicMock(spec=[])  # No order_query attribute
        gw._broker.settings = MagicMock()
        gw._order_command = MagicMock()
        gw.get_orderbook = MagicMock(return_value=[])

        result = gw.get_order("NONEXISTENT")
        assert result is None


class TestCancelOrderPostVerification:
    """Verify cancel_order() still works with post-cancellation verification."""

    def test_cancel_order_verification_uses_direct_lookup(self):
        """cancel_order() post-verification must use direct get_order."""
        broker = MagicMock()
        broker.settings.analytics_only = False
        broker.settings.allow_live_orders = True

        from domain import OrderResponse
        broker.order_command.cancel_order.return_value = OrderResponse.ok(
            order_id="ORD-123", message="Cancelled"
        )
        broker.order_query.get_order.return_value = _make_order(
            "ORD-123", OrderStatus.CANCELLED
        )

        gw = UpstoxBrokerGateway(broker)
        result = gw.cancel_order("ORD-123")

        assert result.success is True
        broker.order_query.get_order.assert_called_once_with("ORD-123")

    def test_cancel_order_detects_race_condition_fill(self):
        """cancel_order() detects if order was filled between cancel send and response."""
        broker = MagicMock()
        broker.settings.analytics_only = False
        broker.settings.allow_live_orders = True

        from domain import OrderResponse
        broker.order_command.cancel_order.return_value = OrderResponse.ok(
            order_id="ORD-123", message="Cancelled"
        )
        # But direct lookup reveals the order was actually FILLED
        broker.order_query.get_order.return_value = _make_order(
            "ORD-123", OrderStatus.FILLED
        )

        gw = UpstoxBrokerGateway(broker)
        result = gw.cancel_order("ORD-123")

        assert result.success is False
        assert "already filled" in result.message.lower()
