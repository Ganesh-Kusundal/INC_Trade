"""Unified order validation service — consolidates scattered validation paths.

Replaces the 3 duplicated validation paths:
1. ``domain/validators/order_validator.py`` — pure field-level checks
2. ``DhanPlaceOrderUseCase.validate()`` — field + broker-specific checks
3. ``UpstoxPlaceOrderUseCase.validate()`` — field + broker-specific checks (copy)

The service follows a 2-phase validation pattern:
1. **Field-level** — validates order fields (symbol, quantity, price, etc.)
   Delegates to the existing ``validate_order()`` from domain validators.
2. **Instrument-aware** — validates against the resolved instrument
   (lot_size, tick_size, product/segment matrix). This is where the
   duplication lived.

Usage::

    validator = OrderValidationService(
        derivative_segments=frozenset({"NFO", "BFO", "MCX"}),
        equity_only_products=frozenset({"DELIVERY"}),
    )

    error = validator.validate(
        symbol="RELIANCE",
        exchange="NSE",
        quantity=10,
        order_type=OrderType.MARKET,
        price=Decimal("2500"),
        trigger_price=Decimal("0"),
        lot_size=1,
        tick_size=Decimal("0.05"),
        product_type=ProductType.INTRADAY,
    )
    if error:
        print(f"Order rejected: {error}")
"""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers_core.domain.enums import OrderType, ProductType
from brokers_core.domain.exceptions import ValidationError
from brokers_core.domain.validators.order_validator import validate_order
from brokers_core.utils.price import is_tick_aligned

logger = logging.getLogger(__name__)


class OrderValidationService:
    """Unified order validation — field-level + instrument-aware + broker-specific.

    Consolidates the 3 scattered validation paths into a single service.
    The service is configurable with broker-specific constants so that
    different adapters (Dhan, Upstox) can share the same validation logic.

    Args:
        derivative_segments: Set of segment codes considered derivatives
            (e.g., ``{"NFO", "BFO", "MCX"}``). Used for lot-size and
            product-type enforcement.
        equity_only_products: Set of ProductType values that are only
            valid on equity exchanges (e.g., ``{"DELIVERY"}``).
    """

    def __init__(
        self,
        derivative_segments: frozenset[str] | None = None,
        equity_only_products: frozenset[str] | None = None,
    ) -> None:
        self._derivative_segments = derivative_segments or frozenset()
        self._equity_only_products = equity_only_products or frozenset()

    def validate(
        self,
        *,
        symbol: str,
        exchange: str,
        quantity: int,
        order_type: OrderType,
        price: Decimal,
        trigger_price: Decimal,
        product_type: ProductType = ProductType.INTRADAY,
        lot_size: int = 1,
        tick_size: Decimal = Decimal("0.05"),
        segment: str = "",
    ) -> str | None:
        """Run all validation checks and return an error string, or None.

        Performs 2-phase validation:

        1. **Field-level** — delegates to ``validate_order()`` from domain
           validators. Checks symbol, exchange, quantity, price, trigger_price.
        2. **Instrument-aware** — checks lot_size alignment, tick_size
           alignment, and product/segment matrix.

        Args:
            symbol: Trading symbol.
            exchange: Exchange code.
            quantity: Order quantity.
            order_type: Order type enum.
            price: Order price.
            trigger_price: Trigger price for stop orders.
            product_type: Product type (default: INTRADAY).
            lot_size: Instrument lot size (default: 1).
            tick_size: Instrument tick size (default: 0.05).
            segment: Market segment for the instrument.

        Returns:
            Error string if validation fails, ``None`` if valid.
        """
        # Phase 1: Field-level validation (raises ValidationError)
        try:
            validate_order(
                symbol=symbol,
                exchange=exchange,
                quantity=quantity,
                order_type=order_type,
                price=price,
                trigger_price=trigger_price,
            )
        except ValidationError as exc:
            return self._translate_field_error(exc, order_type)

        # Phase 2: Instrument-aware validation
        return self._validate_instrument_rules(
            symbol=symbol,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            lot_size=lot_size,
            tick_size=tick_size,
            segment=segment,
        )

    # ── Private Helpers ───────────────────────────────────────────────

    def _validate_instrument_rules(
        self,
        *,
        symbol: str,
        quantity: int,
        price: Decimal,
        order_type: OrderType,
        product_type: ProductType,
        lot_size: int,
        tick_size: Decimal,
        segment: str,
    ) -> str | None:
        """Check instrument-aware and broker-specific rules.

        Returns:
            Error string if a rule is violated, ``None`` if valid.
        """
        # Lot-size enforcement (derivatives only)
        if (
            segment in self._derivative_segments
            and lot_size > 1
            and quantity % lot_size != 0
        ):
            return (
                f"Quantity {quantity} is not a multiple of lot size "
                f"{lot_size} for {symbol}"
            )

        # Product/segment matrix (DELIVERY on derivatives)
        if segment in self._derivative_segments and product_type == ProductType.DELIVERY:
            return (
                f"Product type DELIVERY is not valid for {segment}. "
                "Use INTRADAY or MARGIN for derivatives."
            )

        # Equity-only products on derivative segments
        pt_val = product_type.value
        if segment in self._derivative_segments and pt_val in self._equity_only_products:
            return (
                f"Product type {pt_val} is not valid for {segment}. "
                "Use INTRADAY or MARGIN for derivatives."
            )

        # Tick-size alignment
        if price > 0 and tick_size > 0:
            if not is_tick_aligned(price, tick_size):
                return (
                    f"Price {price} is not aligned to tick size "
                    f"{tick_size} for {symbol}"
                )

        return None

    @staticmethod
    def _translate_field_error(exc: ValidationError, order_type: OrderType) -> str:
        """Map a domain ValidationError onto a stable error string.

        The substrings are part of the adapter's public contract and are
        surfaced in ``OrderResponse.message``.
        """
        text = str(exc)
        lower = text.lower()

        if order_type is OrderType.LIMIT and "price" in lower:
            return "Limit order requires price > 0"
        if order_type is OrderType.STOP_LOSS and ("price" in lower or "trigger" in lower):
            return "Stop-Loss (Limit) order requires price > 0 and trigger_price > 0"
        if order_type is OrderType.STOP_LOSS_MARKET and "trigger" in lower:
            return "Stop-Loss Market order requires trigger_price > 0"
        return text
