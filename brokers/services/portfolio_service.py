"""Portfolio service — application-level portfolio queries.

Adds logging, PnL aggregation, and convenience methods on top of
the raw PortfolioPort.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.domain import Balance, Holding, Position, Trade
from brokers.ports.portfolio import PortfolioPort

logger = logging.getLogger(__name__)


class PortfolioService:
    def __init__(self, portfolio: PortfolioPort):
        self._portfolio = portfolio

    def positions(self) -> list[Position]:
        return self._portfolio.positions()

    def holdings(self) -> list[Holding]:
        return self._portfolio.holdings()

    def funds(self) -> Balance:
        return self._portfolio.funds()

    def trades(self) -> list[Trade]:
        return self._portfolio.trades()

    def total_unrealized_pnl(self) -> Decimal:
        return sum(
            (p.unrealized_pnl for p in self._portfolio.positions()),
            Decimal("0"),
        )

    def total_realized_pnl(self) -> Decimal:
        return sum(
            (p.realized_pnl for p in self._portfolio.positions()),
            Decimal("0"),
        )

    def net_exposure(self) -> Decimal:
        total = Decimal("0")
        for pos in self._portfolio.positions():
            total += pos.average_price * abs(pos.quantity)
        return total
