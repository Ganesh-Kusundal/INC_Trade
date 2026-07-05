"""Enhanced order validation — lot size, tick alignment, product×segment.

Extends the basic validation in OrderService with market microstructure
checks that prevent rejected orders at the exchange level.

All validators now delegate to brokers.domain.validators.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from inc_trade.domain.enums import OrderType, ProductType
from inc_trade.domain.exceptions import OrderRejectedError

logger = logging.getLogger(__name__)

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
    """Validate order fields using domain validators."""
    from inc_trade.domain.validators.order_validator import validate_order as _domain_validate

    _domain_validate(
        symbol=symbol,
        exchange=exchange,
        quantity=quantity,
        order_type=order_type,
        price=price,
        trigger_price=trigger_price,
    )


def validate_lot_size(quantity: int, lot_size: int) -> None:
    from inc_trade.domain.validators.order_validator import validate_lot_size as _v

    _v(quantity, lot_size)


def validate_tick_alignment(
    price: Decimal,
    tick_size: Decimal = Decimal("0.05"),
) -> None:
    from inc_trade.domain.validators.order_validator import validate_tick_alignment as _v

    _v(price, tick_size)


def validate_product_segment(product_type: ProductType, exchange: str) -> None:
    from inc_trade.domain.validators.order_validator import validate_product_segment as _v

    _v(product_type, exchange)


def check_notional_warning(
    quantity: int,
    price: Decimal,
    threshold: Decimal = NOTIONAL_WARNING_THRESHOLD,
) -> None:
    from inc_trade.domain.validators.order_validator import check_notional_warning as _c

    _c(quantity, price, threshold)
