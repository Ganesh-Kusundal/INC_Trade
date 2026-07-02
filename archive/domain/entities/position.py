"""Position and Holding domain entities — includes PositionState machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum

from domain.enums import ProductType


@dataclass(slots=True, frozen=True)
class Position:
    """Canonical position — returned by every broker adapter."""

    symbol: str
    exchange: str
    quantity: int = 0
    avg_price: Decimal = Decimal("0")
    ltp: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None

    @property
    def pnl(self) -> Decimal:
        if self.quantity > 0:
            return Decimal(str(self.quantity)) * (self.ltp - self.avg_price)
        elif self.quantity < 0:
            return Decimal(str(abs(self.quantity))) * (self.avg_price - self.ltp)
        return Decimal("0")

    def with_ltp(self, ltp: Decimal) -> Position:
        """Return a new Position with the last traded price updated."""
        unrealized = (
            Decimal(str(self.quantity)) * (ltp - self.avg_price)
            if self.quantity != 0
            else Decimal("0")
        )
        return replace(self, ltp=ltp, unrealized_pnl=unrealized)

    def with_fill(self, quantity: int, price: Decimal) -> Position:
        """Return a new Position after applying a signed fill."""
        new_qty = self.quantity + quantity
        new_avg = self._compute_avg_price(new_qty, quantity, price)
        new_realized = self._compute_realized_pnl(quantity, price)
        new_unrealized = self._compute_unrealized(new_qty, price, new_avg)
        return replace(
            self,
            quantity=new_qty,
            avg_price=new_avg,
            ltp=price,
            unrealized_pnl=new_unrealized,
            realized_pnl=new_realized,
        )

    def _compute_avg_price(self, new_qty: int, fill_qty: int, fill_price: Decimal) -> Decimal:
        if self.quantity == 0:
            return fill_price
        is_closing = (self.quantity > 0 and fill_qty < 0) or (self.quantity < 0 and fill_qty > 0)
        if is_closing:
            if new_qty == 0:
                return Decimal("0")
            elif abs(fill_qty) > abs(self.quantity):
                return fill_price
            return self.avg_price
        return (Decimal(str(self.quantity)) * self.avg_price + Decimal(str(fill_qty)) * fill_price) / Decimal(
            str(new_qty)
        )

    def _compute_realized_pnl(self, fill_qty: int, fill_price: Decimal) -> Decimal:
        if self.quantity == 0:
            return self.realized_pnl
        is_closing = (self.quantity > 0 and fill_qty < 0) or (self.quantity < 0 and fill_qty > 0)
        if not is_closing:
            return self.realized_pnl
        closed = min(abs(self.quantity), abs(fill_qty))
        pnl_factor = Decimal("1") if self.quantity > 0 else Decimal("-1")
        return self.realized_pnl + Decimal(str(closed)) * (fill_price - self.avg_price) * pnl_factor

    def _compute_unrealized(self, new_qty: int, price: Decimal, avg_price: Decimal) -> Decimal:
        if new_qty == 0:
            return Decimal("0")
        return Decimal(str(new_qty)) * (price - avg_price)


@dataclass(slots=True, frozen=True)
class Holding:
    """Canonical holding — returned by every broker adapter."""

    symbol: str
    exchange: str
    quantity: int = 0
    available_quantity: int = 0
    avg_price: Decimal = Decimal("0")
    ltp: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    correlation_id: str | None = None

class PositionState(str, Enum):
    """Position lifecycle states.

    Tracks the lifecycle of a position from flat through open, reducing,
    closed, or reversed states. Used by PositionManager to enforce valid
    state transitions and prevent illegal position updates.

    Transitions:
    - FLAT → OPEN (buy/sell creates position)
    - FLAT → REVERSED (sell after buy or vice versa in same session)
    - OPEN → REDUCING (partial exit)
    - OPEN → REVERSED (full exit + reverse)
    - OPEN → CLOSED (full exit)
    - REDUCING → FLAT (complete exit)
    - REDUCING → OPEN (add to position)
    - REDUCING → REVERSED (full exit + reverse)
    - REVERSED → FLAT (complete exit)
    - REVERSED → OPEN (reverse back)
    - REVERSED → REDUCING (reduce reversed position)
    - CLOSED → FLAT (reset for new session)
    """

    FLAT = "FLAT"
    OPEN = "OPEN"
    REDUCING = "REDUCING"
    CLOSED = "CLOSED"
    REVERSED = "REVERSED"

    @property
    def is_active(self) -> bool:
        """True if position has non-zero quantity."""
        return self in (PositionState.OPEN, PositionState.REDUCING, PositionState.REVERSED)

    @property
    def is_terminal(self) -> bool:
        """True if position is closed or flat (no active exposure)."""
        return self in (PositionState.FLAT, PositionState.CLOSED)


# Position state machine transition table
# Used by PositionManager to validate position updates
POSITION_STATE_TRANSITIONS: dict[PositionState, frozenset[PositionState]] = {
    PositionState.FLAT: frozenset(
        {
            PositionState.OPEN,
            PositionState.REVERSED,
        }
    ),
    PositionState.OPEN: frozenset(
        {
            PositionState.OPEN,  # Add to position
            PositionState.REDUCING,
            PositionState.CLOSED,
            PositionState.REVERSED,
        }
    ),
    PositionState.REDUCING: frozenset(
        {
            PositionState.FLAT,
            PositionState.OPEN,
            PositionState.REVERSED,
            PositionState.CLOSED,
        }
    ),
    PositionState.CLOSED: frozenset(
        {
            PositionState.FLAT,  # Reset for new session
        }
    ),
    PositionState.REVERSED: frozenset(
        {
            PositionState.FLAT,
            PositionState.OPEN,
            PositionState.REDUCING,
            PositionState.CLOSED,
        }
    ),
}
