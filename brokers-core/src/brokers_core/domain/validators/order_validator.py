"""Order validation rules — lot size, tick alignment, product×segment, notional.

All validators are pure functions that raise domain exceptions.
They have no dependencies beyond Python stdlib and the domain layer.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers_core.domain.constants.exchanges import DERIVATIVE_EXCHANGES
from brokers_core.domain.enums import OrderType, ProductType

_EQUITY_PRODUCTS = {ProductType.INTRADAY, ProductType.DELIVERY}

NOTIONAL_WARNING_THRESHOLD = Decimal("50000")


def validate_symbol(symbol: str) -> None:
    """Validate symbol is non-empty."""
    from brokers_core.domain.exceptions import ValidationError

    if not symbol or not symbol.strip():
        raise ValidationError("symbol is required")


def validate_exchange(exchange: str) -> None:
    """Validate exchange is non-empty."""
    from brokers_core.domain.exceptions import ValidationError

    if not exchange or not exchange.strip():
        raise ValidationError("exchange is required")


def validate_quantity(quantity: int) -> None:
    """Validate quantity is positive."""
    from brokers_core.domain.exceptions import ValidationError

    if quantity <= 0:
        raise ValidationError(f"quantity must be positive, got {quantity}")


def validate_price(price: Decimal) -> None:
    """Validate price is non-negative."""
    from brokers_core.domain.exceptions import ValidationError

    if price < 0:
        raise ValidationError("Price cannot be negative")


def validate_limit_price(price: Decimal) -> None:
    """Validate LIMIT order has a positive price."""
    from brokers_core.domain.exceptions import ValidationError

    if price == 0:
        raise ValidationError(f"LIMIT orders require a positive price (got {price})")


def validate_trigger_price(trigger_price: Decimal, order_type: OrderType) -> None:
    """Validate trigger price for stop orders."""
    from brokers_core.domain.exceptions import ValidationError

    if trigger_price < 0:
        raise ValidationError("Trigger price cannot be negative")
    if trigger_price == 0 and order_type.is_stop:
        raise ValidationError("trigger_price must be positive for stop orders")
    if trigger_price > 0 and order_type not in (
        OrderType.STOP_LOSS,
        OrderType.STOP_LOSS_MARKET,
    ):
        raise ValidationError("Trigger price only valid for SL/SL-M orders")


def validate_lot_size(quantity: int, lot_size: int) -> None:
    """Validate quantity is a multiple of lot size."""
    from brokers_core.domain.exceptions import OrderRejectedError

    if lot_size <= 0:
        return
    if quantity % lot_size != 0:
        raise OrderRejectedError(f"quantity {quantity} is not a multiple of lot_size {lot_size}")


def validate_tick_alignment(
    price: Decimal,
    tick_size: Decimal = Decimal("0.05"),
) -> None:
    """Validate price is aligned to tick size.

    Uses inline tick-check logic to avoid depending on brokers.utils.
    """
    from brokers_core.domain.exceptions import OrderRejectedError

    if price <= Decimal("0"):
        return
    tolerance = Decimal("0.0001")
    remainder = price % tick_size
    aligned = remainder <= tolerance or (tick_size - remainder) <= tolerance
    if not aligned:
        raise OrderRejectedError(f"price {price} is not aligned to tick size {tick_size}")


def validate_product_segment(product_type: ProductType, exchange: str) -> None:
    """Validate product type is compatible with exchange."""
    from brokers_core.domain.exceptions import OrderRejectedError

    if exchange in DERIVATIVE_EXCHANGES and product_type in _EQUITY_PRODUCTS:
        if product_type == ProductType.DELIVERY:
            raise OrderRejectedError(
                f"DELIVERY product is not valid for derivative exchange {exchange}"
            )


def check_notional_warning(
    quantity: int,
    price: Decimal,
    threshold: Decimal = NOTIONAL_WARNING_THRESHOLD,
) -> bool:
    """Check if notional value exceeds threshold. Returns True if warning logged."""
    if price <= Decimal("0"):
        return False
    notional = Decimal(quantity) * price
    if notional > threshold:
        logging.getLogger(__name__).warning(
            "High notional order: %.2f (threshold: %.2f)",
            notional,
            threshold,
        )
        return True
    return False


def validate_order(
    symbol: str,
    exchange: str,
    quantity: int,
    order_type: OrderType,
    price: Decimal,
    trigger_price: Decimal,
) -> None:
    """Run all basic order field validations."""
    validate_symbol(symbol)
    validate_exchange(exchange)
    validate_quantity(quantity)
    validate_price(price)
    if order_type is OrderType.LIMIT:
        validate_limit_price(price)
    validate_trigger_price(trigger_price, order_type)
