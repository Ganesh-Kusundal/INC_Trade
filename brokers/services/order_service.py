"""Order service — application-level order operations with validation.

Sits between the consumer and the broker adapter, adding validation,
idempotency, logging, and error translation. Depends on ports, not concretions.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from brokers.domain import Order, OrderResponse, Side
from brokers.domain.enums import OrderType, ProductType, Validity
from brokers.domain.exceptions import OrderRejectedError
from brokers.ports.order_execution import OrderExecutionPort
from brokers.services.order_validation import (
    check_notional_warning,
    validate_lot_size,
    validate_order_fields,
    validate_product_segment,
    validate_tick_alignment,
)

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(
        self,
        executor: OrderExecutionPort,
        idempotency_cache: Any = None,
        lot_size: int = 0,
        tick_size: Decimal = Decimal("0"),
    ):
        self._executor = executor
        self._idempotency = idempotency_cache
        self._lot_size = lot_size
        self._tick_size = tick_size

    def place_order(
        self,
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
        validate_order_fields(
            symbol, exchange, quantity, order_type, price, trigger_price
        )
        validate_product_segment(product_type, exchange)

        if self._lot_size > 0:
            validate_lot_size(quantity, self._lot_size)
        if self._tick_size > 0 and price > 0:
            validate_tick_alignment(price, self._tick_size)

        check_notional_warning(quantity, price)

        if self._idempotency and correlation_id:
            if not self._idempotency.check_and_set(correlation_id):
                return OrderResponse.already_executed(correlation_id)

        resp = self._executor.place_order(
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

        if resp.success:
            logger.info(
                "order_placed", extra={"order_id": resp.order_id, "symbol": symbol}
            )
        else:
            logger.warning(
                "order_rejected", extra={"symbol": symbol, "message": resp.message}
            )

        return resp

    def cancel_order(self, order_id: str) -> OrderResponse:
        if not order_id:
            raise OrderRejectedError("order_id is required")
        return self._executor.cancel_order(order_id)

    def get_order(self, order_id: str) -> Order | None:
        return self._executor.get_order(order_id)

    def get_orderbook(self) -> list[Order]:
        return self._executor.get_orderbook()
