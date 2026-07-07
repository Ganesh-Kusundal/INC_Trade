"""Order — entity with lifecycle.

The Order entity owns its status transitions and publishes events on
every state change.  This is a rich domain object, not an anemic data bag.

Lifecycle::

    PENDING → OPEN → PARTIALLY_FILLED → FILLED
         │        ↓              ↓           ↑
         │   CANCELLED      CANCELLED       │
         │        ↓              ↓           │
         │      REJECTED      REJECTED       │
         ↓                                   │
    PENDING ──────────────────────────────────→ FILLED
         │
         └→ REJECTED | CANCELLED

    OPEN → EXPIRED
    PARTIALLY_FILLED → EXPIRED
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from brokers.domain.enums import Exchange, OrderStatus, OrderType, ProductType, Side, Validity
from brokers.domain.events import DomainEvent, EventBusProtocol
from brokers.domain.requests import OrderRequest
from brokers.domain.values import OrderResponse



# Valid state transitions (from → {allowed next states})
_VALID_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({
        OrderStatus.OPEN,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    }),
    OrderStatus.OPEN: frozenset({
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    }),
    OrderStatus.PARTIALLY_FILLED: frozenset({
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    }),
    # Terminal states
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
    OrderStatus.UNKNOWN: frozenset({
        OrderStatus.OPEN,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    }),
}

# Map status → event type string for event publication
_STATUS_TO_EVENT: dict[OrderStatus, str] = {
    OrderStatus.OPEN: "ORDER_PLACED",
    OrderStatus.PARTIALLY_FILLED: "ORDER_UPDATED",
    OrderStatus.FILLED: "ORDER_UPDATED",
    OrderStatus.CANCELLED: "ORDER_CANCELLED",
    OrderStatus.REJECTED: "ORDER_REJECTED",
}


class InvalidOrderTransitionError(Exception):
    """Raised when an invalid status transition is attempted."""

    def __init__(self, from_status: OrderStatus, to_status: OrderStatus) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Invalid order transition: {from_status.value} → {to_status.value}"
        )


class Order:
    """Order entity — owns its lifecycle.

    Not frozen — ``_status`` and ``_filled_quantity`` are mutable.
    Thread-safe via a lock.  All transitions are validated against
    the state machine.

    Publishes events on every state transition via the optional EventBus.
    """

    __slots__ = (
        "_average_price",
        "_filled_quantity",
        "_lock",
        "_order_id",
        "_request",
        "_response",
        "_status",
        "_timestamp",
    )

    def __init__(self, request: OrderRequest, response: OrderResponse) -> None:
        self._request = request
        self._response = response
        self._order_id = response.order_id
        self._status = response.status
        self._filled_quantity = 0
        self._average_price: Decimal = Decimal("0")
        self._timestamp = datetime.now(timezone.utc)
        self._lock = threading.RLock()

    # ── Identity ─────────────────────────────────────────────────────

    @property
    def order_id(self) -> str:
        return self._order_id

    @property
    def symbol(self) -> str:
        return self._request.symbol

    @property
    def exchange(self) -> Exchange:
        return self._request.exchange

    @property
    def side(self) -> Side:
        return self._request.side

    @property
    def quantity(self) -> int:
        return self._request.quantity

    @property
    def order_type(self) -> OrderType:
        return self._request.order_type

    @property
    def product_type(self) -> ProductType:
        return self._request.product_type

    @property
    def price(self) -> Decimal:
        return self._request.price

    @property
    def request(self) -> OrderRequest:
        return self._request

    @property
    def response(self) -> OrderResponse:
        return self._response

    # ── State ────────────────────────────────────────────────────────

    @property
    def status(self) -> OrderStatus:
        with self._lock:
            return self._status

    @property
    def filled_quantity(self) -> int:
        with self._lock:
            return self._filled_quantity

    @property
    def average_price(self) -> Decimal:
        with self._lock:
            return self._average_price

    @property
    def remaining_quantity(self) -> int:
        with self._lock:
            return self._request.quantity - self._filled_quantity

    @property
    def is_terminal(self) -> bool:
        """True if the order is in a terminal state (no further transitions)."""
        with self._lock:
            return self._status in (
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
                OrderStatus.EXPIRED,
            )

    @property
    def is_filled(self) -> bool:
        with self._lock:
            return self._status == OrderStatus.FILLED

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._status in (OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)

    # ── Lifecycle ────────────────────────────────────────────────────

    def update_status(
        self,
        new_status: OrderStatus,
        *,
        filled_quantity: int | None = None,
        average_price: Decimal | None = None,
        event_bus: EventBusProtocol,
        correlation_id: str | None = None,
    ) -> None:
        """Transition to a new status and publish an event.

        Validates the transition against the state machine.  If invalid,
        raises :class:`InvalidOrderTransitionError`.  Always publishes
        a DomainEvent for the transition.
        """
        with self._lock:
            old_status = self._status

            # Validate transition
            allowed = _VALID_TRANSITIONS.get(old_status, frozenset())
            if new_status not in allowed and new_status != old_status:
                raise InvalidOrderTransitionError(old_status, new_status)

            self._status = new_status
            if filled_quantity is not None:
                self._filled_quantity = filled_quantity
            if average_price is not None:
                self._average_price = average_price

            # Publish event for the transition
            event_type = _STATUS_TO_EVENT.get(new_status)
            if event_type is not None:
                event_bus.publish(
                    DomainEvent.now(
                        event_type=event_type,
                        payload={
                            "order": self,
                            "order_id": self._order_id,
                            "symbol": self._request.symbol,
                            "status": new_status.value,
                            "old_status": old_status.value,
                            "filled_quantity": self._filled_quantity,
                            "average_price": str(self._average_price),
                        },
                        symbol=self._request.symbol,
                        correlation_id=correlation_id,
                    )
                )

    # ── Convenience factory ──────────────────────────────────────────

    @classmethod
    def from_response(
        cls,
        request: OrderRequest,
        response: OrderResponse,
    ) -> Order:
        """Create an Order from an OrderRequest and OrderResponse."""
        return cls(request, response)

    @classmethod
    def from_broker_data(
        cls,
        *,
        order_id: str,
        symbol: str,
        exchange: Exchange,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal | None = None,
        status: OrderStatus = OrderStatus.OPEN,
        filled_quantity: int = 0,
        average_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> Order:
        """Reconstruct an Order from broker order-book response data.

        Used by mappers when converting broker JSON responses back into
        Order entities.  Uses ``_reconstruct`` to set initial state
        without going through the state-machine transition validation.
        """
        request = OrderRequest(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
            price=price,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )
        response = OrderResponse(
            success=status not in (OrderStatus.REJECTED, OrderStatus.EXPIRED),
            order_id=order_id,
            status=status,
        )

        # Reconcile inconsistent state
        actual_status = status
        if status == OrderStatus.FILLED and filled_quantity != quantity:
            pass  # Broker edge case: partial fills reported as FILLED
        elif status in (OrderStatus.OPEN, OrderStatus.PENDING) and filled_quantity != 0:
            actual_status = OrderStatus.PARTIALLY_FILLED

        return cls._reconstruct(
            request=request,
            response=response,
            status=actual_status,
            filled_quantity=filled_quantity,
            average_price=average_price,
            timestamp=timestamp,
        )

    @classmethod
    def _reconstruct(
        cls,
        *,
        request: OrderRequest,
        response: OrderResponse,
        status: OrderStatus,
        filled_quantity: int,
        average_price: Decimal,
        timestamp: datetime | None,
    ) -> Order:
        """Internal reconstruction path — bypasses state-machine validation.

        Only used by ``from_broker_data`` to rebuild Order entities from
        broker responses where the state is already known.
        """
        order = object.__new__(cls)
        order._request = request
        order._response = response
        order._order_id = response.order_id
        order._status = status
        order._filled_quantity = filled_quantity
        order._average_price = average_price
        order._timestamp = timestamp or datetime.now(timezone.utc)
        order._lock = threading.RLock()
        return order

    def __repr__(self) -> str:
        return f"Order({self._order_id}, {self._request.symbol}, {self._status.value})"


__all__ = [
    "InvalidOrderTransitionError",
    "Order",
]
