"""OrderResponseFactory — single source of truth for OrderResponse construction.

All broker adapters must use this factory instead of constructing
``OrderResponse`` directly. This eliminates duplication and ensures
consistent error handling semantics across Dhan, Upstox, and Paper gateways.

Usage
-----
    from brokers.common.responses import OrderResponseFactory as R

    # Success
    return R.ok(order_id=order.order_id, message="Order placed", status=order.status)

    # Failure
    return R.fail(message=str(exc))

    # Already-executed post-cancel detection
    return R.already_executed(order_id="123")
"""

from __future__ import annotations

from typing import Any

from domain import OrderResponse, OrderStatus


class OrderResponseFactory:
    """Canonical factory for ``OrderResponse`` construction.

    Every broker gateway and adapter should import this factory and use
    its static methods rather than calling ``OrderResponse(...)`` or
    ``OrderResponse.ok()`` / ``OrderResponse.fail()`` directly.
    """

    @staticmethod
    def ok(
        order_id: str,
        message: str = "Order placed",
        status: OrderStatus | None = None,
    ) -> OrderResponse:
        """Build a successful order response.

        Parameters
        ----------
        order_id : str
            Broker-assigned order identifier.
        message : str
            Human-readable success message.
        status : OrderStatus, optional
            Normalised order status. Defaults to ``OPEN``.
        """
        return OrderResponse.ok(
            order_id=order_id,
            message=message,
            status=status,
        )

    @staticmethod
    def fail(
        message: str,
        error_code: str | None = None,
        status: OrderStatus | None = None,
        **extra: Any,
    ) -> OrderResponse:
        """Build a failed order response.

        Parameters
        ----------
        message : str
            Human-readable failure reason.
        error_code : str, optional
            Machine-readable error code (e.g. ``"UNMAPPED_STATUS"``,
            ``"ALREADY_EXECUTED"``).
        status : OrderStatus, optional
            Current order status if known.
        extra : dict
            Additional keyword arguments forwarded to ``OrderResponse.fail()``.
        """
        return OrderResponse.fail(
            message=message,
            error_code=error_code,
            status=status,
            **extra,
        )

    @staticmethod
    def already_executed(order_id: str) -> OrderResponse:
        """Post-cancellation verification: order was filled before cancel completed.

        This is a common pattern across both Dhan and Upstox gateways.
        """
        return OrderResponse.fail(
            message=f"Order {order_id} was already filled before cancel completed",
            status=OrderStatus.FILLED,
        )

    @staticmethod
    def analytics_blocked() -> OrderResponse:
        """Analytics-only mode: live orders blocked."""
        return OrderResponse.fail("Analytics-only mode: live orders are blocked.")

    @staticmethod
    def live_orders_disabled() -> OrderResponse:
        """Live orders disabled by configuration."""
        return OrderResponse.fail(
            "Live orders are disabled. Set allow_live_orders=True in configuration."
        )
