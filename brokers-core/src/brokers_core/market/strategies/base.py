"""OptionStrategy — base class for multi-leg option strategies.

All strategies are composed of ``Instrument`` objects and produce
orders via the strategy's ``place_orders()`` method.

Usage::

    from inc_trade.market.strategies import VerticalSpread

    chain = inst.option_chain("2025-01-30")
    strikes = chain.nearest_strikes(3)

    spread = VerticalSpread(
        underlying=inst,
        long_leg=strikes[0].call.instrument,   # buy lower strike call
        short_leg=strikes[2].call.instrument,   # sell higher strike call
        quantity=25,
        side="bull_call",
    )

    spread.max_profit    # → Decimal
    spread.max_loss      # → Decimal
    spread.net_premium   # → Decimal
    spread.place_orders()  # → list[OrderResponse]
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class StrategyLeg:
    """A single leg in a multi-leg strategy.

    Attributes:
        instrument: The Instrument to trade.
        side: "BUY" or "SELL".
        quantity: Number of units.
        ratio: Leg ratio (default 1). For spreads with unequal legs.
    """

    instrument: Any
    side: str
    quantity: int
    ratio: int = 1


class OptionStrategy(ABC):
    """Abstract base for multi-leg option strategies.

    Every strategy is defined by its legs (instruments + sides) and
    can calculate risk metrics and generate orders.
    """

    legs: tuple[StrategyLeg, ...]
    underlying: Any
    net_premium: Decimal

    def __init__(
        self,
        underlying: Any,
        legs: tuple[StrategyLeg, ...],
    ) -> None:
        self.underlying = underlying
        self.legs = legs
        self._validate()

    @abstractmethod
    def _validate(self) -> None:
        """Validate the strategy legs are compatible.

        Raises ``ValueError`` if legs are incompatible.
        """

    @property
    @abstractmethod
    def max_profit(self) -> Decimal:
        """Maximum possible profit for this strategy."""

    @property
    @abstractmethod
    def max_loss(self) -> Decimal:
        """Maximum possible loss for this strategy."""

    @property
    @abstractmethod
    def break_even(self) -> list[Decimal]:
        """Break-even price(s) for this strategy."""

    @property
    def net_premium(self) -> Decimal:
        """Net premium paid (positive) or received (negative) per unit.

        This is the per-share / per-unit premium (not multiplied by
        quantity or lot size). Use this for max_profit, max_loss, and
        break_even calculations. The total position value is
        ``net_premium * lot_size * quantity``.
        """
        total = Decimal("0")
        for leg in self.legs:
            price = self._leg_price(leg)
            if leg.side.upper() == "BUY":
                total -= price
            else:
                total += price
        return total

    def _leg_price(self, leg: StrategyLeg) -> Decimal:
        """Get the current price of a leg instrument."""
        try:
            quote = leg.instrument.quote()
            if hasattr(quote, "ltp"):
                return quote.ltp
            if isinstance(quote, dict):
                return Decimal(str(quote.get("ltp", 0)))
            return Decimal("0")
        except Exception:
            return Decimal("0")

    def pnl_at(self, spot: Decimal) -> Decimal:
        """Calculate PnL at a given spot price."""
        total = Decimal("0")
        for leg in self.legs:
            price = self._leg_price(leg)
            instr = leg.instrument
            if instr.is_call():
                intrinsic = max(Decimal("0"), spot - (instr.strike or Decimal("0")))
            elif instr.is_put():
                intrinsic = max(Decimal("0"), (instr.strike or Decimal("0")) - spot)
            else:
                intrinsic = spot - price  # futures/equity
            if leg.side.upper() == "BUY":
                total += (intrinsic - price) * leg.quantity * leg.ratio
            else:
                total += (price - intrinsic) * leg.quantity * leg.ratio
        return total

    def place_orders(self, **kwargs: Any) -> list[Any]:
        """Place all leg orders via their instruments.

        Args:
            **kwargs: Additional order parameters forwarded to each leg's
                ``buy()`` or ``sell()`` method.

        Returns:
            List of OrderResponse objects (one per leg).
        """
        results: list[Any] = []
        for leg in self.legs:
            qty = leg.quantity * leg.ratio
            if leg.side.upper() == "BUY":
                result = leg.instrument.buy(quantity=qty, **kwargs)
            else:
                result = leg.instrument.sell(quantity=qty, **kwargs)
            results.append(result)
        return results

    def __repr__(self) -> str:
        cls = type(self).__name__
        leg_summary = ", ".join(
            f"{leg.side} {leg.quantity}x {leg.instrument.symbol}" for leg in self.legs
        )
        return f"{cls}({leg_summary})"
