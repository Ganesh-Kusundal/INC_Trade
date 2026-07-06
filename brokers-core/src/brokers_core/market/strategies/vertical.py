"""Vertical spreads — bull call, bear put, bull put, bear call."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from brokers_core.domain.enums import Side
from brokers_core.market.strategies.base import OptionStrategy, StrategyLeg


class VerticalSpread(OptionStrategy):
    """Vertical spread strategy with two legs of the same type.

    Supports:
        - ``bull_call``: buy lower strike call, sell higher strike call
        - ``bear_call``: sell lower strike call, buy higher strike call
        - ``bull_put``: buy lower strike put, sell higher strike put
        - ``bear_put``: sell lower strike put, buy higher strike put

    Args:
        underlying: The underlying Instrument.
        long_leg: The long (bought) leg Instrument.
        short_leg: The short (sold) leg Instrument.
        quantity: Number of contracts.
        side: ``"bull_call"``, ``"bear_call"``, ``"bull_put"``, or ``"bear_put"``.
    """

    def __init__(
        self,
        underlying: Any,
        long_leg: Any,
        short_leg: Any,
        quantity: int,
        side: str,
    ) -> None:
        self._side = side.lower()
        legs = (
            StrategyLeg(instrument=long_leg, side=Side.BUY, quantity=quantity),
            StrategyLeg(instrument=short_leg, side=Side.SELL, quantity=quantity),
        )
        super().__init__(underlying=underlying, legs=legs)

    def _validate(self) -> None:
        if self._side not in {"bull_call", "bear_call", "bull_put", "bear_put"}:
            raise ValueError(
                f"Invalid vertical spread side: {self._side!r}. "
                "Must be one of: bull_call, bear_call, bull_put, bear_put"
            )

        long_leg, short_leg = self.legs
        lt = long_leg.instrument.option_type
        st = short_leg.instrument.option_type
        if lt != st:
            raise ValueError(f"Vertical spread legs must have same option type. Got {lt} and {st}")

    @property
    def is_call_spread(self) -> bool:
        return self._side in {"bull_call", "bear_call"}

    @property
    def is_bullish(self) -> bool:
        return self._side in {"bull_call", "bull_put"}

    @property
    def width(self) -> Decimal:
        """Difference between the two strikes."""
        long_strike = self.legs[0].instrument.strike or Decimal("0")
        short_strike = self.legs[1].instrument.strike or Decimal("0")
        return abs(long_strike - short_strike)

    @property
    def max_profit(self) -> Decimal:
        if self._side == "bull_call":
            return self.width - abs(self.net_premium)
        if self._side == "bear_call":
            return abs(self.net_premium)
        if self._side == "bull_put":
            return abs(self.net_premium)
        if self._side == "bear_put":
            return self.width - abs(self.net_premium)
        return Decimal("0")

    @property
    def max_loss(self) -> Decimal:
        if self._side == "bull_call":
            return abs(self.net_premium)
        if self._side == "bear_call":
            return self.width - abs(self.net_premium)
        if self._side == "bull_put":
            return self.width - abs(self.net_premium)
        if self._side == "bear_put":
            return abs(self.net_premium)
        return Decimal("0")

    @property
    def break_even(self) -> list[Decimal]:
        long_strike = self.legs[0].instrument.strike or Decimal("0")
        short_strike = self.legs[1].instrument.strike or Decimal("0")
        premium = abs(self.net_premium)

        if self._side == "bull_call":
            return [long_strike + premium]
        if self._side == "bear_call":
            return [short_strike + premium]
        if self._side == "bull_put":
            return [short_strike - premium]
        if self._side == "bear_put":
            return [long_strike - premium]
        return []
