"""Trading Context — orders, accounts, portfolio, positions, risk.

This bounded context owns everything related to trading:
- Account aggregate (owner of orders and portfolio)
- Order placement, modification, cancellation
- Portfolio tracking (positions, holdings, funds)
- Risk checks and kill switch

Trading MUST NOT import from market.
"""

from inc_trade.trading.account import Account as Account
from inc_trade.trading.account import AccountStatus as AccountStatus
from inc_trade.trading.account import AccountType as AccountType
from inc_trade.trading.account_registry import (
    AccountRegistry as AccountRegistry,
)
from inc_trade.trading.context import AccountHandle as AccountHandle
from inc_trade.trading.context import TradingContext as TradingContext
from inc_trade.trading.portfolio import (
    ExposureSummary as ExposureSummary,
)
from inc_trade.trading.portfolio import (
    PortfolioAggregator as PortfolioAggregator,
)

__all__ = [
    "Account",
    "AccountHandle",
    "AccountRegistry",
    "AccountStatus",
    "AccountType",
    "ExposureSummary",
    "PortfolioAggregator",
    "TradingContext",
]
