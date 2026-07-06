"""Straddle strategy — long/short straddle (same strike call + put)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from inc_trade.market.strategies.base import OptionStrategy, StrategyLeg


class Straddle(OptionStrategy):
    """Straddle strategy: long/short call + put at the same strike.

    A **long straddle** profits from high volatility (big move in either
    direction). A **short straddle** profits from low volatility (price
    staying near the strike).

    Args:
        underlying: The underlying Instrument.
        call_leg: Call option Instrument at the chosen strike.
        put_leg: Put option Instrument at the same strike.
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
                StrategyLeg(instrument=call_leg, side="BUY", quantity=quantity),
                StrategyLeg(instrument=put_leg, side="BUY", quantity=quantity),
            )
        else:
            legs = (
                StrategyLeg(instrument=call_leg, side="SELL", quantity=quantity),
                StrategyLeg(instrument=put_leg, side="SELL", quantity=quantity),
            )
        super().__init__(underlying=underlying, legs=legs)

    def _validate(self) -> None:
        if self._side not in {"long", "short"}:
            raise ValueError(f"Invalid straddle side: {self._side!r}. Must be 'long' or 'short'.")
        call_leg, put_leg = self.legs
        if not call_leg.instrument.is_call() or not put_leg.instrument.is_put():
            raise ValueError("Straddle requires one call and one put instrument.")

    @property
    def is_long(self) -> bool:
        return self._side == "long"

    @property
    def strike(self) -> Decimal:
        """The straddle strike (same for both legs)."""
        return self.legs[0].instrument.strike or Decimal("0")

    @property
    def max_profit(self) -> Decimal:
        if self._side == "long":
            return Decimal("Inf")  # unlimited upside
        return Decimal(str(self.net_premium)) if self.net_premium > 0 else Decimal("0")

    @property
    def max_loss(self) -> Decimal:
        if self._side == "long":
            return abs(self.net_premium)  # total premium paid
        return Decimal("Inf")  # unlimited downside on short straddle

    @property
    def break_even(self) -> list[Decimal]:
        premium = abs(self.net_premium)
        strike = self.strike
        if self._side == "long":
            return [strike - premium, strike + premium]
        return [strike - premium, strike + premium]

    def pnl_at(self, spot: Decimal) -> Decimal:
        """Calculate PnL at a given spot price (overrides base for straddle)."""
        premium = abs(self._leg_price(self.legs[0]) + self._leg_price(self.legs[1]))
        strike = self.strike

        if self._side == "long":
            # Long straddle: profit = move beyond premium
            return max(spot - strike, strike - spot) - premium
        else:
            # Short straddle: profit = premium - move beyond
            return premium - max(spot - strike, strike - spot)
