"""Iron Condor — four-leg strategy for range-bound markets."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from brokers_core.domain.enums import Side
from brokers_core.market.strategies.base import OptionStrategy, StrategyLeg


class IronCondor(OptionStrategy):
    """Iron Condor: sell lower strike put, buy OTM put, sell lower call, buy OTM call.

    Profits when the underlying stays between the short strikes. Max loss
    is limited to the width of one wing minus the net premium.

    Args:
        underlying: The underlying Instrument.
        long_put_leg: Long (bought) OTM put — defines left wing.
        short_put_leg: Short (sold) put — defines left body.
        short_call_leg: Short (sold) call — defines right body.
        long_call_leg: Long (bought) OTM call — defines right wing.
        quantity: Number of contracts per leg.
    """

    def __init__(
        self,
        underlying: Any,
        long_put_leg: Any,
        short_put_leg: Any,
        short_call_leg: Any,
        long_call_leg: Any,
        quantity: int,
    ) -> None:
        legs = (
            StrategyLeg(instrument=long_put_leg, side=Side.BUY, quantity=quantity),
            StrategyLeg(instrument=short_put_leg, side=Side.SELL, quantity=quantity),
            StrategyLeg(instrument=short_call_leg, side=Side.SELL, quantity=quantity),
            StrategyLeg(instrument=long_call_leg, side=Side.BUY, quantity=quantity),
        )
        super().__init__(underlying=underlying, legs=legs)

    def _validate(self) -> None:
        lp, sp, sc, lc = self.legs
        if not lp.instrument.is_put() or not sp.instrument.is_put():
            raise ValueError("Iron condor requires two put legs (long + short).")
        if not sc.instrument.is_call() or not lc.instrument.is_call():
            raise ValueError("Iron condor requires two call legs (short + long).")

        put_wing = lp.instrument.strike or Decimal("0")
        put_body = sp.instrument.strike or Decimal("0")
        call_body = sc.instrument.strike or Decimal("0")
        call_wing = lc.instrument.strike or Decimal("0")

        if not (put_wing < put_body < call_body < call_wing):
            raise ValueError(
                "Iron condor requires strikes: long_put < short_put < short_call < long_call."
            )

    @property
    def max_profit(self) -> Decimal:
        return abs(self.net_premium) if self.net_premium > 0 else Decimal("0")

    @property
    def max_loss(self) -> Decimal:
        # Wing width = distance between short and long on one side
        put_body = self.legs[1].instrument.strike or Decimal("0")
        put_wing = self.legs[0].instrument.strike or Decimal("0")
        put_width = abs(put_body - put_wing)
        call_body = self.legs[2].instrument.strike or Decimal("0")
        call_wing = self.legs[3].instrument.strike or Decimal("0")
        call_width = abs(call_body - call_wing)
        return max(put_width, call_width) - abs(self.net_premium)

    @property
    def break_even(self) -> list[Decimal]:
        premium = abs(self.net_premium)
        put_body = self.legs[1].instrument.strike or Decimal("0")
        call_body = self.legs[2].instrument.strike or Decimal("0")
        return [put_body - premium, call_body + premium]
