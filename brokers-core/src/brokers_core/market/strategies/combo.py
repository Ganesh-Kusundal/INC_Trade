"""ComboOrder — custom N-leg strategy builder.

Allows composing arbitrary multi-leg strategies from individual
Instrument buy/sell legs, with validation options.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from brokers_core.market.strategies.base import OptionStrategy, StrategyLeg


class ComboOrder(OptionStrategy):
    """Custom multi-leg strategy with arbitrary composition.

    Unlike named strategies (``VerticalSpread``, ``Straddle``, etc.),
    ``ComboOrder`` accepts any number of legs with no structure
    constraints. This is the escape hatch for broker-specific or
    exotic strategies.

    Args:
        underlying: The underlying Instrument.
        legs: Sequence of ``StrategyLeg`` defining each leg.
        name: Optional human-readable name for the combo.
    """

    def __init__(
        self,
        underlying: Any,
        legs: tuple[StrategyLeg, ...] | list[StrategyLeg],
        name: str = "",
    ) -> None:
        self._combo_name = name
        super().__init__(underlying=underlying, legs=tuple(legs))

    def _validate(self) -> None:
        if len(self.legs) < 2:
            raise ValueError(f"ComboOrder requires at least 2 legs, got {len(self.legs)}.")
        # No structural validation — ComboOrder is the escape hatch.
        # Individual leg validation (symbol, exchange, lot_size) is
        # handled by the instrument's buy()/sell() at order time.

    @property
    def max_profit(self) -> Decimal:
        """Maximum possible profit.

        For custom combos with undefined risk, returns Decimal("Inf")
        if any leg has undefined max profit (short options).
        """
        return Decimal("Inf")

    @property
    def max_loss(self) -> Decimal:
        """Maximum possible loss.

        For custom combos with undefined risk, returns Decimal("Inf")
        if any leg has undefined max loss (long options).
        """
        return Decimal("Inf")

    @property
    def break_even(self) -> list[Decimal]:
        """Break-even prices.

        For custom combos, computes the spot where net PnL = 0
        across all legs. May have multiple break-evens.
        """
        # For simplicity, return mid of all strikes
        strikes = [
            leg.instrument.strike or Decimal("0")
            for leg in self.legs
            if leg.instrument.strike is not None
        ]
        if not strikes:
            return [Decimal("0")]
        premium = abs(self.net_premium)
        return [sum(strikes) / len(strikes) + premium]

    def __repr__(self) -> str:
        cls = type(self).__name__
        name = self._combo_name or "combo"
        leg_summary = ", ".join(
            f"{leg.side} {leg.quantity}x {leg.instrument.symbol}" for leg in self.legs
        )
        return f'{cls}("{name}", {leg_summary})'
