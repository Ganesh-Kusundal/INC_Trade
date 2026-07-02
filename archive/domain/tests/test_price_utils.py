"""Tests for domain.utils.price — tick snapping, alignment, and wire conversion."""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.utils.price import is_tick_aligned, snap_to_tick, to_wire_float


class TestSnapToTick:
    def test_exact_multiple_unchanged(self):
        assert snap_to_tick(Decimal("100.05"), Decimal("0.05")) == Decimal("100.05")

    def test_snaps_up(self):
        assert snap_to_tick(Decimal("100.13"), Decimal("0.05")) == Decimal("100.15")

    def test_snaps_down(self):
        assert snap_to_tick(Decimal("100.12"), Decimal("0.05")) == Decimal("100.10")

    def test_half_rounds_up(self):
        assert snap_to_tick(Decimal("100.125"), Decimal("0.05")) == Decimal("100.15")

    def test_zero_price(self):
        assert snap_to_tick(Decimal("0"), Decimal("0.05")) == Decimal("0")

    def test_large_price(self):
        result = snap_to_tick(Decimal("999999.99"), Decimal("0.05"))
        assert result == Decimal("1000000.00")

    def test_sub_penny_tick(self):
        result = snap_to_tick(Decimal("1.003"), Decimal("0.001"))
        assert result == Decimal("1.003")

    def test_tick_size_one(self):
        assert snap_to_tick(Decimal("100.7"), Decimal("1")) == Decimal("101")

    def test_zero_tick_size_raises(self):
        with pytest.raises(ValueError, match="tick_size must be positive"):
            snap_to_tick(Decimal("100"), Decimal("0"))

    def test_negative_tick_size_raises(self):
        with pytest.raises(ValueError, match="tick_size must be positive"):
            snap_to_tick(Decimal("100"), Decimal("-0.05"))

    def test_negative_price_raises(self):
        with pytest.raises(ValueError, match="price must be non-negative"):
            snap_to_tick(Decimal("-1"), Decimal("0.05"))

    def test_mcx_tick_size(self):
        assert snap_to_tick(Decimal("72340"), Decimal("10")) == Decimal("72340")
        assert snap_to_tick(Decimal("72345"), Decimal("10")) == Decimal("72350")


class TestIsTickAligned:
    def test_aligned(self):
        assert is_tick_aligned(Decimal("100.05"), Decimal("0.05")) is True

    def test_not_aligned(self):
        assert is_tick_aligned(Decimal("100.07"), Decimal("0.05")) is False

    def test_zero_is_aligned(self):
        assert is_tick_aligned(Decimal("0"), Decimal("0.05")) is True

    def test_tolerance_absorbs_residue(self):
        assert is_tick_aligned(Decimal("100.0500000001"), Decimal("0.05")) is True

    def test_custom_tolerance(self):
        assert is_tick_aligned(
            Decimal("100.03"), Decimal("0.05"), tolerance=Decimal("0.05")
        ) is True

    def test_zero_tick_size_raises(self):
        with pytest.raises(ValueError, match="tick_size must be positive"):
            is_tick_aligned(Decimal("100"), Decimal("0"))

    def test_negative_price_raises(self):
        with pytest.raises(ValueError, match="price must be non-negative"):
            is_tick_aligned(Decimal("-1"), Decimal("0.05"))


class TestToWireFloat:
    def test_basic_conversion(self):
        assert to_wire_float(Decimal("1234.56")) == 1234.56

    def test_truncates_to_max_decimals(self):
        assert to_wire_float(Decimal("1234.56789"), max_decimals=2) == 1234.57

    def test_default_four_decimals(self):
        result = to_wire_float(Decimal("100.12345678"))
        assert result == 100.1235

    def test_zero_decimals(self):
        assert to_wire_float(Decimal("100.5"), max_decimals=0) == 101.0

    def test_preserves_precision(self):
        result = to_wire_float(Decimal("0.0001"))
        assert result == 0.0001

    def test_negative_max_decimals_raises(self):
        with pytest.raises(ValueError, match="max_decimals must be >= 0"):
            to_wire_float(Decimal("100"), max_decimals=-1)

    def test_large_price(self):
        result = to_wire_float(Decimal("999999.99"))
        assert result == 999999.99

    def test_rounds_half_up(self):
        assert to_wire_float(Decimal("1.005"), max_decimals=2) == 1.01
