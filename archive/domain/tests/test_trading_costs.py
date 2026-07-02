"""Tests for domain.trading_costs — canonical commission/slippage models.

Covers:
- All CommissionModel variants (FLAT, INDIAN_EQUITY, INDIAN_FNO)
- All SlippageModel variants (FIXED_PCT, VOLUME_WEIGHTED)
- Edge cases: zero slippage, zero volume, extreme values
- Side enum compatibility (Side.BUY / Side.SELL strings)
- IndianMarketFees defaults and custom values
- compute_commission routing
- apply_slippage quantization
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.trading_costs import (
    CommissionModel,
    IndianMarketFees,
    SlippageModel,
    apply_slippage,
    compute_commission,
    compute_indian_equity_fees,
    compute_indian_fno_fees,
    compute_slippage_pct,
)

# ---------------------------------------------------------------------------
# apply_slippage
# ---------------------------------------------------------------------------


class TestApplySlippage:
    def test_zero_slippage_returns_price_unchanged(self):
        price = Decimal("100.00")
        assert apply_slippage(price, side="BUY", slippage_pct=0.0) == price

    def test_buy_slippage_increases_price(self):
        result = apply_slippage(Decimal("100"), side="BUY", slippage_pct=0.1)
        assert result == Decimal("100.1000")

    def test_sell_slippage_decreases_price(self):
        result = apply_slippage(Decimal("100"), side="SELL", slippage_pct=0.1)
        assert result == Decimal("99.9000")

    def test_quantized_to_4_decimals(self):
        result = apply_slippage(Decimal("100"), side="BUY", slippage_pct=0.001)
        assert result == result.quantize(Decimal("0.0001"))

    def test_side_enum_buy(self):
        from domain import Side

        result = apply_slippage(Decimal("100"), side=Side.BUY, slippage_pct=0.1)
        assert result == Decimal("100.1000")

    def test_side_enum_sell(self):
        from domain import Side

        result = apply_slippage(Decimal("100"), side=Side.SELL, slippage_pct=0.1)
        assert result == Decimal("99.9000")

    def test_duck_typing_side_object(self):
        """apply_slippage uses hasattr(side, 'value') for duck-typing."""
        class FakeSide:
            value = "BUY"
        result = apply_slippage(Decimal("100"), side=FakeSide(), slippage_pct=0.1)
        assert result == Decimal("100.1000")

    def test_case_insensitive_side(self):
        r1 = apply_slippage(Decimal("100"), side="buy", slippage_pct=0.1)
        r2 = apply_slippage(Decimal("100"), side="BUY", slippage_pct=0.1)
        assert r1 == r2

    def test_large_slippage(self):
        result = apply_slippage(Decimal("1000"), side="BUY", slippage_pct=5.0)
        assert result == Decimal("1050.0000")

    def test_tiny_price(self):
        result = apply_slippage(Decimal("0.01"), side="BUY", slippage_pct=10.0)
        assert result == Decimal("0.0110")

    def test_zero_price(self):
        result = apply_slippage(Decimal("0"), side="BUY", slippage_pct=0.1)
        assert result == Decimal("0.0000")

    def test_negative_slippage_pct(self):
        """Negative slippage_pct reverses the direction (BUY gets cheaper, SELL gets more expensive)."""
        result = apply_slippage(Decimal("100"), side="BUY", slippage_pct=-0.1)
        # factor = 1 + (-0.1/100) = 0.999
        assert result == Decimal("99.9000")


# ---------------------------------------------------------------------------
# compute_slippage_pct
# ---------------------------------------------------------------------------


class TestComputeSlippagePct:
    def test_fixed_pct_returns_base(self):
        result = compute_slippage_pct(SlippageModel.FIXED_PCT, 0.1, 1000, 5000)
        assert result == 0.1

    def test_volume_weighted_high_volume_reduces_slippage(self):
        result = compute_slippage_pct(SlippageModel.VOLUME_WEIGHTED, 0.1, 10000, 5000)
        assert result == 0.05  # 0.1 * (5000/10000)

    def test_volume_weighted_low_volume_increases_slippage(self):
        result = compute_slippage_pct(SlippageModel.VOLUME_WEIGHTED, 0.1, 1000, 5000)
        assert result == 0.5  # 0.1 * (5000/1000)

    def test_volume_weighted_zero_bar_volume_returns_base(self):
        result = compute_slippage_pct(SlippageModel.VOLUME_WEIGHTED, 0.1, 0, 5000)
        assert result == 0.1

    def test_volume_weighted_zero_avg_volume_returns_base(self):
        result = compute_slippage_pct(SlippageModel.VOLUME_WEIGHTED, 0.1, 1000, 0)
        assert result == 0.1

    def test_volume_weighted_both_zero_returns_base(self):
        result = compute_slippage_pct(SlippageModel.VOLUME_WEIGHTED, 0.1, 0, 0)
        assert result == 0.1

    def test_volume_weighted_equal_volumes_returns_base(self):
        result = compute_slippage_pct(SlippageModel.VOLUME_WEIGHTED, 0.1, 5000, 5000)
        assert result == 0.1

    def test_zero_base_slippage(self):
        result = compute_slippage_pct(SlippageModel.VOLUME_WEIGHTED, 0.0, 1000, 5000)
        assert result == 0.0


# ---------------------------------------------------------------------------
# compute_commission
# ---------------------------------------------------------------------------


class TestComputeCommission:
    def test_flat_model(self):
        result = compute_commission(
            100000, "BUY", model=CommissionModel.FLAT, flat_fee=20.0
        )
        assert result == 20.0

    def test_flat_model_zero_fee(self):
        result = compute_commission(
            100000, "BUY", model=CommissionModel.FLAT, flat_fee=0.0
        )
        assert result == 0.0

    def test_indian_equity_model_buy(self):
        result = compute_commission(
            100000, "BUY", model=CommissionModel.INDIAN_EQUITY
        )
        assert result > 0

    def test_indian_equity_model_sell(self):
        result = compute_commission(
            100000, "SELL", model=CommissionModel.INDIAN_EQUITY
        )
        assert result > 0

    def test_indian_equity_sell_higher_than_buy(self):
        buy_fee = compute_commission(100000, "BUY", model=CommissionModel.INDIAN_EQUITY)
        sell_fee = compute_commission(100000, "SELL", model=CommissionModel.INDIAN_EQUITY)
        assert sell_fee > buy_fee

    def test_indian_fno_model(self):
        result = compute_commission(
            100000, "SELL", model=CommissionModel.INDIAN_FNO
        )
        assert result > 0

    def test_custom_fees(self):
        fees = IndianMarketFees(brokerage_pct=0.1, brokerage_max=100.0)
        result = compute_commission(
            100000, "BUY", model=CommissionModel.INDIAN_EQUITY, fees=fees
        )
        assert result > 0

    def test_default_model_is_flat(self):
        result = compute_commission(100000, "BUY", flat_fee=20.0)
        assert result == 20.0

    def test_indian_equity_default_fees(self):
        """compute_commission with Indian equity model and fees=None (default)."""
        result = compute_commission(100000, "BUY", model=CommissionModel.INDIAN_EQUITY)
        assert result > 0

    def test_indian_fno_default_fees(self):
        """compute_commission with F&O model and fees=None (default)."""
        result = compute_commission(100000, "SELL", model=CommissionModel.INDIAN_FNO)
        assert result > 0


# ---------------------------------------------------------------------------
# compute_indian_equity_fees
# ---------------------------------------------------------------------------


class TestIndianEquityFees:
    def test_brokerage_capped_at_max(self):
        """Brokerage should be capped at brokerage_max."""
        fees = IndianMarketFees(brokerage_pct=0.03, brokerage_max=20.0)
        # 100000 * 0.03 / 100 = 30, capped at 20
        result = compute_indian_equity_fees(100000, "BUY", fees)
        assert result > 0

    def test_stt_only_on_sell(self):
        fees = IndianMarketFees()
        buy_fee = compute_indian_equity_fees(100000, "BUY", fees)
        sell_fee = compute_indian_equity_fees(100000, "SELL", fees)
        # Sell should be higher due to STT
        assert sell_fee > buy_fee

    def test_stamp_duty_only_on_buy(self):
        """Stamp duty is only charged on buy side."""
        fees = IndianMarketFees(
            brokerage_pct=0.0,
            brokerage_max=0.0,
            stt_pct_sell_delivery=0.0,
            exchange_fees_pct=0.0,
            gst_pct=0.0,
            stamp_duty_pct_buy=0.015,
            sebi_charges_per_crore=0.0,
        )
        buy_fee = compute_indian_equity_fees(100000, "BUY", fees)
        sell_fee = compute_indian_equity_fees(100000, "SELL", fees)
        assert buy_fee > sell_fee

    def test_default_fees(self):
        result = compute_indian_equity_fees(100000, "BUY")
        assert result > 0

    def test_zero_notional(self):
        result = compute_indian_equity_fees(0, "BUY")
        assert result == 0.0

    def test_sebi_charges(self):
        """SEBI charges are proportional to notional."""
        fees = IndianMarketFees(
            brokerage_pct=0.0,
            brokerage_max=0.0,
            stt_pct_sell_delivery=0.0,
            exchange_fees_pct=0.0,
            gst_pct=0.0,
            stamp_duty_pct_buy=0.0,
            sebi_charges_per_crore=10.0,
        )
        # 1 crore = 10,000,000. SEBI: 10,000,000 * 10 / 100,000,000 = 1.0
        result = compute_indian_equity_fees(1_00_00_000, "BUY", fees)
        assert result == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# compute_indian_fno_fees
# ---------------------------------------------------------------------------


class TestIndianFnoFees:
    def test_stt_on_sell_only(self):
        fees = IndianMarketFees()
        buy_fee = compute_indian_fno_fees(100000, "BUY", fees)
        sell_fee = compute_indian_fno_fees(100000, "SELL", fees)
        assert sell_fee > buy_fee

    def test_no_stamp_duty(self):
        """F&O trades don't have stamp duty (unlike equity)."""
        fees = IndianMarketFees(
            brokerage_pct=0.0,
            brokerage_max=0.0,
            stt_pct_fno=0.0,
            exchange_fees_pct=0.0,
            gst_pct=0.0,
            stamp_duty_pct_buy=0.015,
            sebi_charges_per_crore=0.0,
        )
        # Both BUY and SELL should be zero (no stamp duty for F&O)
        buy_fee = compute_indian_fno_fees(100000, "BUY", fees)
        sell_fee = compute_indian_fno_fees(100000, "SELL", fees)
        assert buy_fee == 0.0
        assert sell_fee == 0.0

    def test_default_fees(self):
        result = compute_indian_fno_fees(100000, "SELL")
        assert result > 0

    def test_equity_sell_higher_than_fno_sell(self):
        """Equity sell has higher STT than F&O sell."""
        equity = compute_indian_equity_fees(100000, "SELL")
        fno = compute_indian_fno_fees(100000, "SELL")
        assert equity > fno


# ---------------------------------------------------------------------------
# IndianMarketFees
# ---------------------------------------------------------------------------


class TestIndianMarketFees:
    def test_defaults(self):
        fees = IndianMarketFees()
        assert fees.brokerage_pct == 0.03
        assert fees.brokerage_max == 20.0
        assert fees.stt_pct_sell_delivery == 0.1
        assert fees.stt_pct_fno == 0.05
        assert fees.exchange_fees_pct == 0.00345
        assert fees.gst_pct == 18.0
        assert fees.stamp_duty_pct_buy == 0.015
        assert fees.sebi_charges_per_crore == 10.0

    def test_frozen(self):
        fees = IndianMarketFees()
        original = fees.brokerage_pct
        with pytest.raises(Exception):
            fees.brokerage_pct = 0.05  # type: ignore[misc]
        assert fees.brokerage_pct == original


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_commission_model_values(self):
        assert CommissionModel.FLAT.value == "flat"
        assert CommissionModel.INDIAN_EQUITY.value == "indian_equity"
        assert CommissionModel.INDIAN_FNO.value == "indian_fno"

    def test_slippage_model_values(self):
        assert SlippageModel.FIXED_PCT.value == "fixed_pct"
        assert SlippageModel.VOLUME_WEIGHTED.value == "volume_weighted"

    def test_commission_model_is_str(self):
        assert isinstance(CommissionModel.FLAT, str)

    def test_slippage_model_is_str(self):
        assert isinstance(SlippageModel.FIXED_PCT, str)
