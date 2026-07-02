"""Tests for order validation rules."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.domain.enums import OrderType, ProductType
from brokers.domain.exceptions import OrderRejectedError
from brokers.services.order_validation import (
    check_notional_warning,
    validate_lot_size,
    validate_order_fields,
    validate_product_segment,
    validate_tick_alignment,
)


class TestValidateOrderFields:
    def test_empty_symbol_raises(self):
        with pytest.raises(OrderRejectedError, match="symbol"):
            validate_order_fields("", "NSE", 10, OrderType.MARKET, Decimal("0"), Decimal("0"))

    def test_empty_exchange_raises(self):
        with pytest.raises(OrderRejectedError, match="exchange"):
            validate_order_fields("RELIANCE", "", 10, OrderType.MARKET, Decimal("0"), Decimal("0"))

    def test_zero_quantity_raises(self):
        with pytest.raises(OrderRejectedError, match="quantity"):
            validate_order_fields("RELIANCE", "NSE", 0, OrderType.MARKET, Decimal("0"), Decimal("0"))

    def test_negative_quantity_raises(self):
        with pytest.raises(OrderRejectedError, match="quantity"):
            validate_order_fields("RELIANCE", "NSE", -5, OrderType.MARKET, Decimal("0"), Decimal("0"))

    def test_limit_order_zero_price_raises(self):
        with pytest.raises(OrderRejectedError, match="price"):
            validate_order_fields("RELIANCE", "NSE", 10, OrderType.LIMIT, Decimal("0"), Decimal("0"))

    def test_stop_order_zero_trigger_raises(self):
        with pytest.raises(OrderRejectedError, match="trigger_price"):
            validate_order_fields("RELIANCE", "NSE", 10, OrderType.STOP_LOSS, Decimal("100"), Decimal("0"))

    def test_valid_market_order(self):
        validate_order_fields("RELIANCE", "NSE", 10, OrderType.MARKET, Decimal("0"), Decimal("0"))

    def test_valid_limit_order(self):
        validate_order_fields("RELIANCE", "NSE", 10, OrderType.LIMIT, Decimal("2500"), Decimal("0"))


class TestValidateLotSize:
    def test_valid_multiple(self):
        validate_lot_size(100, 50)

    def test_exact_lot(self):
        validate_lot_size(50, 50)

    def test_invalid_multiple_raises(self):
        with pytest.raises(OrderRejectedError, match="lot_size"):
            validate_lot_size(75, 50)

    def test_zero_lot_size_skips(self):
        validate_lot_size(75, 0)


class TestValidateTickAlignment:
    def test_aligned_price(self):
        validate_tick_alignment(Decimal("100.05"), Decimal("0.05"))

    def test_misaligned_price_raises(self):
        with pytest.raises(OrderRejectedError, match="tick size"):
            validate_tick_alignment(Decimal("100.03"), Decimal("0.05"))

    def test_zero_price_skips(self):
        validate_tick_alignment(Decimal("0"), Decimal("0.05"))


class TestValidateProductSegment:
    def test_intraday_on_nse_ok(self):
        validate_product_segment(ProductType.INTRADAY, "NSE")

    def test_delivery_on_nse_ok(self):
        validate_product_segment(ProductType.DELIVERY, "NSE")

    def test_delivery_on_nfo_raises(self):
        with pytest.raises(OrderRejectedError, match="DELIVERY"):
            validate_product_segment(ProductType.DELIVERY, "NFO")


class TestCheckNotionalWarning:
    def test_below_threshold_no_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            check_notional_warning(10, Decimal("100"))
        assert "High notional" not in caplog.text

    def test_above_threshold_warns(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            check_notional_warning(100, Decimal("1000"))
        assert "High notional" in caplog.text
