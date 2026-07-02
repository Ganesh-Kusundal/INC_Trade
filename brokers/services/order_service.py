"""Order service — application-level order operations with validation.

Sits between the consumer and the broker adapter, adding validation,
logging, and error translation. Depends on ports, not concretions.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.domain import Order, OrderResponse, Side
from brokers.domain.enums import OrderType, ProductType, Validity
from brokers.domain.exceptions import OrderRejectedError
from brokers.ports.order_execution import OrderExecutionPort

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, executor: OrderExecutionPort):
        self._executor = executor

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
    ) -> OrderResponse:
        self._validate(
            symbol, exchange, side, quantity, order_type, price, trigger_price
        )

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

    @staticmethod
    def _validate(
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType,
        price: Decimal,
        trigger_price: Decimal,
    ) -> None:
        if not symbol:
            raise OrderRejectedError("symbol is required")
        if not exchange:
            raise OrderRejectedError("exchange is required")
        if quantity <= 0:
            raise OrderRejectedError(f"quantity must be positive, got {quantity}")
        if order_type == OrderType.LIMIT and price <= Decimal("0"):
            raise OrderRejectedError("LIMIT orders require a positive price")
        if order_type.is_stop and trigger_price <= Decimal("0"):
            raise OrderRejectedError("STOP orders require a positive trigger_price")
