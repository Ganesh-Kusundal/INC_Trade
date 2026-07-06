"""Order service — domain layer for order management.

This service provides business logic for order placement, validation,
and lifecycle management. It depends on the OrderExecutionPort abstraction,
not on any specific broker implementation.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from inc_trade.domain import Order, OrderRequest, OrderResponse
from inc_trade.domain.enums import OrderType, ProductType, Side, Validity
from inc_trade.ports.order_execution import OrderExecutionPort
from inc_trade.ports.order_guard import OrderGuardPort
from inc_trade.services.order_guard import order_guard_from_flag

logger = logging.getLogger(__name__)


class OrderService:
    """Domain service for order management.

    Encapsulates business rules for order placement, validation, and risk checks.
    Clients depend on this service instead of calling broker gateways directly.
    """

    def __init__(
        self,
        order_port: OrderExecutionPort,
        idempotency_cache: Any | None = None,
        allow_live_orders: bool = True,
        order_guard: OrderGuardPort | None = None,
    ):
        """Initialize with an order execution port.

        Args:
            order_port: Broker-agnostic order execution interface
            idempotency_cache: Optional cache for idempotency (backward compat)
            allow_live_orders: Enable live order placement (backward compat)
            order_guard: Optional guard override; defaults to allow_live_orders flag
        """
        self._order_port = order_port
        self._idempotency_cache = idempotency_cache
        self._order_guard = order_guard or order_guard_from_flag(allow_live_orders)

    def place_order(
        self,
        symbol: str = "",
        exchange: str = "",
        side: Side = Side.BUY,
        quantity: int = 0,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str = "",
        request: OrderRequest | None = None,
    ) -> OrderResponse:
        """Place an order with business validation.

        Args:
            symbol: Instrument symbol
            exchange: Exchange code
            side: BUY or SELL
            quantity: Number of shares/contracts
            order_type: MARKET, LIMIT, etc.
            price: Limit price (for LIMIT orders)
            product_type: INTRADAY, DELIVERY, etc.
            validity: DAY, IOC, etc.
            trigger_price: Stop-loss trigger price
            correlation_id: Unique ID for idempotency

            correlation_id: Unique ID for idempotency
            request: Optional OrderRequest DTO encapsulating the order details

        Returns:
            OrderResponse with success status and order details
        """
        if request is not None:
            symbol = request.symbol
            exchange = request.exchange
            side = request.side
            quantity = request.quantity
            order_type = request.order_type
            product_type = request.product_type
            validity = request.validity
            correlation_id = request.correlation_id
            price = getattr(request, "price", Decimal("0"))
            trigger_price = getattr(request, "trigger_price", Decimal("0"))

        # Business validation
        if not symbol or not symbol.strip():
            from inc_trade.domain.exceptions import ValidationError

            raise ValidationError("symbol is required")

        if not exchange or not exchange.strip():
            from inc_trade.domain.exceptions import ValidationError

            raise ValidationError("exchange is required")

        if quantity <= 0:
            from inc_trade.domain.exceptions import ValidationError

            raise ValidationError("quantity must be positive")

        if order_type == OrderType.STOP_LOSS and trigger_price <= 0:
            from inc_trade.domain.exceptions import ValidationError

            raise ValidationError("trigger_price must be positive for STOP_LOSS orders")

        if order_type in (OrderType.LIMIT, OrderType.STOP_LOSS) and price <= 0:
            from inc_trade.domain.exceptions import ValidationError

            raise ValidationError("price must be positive for LIMIT/STOP_LOSS orders")

        blocked = self._order_guard.check_live_order_allowed()
        if blocked is not None:
            return blocked

        # Delegate to broker-specific implementation
        return self._order_port.place_order(
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

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an existing order.

        Args:
            order_id: Order identifier to cancel

        Returns:
            OrderResponse with cancellation status
        """
        if not order_id:
            from inc_trade.domain.exceptions import OrderRejectedError

            raise OrderRejectedError("order_id is required")

        blocked = self._order_guard.check_live_order_allowed()
        if blocked is not None:
            return blocked

        return self._order_port.cancel_order(order_id)

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> OrderResponse:
        """Modify an existing order.

        Args:
            order_id: Order identifier to modify
            quantity: New quantity (optional)
            price: New price (optional)
            order_type: New order type (optional)
            validity: New validity (optional)

        Returns:
            OrderResponse with modification status
        """
        if not order_id:
            return OrderResponse.fail("Order ID is required", error_code="VALIDATION_FAILED")

        blocked = self._order_guard.check_live_order_allowed()
        if blocked is not None:
            return blocked

        return self._order_port.modify_order(
            order_id=order_id,
            quantity=quantity,
            price=price,
            order_type=order_type,
            validity=validity,
        )

    def get_order(self, order_id: str) -> Order | None:
        """Fetch order details by ID.

        Args:
            order_id: Order identifier

        Returns:
            Order object if found, None otherwise
        """
        return self._order_port.get_order(order_id)

    def get_orderbook(self) -> list[Order]:
        """Fetch all open orders.

        Returns:
            List of open orders
        """
        return self._order_port.get_orderbook()
