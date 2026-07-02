"""Simulated portfolio management for paper trading."""

from __future__ import annotations

from decimal import Decimal

from domain import Balance, Holding, Position
from domain.constants.defaults import PAPER_INITIAL_CAPITAL

from .paper_orders import PaperOrders


class PaperPortfolio:
    """Simulates portfolio state: positions, holdings, and account balance."""

    def __init__(
        self,
        orders: PaperOrders,
        initial_capital: Decimal = PAPER_INITIAL_CAPITAL,
    ) -> None:
        self._orders = orders
        self._holdings: list[Holding] = []
        self._capital = initial_capital

    def get_positions(self) -> list[Position]:
        return self._orders.get_positions()

    def get_holdings(self) -> list[Holding]:
        return list(self._holdings)

    def get_balance(self) -> Balance:
        positions = self._orders.get_positions()
        used = sum(abs(p.quantity) * p.avg_price for p in positions)
        realized = sum(p.realized_pnl for p in positions)
        available = self._capital - used + realized
        total = self._capital + realized
        return Balance(
            available_balance=available,
            used_margin=used,
            total_margin=total,
            sod_limit=total,
            collateral_amount=Decimal("0"),
            utilized_amount=used,
            withdrawable_balance=available,
        )
