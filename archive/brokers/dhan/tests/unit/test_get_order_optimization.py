"""Unit tests for Task 2.1: Dhan get_order() direct lookup optimization.

Verifies that get_order() uses the OrdersAdapter.get_order() direct endpoint
(GET /orders/{order_id}) instead of fetching the full orderbook.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.dhan.gateway import BrokerGateway
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

    def test_get_order_calls_adapter_get_order(self):
        """get_order() must call orders.get_order(order_id), NOT get_orderbook()."""
        conn = MagicMock()
        expected_order = _make_order("ORD-123")
        conn.orders.get_order.return_value = expected_order

        gw = BrokerGateway(conn)
        result = gw.get_order("ORD-123")

        conn.orders.get_order.assert_called_once_with("ORD-123")
        conn.orders.get_orderbook.assert_not_called()
        assert result is expected_order

    def test_get_order_returns_none_on_exception(self):
        """get_order() returns None when adapter raises (order not found)."""
        conn = MagicMock()
        conn.orders.get_order.side_effect = Exception("Order not found")

        gw = BrokerGateway(conn)
        result = gw.get_order("NONEXISTENT")

        assert result is None
        conn.orders.get_order.assert_called_once_with("NONEXISTENT")
        conn.orders.get_orderbook.assert_not_called()

    def test_get_order_logs_warning_when_lookup_fails(self, caplog):
        import logging

        conn = MagicMock()
        conn.orders.get_order.side_effect = RuntimeError("broker timeout")

        gw = BrokerGateway(conn)
        with caplog.at_level(logging.WARNING):
            result = gw.get_order("ORD-999")

        assert result is None
        assert any("get_order_failed" in r.message for r in caplog.records)

    def test_get_order_returns_order_on_success(self):
        """get_order() returns the Order from the adapter on success."""
        conn = MagicMock()
        filled_order = _make_order("ORD-456", OrderStatus.FILLED)
        conn.orders.get_order.return_value = filled_order

        gw = BrokerGateway(conn)
        result = gw.get_order("ORD-456")

        assert result is filled_order
        assert result.status == OrderStatus.FILLED
        assert result.order_id == "ORD-456"

    def test_get_order_does_not_fetch_orderbook(self):
        """Critical: get_order() must NOT call get_orderbook() — that's the whole point."""
        conn = MagicMock()
        conn.orders.get_order.return_value = _make_order()

        gw = BrokerGateway(conn)
        gw.get_order("ORD-123")

        # This is the key assertion — the optimization
        conn.orders.get_orderbook.assert_not_called()


class TestCancelOrderPostVerification:
    """Verify cancel_order() still works with post-cancellation verification."""

    def test_cancel_order_verification_uses_direct_lookup(self):
        """cancel_order() verification must use direct get_order, not orderbook scan."""
        conn = MagicMock()

        # Simulate successful cancel
        from domain import OrderResponse
        conn.orders.cancel_order.return_value = OrderResponse.ok(
            order_id="ORD-123", message="Cancelled", status=OrderStatus.CANCELLED
        )
        # Simulate direct lookup returning cancelled order
        conn.orders.get_order.return_value = _make_order("ORD-123", OrderStatus.CANCELLED)

        gw = BrokerGateway(conn)
        result = gw.cancel_order("ORD-123")

        assert result.success is True
        conn.orders.get_order.assert_called_once_with("ORD-123")
        conn.orders.get_orderbook.assert_not_called()

    def test_cancel_order_detects_race_condition_fill(self):
        """cancel_order() detects if order was filled between cancel send and response."""
        conn = MagicMock()

        from domain import OrderResponse
        conn.orders.cancel_order.return_value = OrderResponse.ok(
            order_id="ORD-123", message="Cancelled"
        )
        # But direct lookup reveals the order was actually FILLED
        conn.orders.get_order.return_value = _make_order("ORD-123", OrderStatus.FILLED)

        gw = BrokerGateway(conn)
        result = gw.cancel_order("ORD-123")

        assert result.success is False
        assert "already filled" in result.message.lower() or "ALREADY_EXECUTED" in str(result.error_code or "")

    def test_cancel_order_handles_get_order_failure_gracefully(self):
        """cancel_order() succeeds even if post-verification get_order fails."""
        conn = MagicMock()

        from domain import OrderResponse
        conn.orders.cancel_order.return_value = OrderResponse.ok(
            order_id="ORD-123", message="Cancelled"
        )
        # get_order raises (e.g., order already purged from system)
        conn.orders.get_order.side_effect = Exception("Not found")

        gw = BrokerGateway(conn)
        result = gw.cancel_order("ORD-123")

        # Should still return success since cancel itself succeeded
        assert result.success is True
