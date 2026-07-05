"""VWAP — Volume-Weighted Average Price calculator.

VWAP is the running average price weighted by trade volume. Formula::

    VWAP = Σ(price * volume) / Σ(volume)

This is a stateful calculator: feed it ``Trade`` objects and read the
current VWAP. Reset to start a new session.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inc_trade.domain.entities import Trade


@dataclass
class VWAPCalculator:
    """Running VWAP calculator fed by ``Trade`` events.

    Attributes:
        cumulative_pv: Σ(price * volume) so far.
        cumulative_volume: Σ(volume) so far.
        trade_count: Number of trades consumed.
    """

    cumulative_pv: Decimal = Decimal("0")
    cumulative_volume: int = 0
    trade_count: int = 0

    def update(self, trade: Trade) -> None:
        """Incorporate a single trade into the running VWAP.

        Args:
            trade: ``Trade`` domain entity with price and quantity.
        """
        if trade.quantity <= 0:
            return
        self.cumulative_pv += trade.price * Decimal(trade.quantity)
        self.cumulative_volume += trade.quantity
        self.trade_count += 1

    def update_raw(self, price: Decimal, quantity: int) -> None:
        """Incorporate a raw price * quantity observation.

        Args:
            price: Trade price.
            quantity: Trade quantity.
        """
        if quantity <= 0:
            return
        self.cumulative_pv += price * Decimal(quantity)
        self.cumulative_volume += quantity
        self.trade_count += 1

    @property
    def value(self) -> Decimal:
        """Current VWAP. ``Decimal('0')`` if no trades consumed."""
        if self.cumulative_volume <= 0:
            return Decimal("0")
        return self.cumulative_pv / Decimal(self.cumulative_volume)

    def reset(self) -> None:
        """Reset state for a new session."""
        self.cumulative_pv = Decimal("0")
        self.cumulative_volume = 0
        self.trade_count = 0
