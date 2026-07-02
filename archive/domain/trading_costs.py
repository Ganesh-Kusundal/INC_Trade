"""Canonical trading cost models — single source of truth for commission and slippage.

This module consolidates all commission/slippage calculation logic that was
previously duplicated across:
- analytics/replay/models.py (compute_indian_equity_fees, compute_indian_fno_fees)
- analytics/replay/engine.py (_compute_commission, _compute_slippage_pct)
- application/execution/simulated_fill.py (apply_slippage)
- analytics/paper/engine.py (inline slippage/commission)
- analytics/indicators/halftrend_backtest.py (inline commission)
- datalake/research/fast_backtest.py (inline slippage/commission)

All consumers should import from this module going forward.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CommissionModel(str, Enum):
    """Commission calculation model."""

    FLAT = "flat"  # Legacy: flat fee per trade
    INDIAN_EQUITY = "indian_equity"  # Indian equity market fees
    INDIAN_FNO = "indian_fno"  # Indian F&O market fees


class SlippageModel(str, Enum):
    """Slippage calculation model."""

    FIXED_PCT = "fixed_pct"  # Fixed percentage of price
    VOLUME_WEIGHTED = "volume_weighted"  # Slippage inversely proportional to volume


# ---------------------------------------------------------------------------
# Indian Market Fee Structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndianMarketFees:
    """Realistic Indian market transaction costs.

    Based on NSE fee structure as of 2024. Values are approximate
    and should be updated when exchange fee schedules change.
    """

    brokerage_pct: float = 0.03  # 0.03% per leg (or ₹20 cap)
    brokerage_max: float = 20.0  # ₹20 per order cap
    stt_pct_sell_delivery: float = 0.1  # STT on sell side (delivery)
    stt_pct_sell_intraday: float = 0.025  # STT on sell side (intraday)
    stt_pct_fno: float = 0.05  # STT on F&O sell
    exchange_fees_pct: float = 0.00345  # NSE transaction charges
    gst_pct: float = 18.0  # GST on brokerage + exchange fees
    stamp_duty_pct_buy: float = 0.015  # Stamp duty on buy side
    sebi_charges_per_crore: float = 10.0  # SEBI regulatory fees


# ---------------------------------------------------------------------------
# Commission Calculation
# ---------------------------------------------------------------------------


def compute_commission(
    notional: float,
    side: str,
    *,
    model: CommissionModel = CommissionModel.FLAT,
    flat_fee: float = 0.0,
    fees: IndianMarketFees | None = None,
) -> float:
    """Compute commission based on the configured model.

    Parameters
    ----------
    notional : float
        Trade value (price * quantity).
    side : str
        "BUY" or "SELL".
    model : CommissionModel
        How to calculate commission.
    flat_fee : float
        Flat commission per trade (used when model is FLAT).
    fees : IndianMarketFees, optional
        Fee structure for Indian market models.

    Returns
    -------
    float
        Commission amount in INR.
    """
    if model == CommissionModel.FLAT:
        return flat_fee
    elif model == CommissionModel.INDIAN_EQUITY:
        return compute_indian_equity_fees(notional, side, fees)
    elif model == CommissionModel.INDIAN_FNO:
        return compute_indian_fno_fees(notional, side, fees)
    return 0.0


def compute_indian_equity_fees(
    notional: float,
    side: str,
    fees: IndianMarketFees | None = None,
) -> float:
    """Compute total transaction cost for Indian equity delivery/intraday.

    Parameters
    ----------
    notional : float
        Trade value (price * quantity).
    side : str
        "BUY" or "SELL".
    fees : IndianMarketFees, optional
        Fee structure. Defaults to standard NSE fees.

    Returns
    -------
    float
        Total fees in INR.
    """
    if fees is None:
        fees = IndianMarketFees()

    brokerage = min(notional * fees.brokerage_pct / 100, fees.brokerage_max)
    stt = notional * fees.stt_pct_sell_delivery / 100 if side == "SELL" else 0
    exchange = notional * fees.exchange_fees_pct / 100
    gst = (brokerage + exchange) * fees.gst_pct / 100
    stamp = notional * fees.stamp_duty_pct_buy / 100 if side == "BUY" else 0
    sebi = notional * fees.sebi_charges_per_crore / 100_000_000

    return brokerage + stt + exchange + gst + stamp + sebi


def compute_indian_fno_fees(
    notional: float,
    side: str,
    fees: IndianMarketFees | None = None,
) -> float:
    """Compute total transaction cost for Indian F&O trades.

    Parameters
    ----------
    notional : float
        Trade value (price * quantity).
    side : str
        "BUY" or "SELL".
    fees : IndianMarketFees, optional
        Fee structure. Defaults to standard NSE F&O fees.

    Returns
    -------
    float
        Total fees in INR.
    """
    if fees is None:
        fees = IndianMarketFees()

    brokerage = min(notional * fees.brokerage_pct / 100, fees.brokerage_max)
    stt = notional * fees.stt_pct_fno / 100 if side == "SELL" else 0
    exchange = notional * fees.exchange_fees_pct / 100
    gst = (brokerage + exchange) * fees.gst_pct / 100
    sebi = notional * fees.sebi_charges_per_crore / 100_000_000

    return brokerage + stt + exchange + gst + sebi


# ---------------------------------------------------------------------------
# Slippage Calculation
# ---------------------------------------------------------------------------


def apply_slippage(
    price: Decimal,
    *,
    side: str | object,
    slippage_pct: float = 0.0,
) -> Decimal:
    """Apply per-side slippage. Buy = price up, Sell = price down.

    Parameters
    ----------
    price : Decimal
        Base price.
    side : str or Side enum
        "BUY" or "SELL", or a :class:`domain.types.Side` enum value.
    slippage_pct : float
        Slippage as percentage of price (0.01 = 0.01%).

    Returns
    -------
    Decimal
        Price adjusted for slippage, quantized to 4 decimal places.
    """
    if slippage_pct == 0:
        return price
    side_val = side.value.upper() if hasattr(side, "value") else str(side).upper()
    factor = (1 + slippage_pct / 100) if side_val == "BUY" else (1 - slippage_pct / 100)
    return (price * Decimal(str(factor))).quantize(Decimal("0.0001"))


def compute_slippage_pct(
    slippage_model: SlippageModel,
    base_slippage_pct: float,
    bar_volume: float,
    avg_volume: float = 0.0,
) -> float:
    """Compute effective slippage percentage based on the configured model.

    For VOLUME_WEIGHTED model, slippage is inversely proportional to volume:
        effective_slippage = base_slippage * (avg_volume / bar_volume)
    Higher volume results in less slippage.

    Parameters
    ----------
    slippage_model : SlippageModel
        How to calculate slippage.
    base_slippage_pct : float
        Base slippage percentage.
    bar_volume : float
        Volume of the current bar.
    avg_volume : float
        Average volume used as reference for VOLUME_WEIGHTED model.

    Returns
    -------
    float
        Effective slippage as a percentage of price.
    """
    if slippage_model == SlippageModel.FIXED_PCT:
        return base_slippage_pct
    elif slippage_model == SlippageModel.VOLUME_WEIGHTED:
        if avg_volume <= 0 or bar_volume <= 0:
            return base_slippage_pct
        ratio = avg_volume / bar_volume
        return base_slippage_pct * ratio
    return base_slippage_pct
