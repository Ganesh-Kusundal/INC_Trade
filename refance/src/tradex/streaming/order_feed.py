"""Order update feed — live order status monitoring."""

from __future__ import annotations

from typing import Any, Callable, Coroutine, Optional

from tradex.core.events import EventBus
from tradex.core.logging_config import get_logger
from tradex.domain.enums import OrderStatus
from tradex.domain.events import (
    OrderFilled,
    OrderPlaced,
    OrderRejected,
    OrderStatusChanged,
)

logger = get_logger("streaming.order_feed")

OrderUpdateHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class OrderFeed:
    """Live order update feed.

    Connects to the broker's order update WebSocket
    and publishes order events.
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._event_bus = event_bus
        self._handlers: list[OrderUpdateHandler] = []
        self._order_cache: dict[str, dict[str, Any]] = {}

    def on_update(self, handler: OrderUpdateHandler) -> None:
        """Register an order update handler."""
        self._handlers.append(handler)

    async def process_update(self, data: dict[str, Any]) -> None:
        """Process an incoming order update."""
        # Dispatch to handlers
        for handler in self._handlers:
            try:
                await handler(data)
            except Exception as e:
                logger.error("order_handler_error", error=str(e))

        # Parse and publish domain events
        if self._event_bus:
            events = self._parse_order_update(data)
            for event in events:
                await self._event_bus.publish(event)

        # Update cache
        order_id = str(data.get("orderId", ""))
        if order_id:
            self._order_cache[order_id] = data

    def _parse_order_update(self, data: dict[str, Any]) -> list[Any]:
        """Parse raw order update into domain events."""
        events = []
        order_id = str(data.get("orderId", ""))
        status_str = data.get("orderStatus", "")
        correlation_id = data.get("correlationID", "")

        status_map = {
            "PENDING": OrderStatus.PENDING,
            "PLACED": OrderStatus.PLACED,
            "ACCEPTED": OrderStatus.ACCEPTED,
            "OPEN": OrderStatus.OPEN,
            "PART_TRADED": OrderStatus.PART_TRADED,
            "TRADED": OrderStatus.TRADED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED,
            "TRIGGER_PENDING": OrderStatus.TRIGGER_PENDING,
        }

        new_status = status_map.get(status_str, OrderStatus.UNKNOWN)

        if new_status == OrderStatus.PLACED:
            events.append(
                OrderPlaced(
                    order_id=order_id,
                    correlation_id=correlation_id,
                    security_id=str(data.get("securityId", "")),
                )
            )
        elif new_status == OrderStatus.REJECTED:
            events.append(
                OrderRejected(
                    order_id=order_id,
                    correlation_id=correlation_id,
                    reason=data.get("rejectionReason", ""),
                )
            )
        elif new_status in (OrderStatus.TRADED,):
            events.append(
                OrderFilled(
                    order_id=order_id,
                    correlation_id=correlation_id,
                    filled_quantity=int(data.get("filledQty", 0)),
                    average_price=float(data.get("averagePrice", 0)),
                )
            )

        # Always emit status change
        events.append(
            OrderStatusChanged(
                order_id=order_id,
                correlation_id=correlation_id,
                new_status=new_status,
                filled_quantity=int(data.get("filledQty", 0)),
                pending_quantity=int(data.get("pendingQty", 0)),
            )
        )

        return events

    @property
    def cached_orders(self) -> dict[str, dict[str, Any]]:
        return dict(self._order_cache)
