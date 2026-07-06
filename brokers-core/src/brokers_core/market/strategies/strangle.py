"""Strangle strategy — long/short strangle (OTM call + OTM put)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from brokers_core.domain.enums import Side
from brokers_core.market.strategies.base import OptionStrategy, StrategyLeg


class Strangle(OptionStrategy):
    """Strangle strategy: long/short OTM call + OTM put.

    A **long strangle** profits from large moves (cheaper than straddle).
    A **short strangle** profits from range-bound price action.

    Args:
        underlying: The underlying Instrument.
        call_leg: OTM call option Instrument.
        put_leg: OTM put option Instrument.
        quantity: Number of contracts for each leg.
        side: ``"long"`` or ``"short"``.
    """

    def __init__(
        self,
        underlying: Any,
        call_leg: Any,
        put_leg: Any,
        quantity: int,
        side: str = "long",
    ) -> None:
        self._side = side.lower()
        if self._side == "long":
            legs = (
                StrategyLeg(instrument=call_leg, side=Side.BUY, quantity=quantity),
                StrategyLeg(instrument=put_leg, side=Side.BUY, quantity=quantity),
            )
        else:
            legs = (
                StrategyLeg(instrument=call_leg, side=Side.SELL, quantity=quantity),
                StrategyLeg(instrument=put_leg, side=Side.SELL, quantity=quantity),
            )
        super().__init__(underlying=underlying, legs=legs)

    def _validate(self) -> None:
        if self._side not in {"long", "short"}:
            raise ValueError(f"Invalid strangle side: {self._side!r}. Must be 'long' or 'short'.")
        call_leg, put_leg = self.legs
        if not call_leg.instrument.is_call() or not put_leg.instrument.is_put():
            raise ValueError("Strangle requires one call and one put instrument.")
        call_strike = call_leg.instrument.strike or Decimal("0")
        put_strike = put_leg.instrument.strike or Decimal("0")
        if put_strike >= call_strike:
            raise ValueError(
                f"Strangle requires put strike < call strike. "
                f"Got put={put_strike}, call={call_strike}"
            )

    @property
    def is_long(self) -> bool:
        return self._side == "long"

    @property
    def call_strike(self) -> Decimal:
        return self.legs[0].instrument.strike or Decimal("0")

    @property
    def put_strike(self) -> Decimal:
        return self.legs[1].instrument.strike or Decimal("0")

    @property
    def max_profit(self) -> Decimal:
        if self._side == "long":
            return Decimal("Inf")
        return Decimal(str(self.net_premium)) if self.net_premium > 0 else Decimal("0")

    @property
    def max_loss(self) -> Decimal:
        if self._side == "long":
            return abs(self.net_premium)
        return Decimal("Inf")

    @property
    def break_even(self) -> list[Decimal]:
        premium = abs(self.net_premium)
        return [self.put_strike - premium, self.call_strike + premium]

    def pnl_at(self, spot: Decimal) -> Decimal:
        premium = abs(self.net_premium)
        if self._side == "long":
            # Long strangle: profit when spot moves beyond either strike + premium
            if spot <= self.put_strike:
                return (self.put_strike - spot) - premium
            elif spot >= self.call_strike:
                return (spot - self.call_strike) - premium
            else:
                return -premium
        else:
            # Short strangle: profit when spot stays between strikes - premium
            if spot <= self.put_strike:
                return premium - (self.put_strike - spot)
            elif spot >= self.call_strike:
                return premium - (spot - self.call_strike)
            else:
                return premium
