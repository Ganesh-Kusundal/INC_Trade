"""Portfolio service — domain layer for portfolio management.

This service provides business logic for fetching and analyzing portfolio
data. It depends on the PortfolioPort abstraction, not on any specific
broker implementation.
"""

from __future__ import annotations

import logging

from inc_trade.domain.entities import Balance, Holding, Position, Trade
from inc_trade.ports.portfolio import PortfolioPort

logger = logging.getLogger(__name__)


class PortfolioService:
    """Domain service for portfolio management.

    Encapsulates business rules for position analysis, risk management,
    and performance tracking.
    """

    def __init__(self, portfolio_port: PortfolioPort):
        """Initialize with a portfolio port.

        Args:
            portfolio_port: Broker-agnostic portfolio interface
        """
        self._portfolio_port = portfolio_port

    def positions(self) -> list[Position]:
        """Get all open positions.

        Returns:
            List of Position objects
        """
        return self._portfolio_port.positions()

    def holdings(self) -> list[Holding]:
        """Get all holdings.

        Returns:
            List of Holding objects
        """
        return self._portfolio_port.holdings()

    def funds(self) -> Balance:
        """Get account balance.

        Returns:
            Balance object
        """
        return self._portfolio_port.funds()

    def trades(self) -> list[Trade]:
        """Get trade history.

        Returns:
            List of Trade objects
        """
        return self._portfolio_port.trades()

    def get_net_position_value(self) -> float:
        """Calculate net value of all positions.

        Returns:
            Net position value in rupees
        """
        positions = self.positions()
        return sum(p.market_value for p in positions if p.market_value is not None)  # type: ignore[attr-defined]

    def total_unrealized_pnl(self) -> float:
        """Calculate total unrealized P&L across all positions.

        Returns:
            Total unrealized profit/loss in rupees
        """
        positions = self.positions()
        return sum(p.unrealized_pnl for p in positions)

    def total_realized_pnl(self) -> float:
        """Calculate total realized P&L from trades.

        Returns:
            Total realized profit/loss in rupees
        """
        trades = self.trades()
        return sum(t.pnl for t in trades if t.pnl is not None)  # type: ignore[attr-defined]

    def net_exposure(self) -> float:
        """Calculate net exposure across all positions.

        Returns:
            Net exposure in rupees
        """
        positions = self.positions()
        return sum(p.exposure for p in positions if p.exposure is not None)  # type: ignore[attr-defined]
