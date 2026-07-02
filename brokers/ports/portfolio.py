"""Portfolio port — positions, holdings, and funds.

Narrow interface (ISP) for portfolio queries. Broker adapters
implement this to provide position and account information.
"""

from __future__ import annotations

from typing import Protocol

from brokers.domain.entities import Balance, Holding, Position, Trade


class PortfolioPort(Protocol):
    def positions(self) -> list[Position]: ...
    def holdings(self) -> list[Holding]: ...
    def funds(self) -> Balance: ...
    def trades(self) -> list[Trade]: ...
