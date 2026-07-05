"""OrderManagementSystem — centralized order management with validation pipeline.

Lives in the Trading bounded context. Depends ONLY on:
- domain/ (validators, entities, events, order_lifecycle)
- ports/ (OrderExecutionPort)
- self (oms/)

NEVER imports: services/, infrastructure/, adapters/
"""

from __future__ import annotations

import logging
import threading
from decimal import Decimal
from typing import Any

from inc_trade.domain.entities import Order, OrderResponse
from inc_trade.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from inc_trade.domain.exceptions import OrderRejectedError
from inc_trade.oms.idempotency import IdempotencyCache
from inc_trade.oms.kill_switch import KillSwitch
from inc_trade.oms.router import ExecutionRouter

logger = logging.getLogger(__name__)


class OrderManagementSystem:
    """Centralized order management with validation, idempotency, and routing.

    Pipeline for place_order:
    1. Check kill switch
    2. Check idempotency (if correlation_id provided)
    3. Validate fields (domain validators)
    4. Route to correct broker via ExecutionRouter
    5. Execute via OrderExecutionPort
    6. Save to OrderRepository
    7. Publish OrderPlacedEvent
    8. Cache idempotency response
    """

    def __init__(
        self,
        execution_router: ExecutionRouter,
        order_repository: Any,
        event_publisher: Any | None = None,
        kill_switch: KillSwitch | None = None,
        idempotency_cache: IdempotencyCache | None = None,
    ) -> None:
        self._router = execution_router
        self._repo = order_repository
        self._events = event_publisher
        self._kill_switch = kill_switch or KillSwitch()
        self._idempotency = idempotency_cache or IdempotencyCache()

    def place_order(
        self,
        account_id: str,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str = "",
    ) -> OrderResponse:
        """Place an order with full validation pipeline.

        Args:
            account_id: Account identifier in ``{broker_id}/{account_name}`` format.
            symbol: Trading symbol.
            exchange: Exchange code.
            side: Order side (BUY/SELL).
            quantity: Order quantity.
            order_type: Order type (MARKET, LIMIT, SL, SL-M).
            price: Order price (0 for MARKET).
            product_type: Product type (INTRADAY, CNC, NRML).
            validity: Order validity (DAY, IOC).
            trigger_price: Trigger price for SL orders.
            correlation_id: Idempotency key for deduplication.

        Returns:
            OrderResponse from the broker adapter.

        Raises:
            OrderRejectedError: If kill switch is engaged.
            ValueError: If validation fails.
        """
        # Step 1: Kill switch
        if self._kill_switch.is_engaged:
            raise OrderRejectedError(
                "Kill switch is engaged. All orders blocked."
            )

        # Step 2: Idempotency
        if correlation_id:
            cached = self._idempotency.get(correlation_id)
            if cached is not None:
                return cached  # Duplicate request — return cached response

        # Step 3: Validate
        if not symbol:
            raise ValueError("symbol cannot be empty")
        if not exchange:
            raise ValueError("exchange cannot be empty")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if order_type in (OrderType.LIMIT, OrderType.SL) and price <= 0:
            raise ValueError(f"price required for {order_type.value} orders")
        if order_type in (OrderType.SL, OrderType.SL_M) and trigger_price <= 0:
            raise ValueError(f"trigger_price required for {order_type.value} orders")

        # Step 4: Route
        provider = self._router.route(account_id)

        # Step 5: Execute
        response = provider.place_order(
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

        # Step 6: Save to repository
        if response.success and response.order_id:
            order = Order(
                order_id=response.order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                status=response.status,
                price=price,
                order_type=order_type,
                product_type=product_type,
                validity=validity,
                trigger_price=trigger_price,
                correlation_id=correlation_id,
            )
            self._repo.save(order, account_id=account_id)

        # Step 7: Publish event
        if self._events and response.success:
            try:
                from inc_trade.domain.events import OrderPlacedEvent
                self._events.publish(OrderPlacedEvent(
                    account_id=account_id,
                    order_id=response.order_id,
                    correlation_id=correlation_id,
                    symbol=symbol,
                    exchange=exchange,
                    side=side.value,
                    quantity=quantity,
                    order_type=order_type.value,
                    price=price,
                ))
            except Exception as exc:
                logger.warning("Failed to publish order event: %s", exc)

        # Step 8: Cache idempotency
        if correlation_id and response.success:
            self._idempotency.put(correlation_id, response)

        return response

    def modify_order(
        self,
        account_id: str,
        order_id: str,
        **kwargs: Any,
    ) -> OrderResponse:
        """Modify an existing order with state validation.

        Args:
            account_id: Account identifier.
            order_id: Order ID to modify.
            **kwargs: Fields to modify (quantity, price, order_type, etc.).

        Returns:
            OrderResponse from the broker adapter.
        """
        if self._kill_switch.is_engaged:
            raise OrderRejectedError("Kill switch engaged")

        provider = self._router.route(account_id)
        response = provider.modify_order(order_id=order_id, **kwargs)

        if response.success:
            self._repo.update_status(order_id, response.status)

        return response

    def cancel_order(
        self,
        account_id: str,
        order_id: str,
    ) -> OrderResponse:
        """Cancel an existing order.

        Args:
            account_id: Account identifier.
            order_id: Order ID to cancel.

        Returns:
            OrderResponse from the broker adapter.
        """
        provider = self._router.route(account_id)
        response = provider.cancel_order(order_id)

        if response.success:
            self._repo.update_status(order_id, OrderStatus.CANCELLED)
            if self._events:
                try:
                    from inc_trade.domain.events import OrderCancelledEvent
                    self._events.publish(OrderCancelledEvent(
                        account_id=account_id,
                        order_id=order_id,
                    ))
                except Exception as exc:
                    logger.warning("Failed to publish cancel event: %s", exc)

        return response

    @property
    def kill_switch(self) -> KillSwitch:
        """Access the kill switch for emergency control."""
        return self._kill_switch

    @property
    def order_repository(self) -> Any:
        """Access the order repository."""
        return self._repo
