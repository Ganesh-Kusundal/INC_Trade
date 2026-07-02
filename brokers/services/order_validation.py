"""Enhanced order validation — lot size, tick alignment, product×segment.

Extends the basic validation in OrderService with market microstructure
checks that prevent rejected orders at the exchange level.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.domain.enums import OrderType, ProductType
from brokers.domain.exceptions import OrderRejectedError
from brokers.utils.price import is_tick_aligned

logger = logging.getLogger(__name__)

_EQUITY_EXCHANGES = {"NSE", "BSE"}
_DERIVATIVE_EXCHANGES = {"NFO", "BFO", "MCX", "CDS", "BCD"}

_EQUITY_PRODUCTS = {ProductType.INTRADAY, ProductType.DELIVERY}

NOTIONAL_WARNING_THRESHOLD = Decimal("50000")


def validate_order_fields(
    symbol: str,
    exchange: str,
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


def validate_lot_size(quantity: int, lot_size: int) -> None:
    if lot_size <= 0:
        return
    if quantity % lot_size != 0:
        raise OrderRejectedError(
            f"quantity {quantity} is not a multiple of lot_size {lot_size}"
        )


def validate_tick_alignment(
    price: Decimal,
    tick_size: Decimal = Decimal("0.05"),
) -> None:
    if price <= Decimal("0"):
        return
    if not is_tick_aligned(price, tick_size):
        raise OrderRejectedError(
            f"price {price} is not aligned to tick size {tick_size}"
        )


def validate_product_segment(product_type: ProductType, exchange: str) -> None:
    if exchange in _DERIVATIVE_EXCHANGES and product_type in _EQUITY_PRODUCTS:
        if product_type == ProductType.DELIVERY:
            raise OrderRejectedError(
                f"DELIVERY product is not valid for derivative exchange {exchange}"
            )


def check_notional_warning(
    quantity: int,
    price: Decimal,
    threshold: Decimal = NOTIONAL_WARNING_THRESHOLD,
) -> None:
    if price <= Decimal("0"):
        return
    notional = Decimal(quantity) * price
    if notional > threshold:
        logger.warning(
            "High notional order: %.2f (threshold: %.2f)",
            notional,
            threshold,
        )
