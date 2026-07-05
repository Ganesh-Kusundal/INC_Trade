"""Greeks — position-level options greeks.

This module aggregates ``OptionLeg`` greeks across a portfolio.
It does not compute greeks from Black-Scholes; it reads broker-provided
delta/theta/gamma/vega/iv and aggregates them weighted by quantity.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inc_trade.domain.entities import OptionLeg


class GreeksCalculator:
    """Aggregate and inspect option greeks.

    Usage::

        greeks = GreeksCalculator()
        total = greeks.portfolio_greeks([(leg_buy, 75), (leg_sell, 75)])
        # total["delta"], total["theta"], ...
    """

    @staticmethod
    def single_leg(leg: OptionLeg) -> dict[str, Decimal | None]:
        """Return greeks for a single option leg.

        Args:
            leg: ``OptionLeg`` with broker-supplied greeks.

        Returns:
            Dict with keys ``delta``, ``gamma``, ``theta``, ``vega``,
            ``iv`` (each may be ``None``).
        """
        return {
            "delta": leg.delta,
            "gamma": leg.gamma,
            "theta": leg.theta,
            "vega": leg.vega,
            "iv": leg.iv,
        }

    @staticmethod
    def portfolio_greeks(
        positions: list[tuple[OptionLeg, int]],
    ) -> dict[str, Decimal]:
        """Aggregate greeks across a portfolio of option positions.

        Each tuple is ``(leg, signed_quantity)``. Negative quantity
        represents a short position; greeks are weighted accordingly.

        Args:
            positions: List of ``(leg, signed_quantity)``.

        Returns:
            Dict with aggregate ``delta``, ``gamma``, ``theta``,
            ``vega``. Missing greeks contribute zero.
        """
        delta = Decimal("0")
        gamma = Decimal("0")
        theta = Decimal("0")
        vega = Decimal("0")
        for leg, qty in positions:
            sign = Decimal(qty)
            if leg.delta is not None:
                delta += leg.delta * sign
            if leg.gamma is not None:
                gamma += leg.gamma * sign
            if leg.theta is not None:
                theta += leg.theta * sign
            if leg.vega is not None:
                vega += leg.vega * sign
        return {
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
        }
