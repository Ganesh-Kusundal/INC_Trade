"""Portfolio capability group for Upstox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PortfolioCapability:
    """Holdings, positions, funds, and margin."""

    portfolio: Any
    margin: Any
    portfolio_client: Any
    margin_client: Any

    def positions(self) -> Any:
        return self.portfolio.get_positions()

    def holdings(self) -> Any:
        return self.portfolio.get_holdings()

    def funds(self) -> Any:
        return self.portfolio.get_funds()
