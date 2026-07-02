"""Portfolio adapter — portfolio, positions, holdings, and funds queries.

Responsibility: Fetch account portfolio data including positions, holdings,
and fund limits from Upstox broker.
Thread-safe: All methods are stateless and thread-safe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain import Balance, Holding, Position, Trade

if TYPE_CHECKING:
    from brokers.upstox.broker import UpstoxBroker


class PortfolioAdapter:
    """Adapter for portfolio and account data queries.

    Encapsulates:
    - Fund limits and balance queries
    - Position tracking (open/closed positions)
    - Holdings (long-term equity holdings)
    - Trade book (executed trades)

    Thread Safety:
        All methods are stateless and thread-safe. Delegates to broker's
        portfolio and order_query adapters which maintain their own state.

    Example::

        adapter = PortfolioAdapter(broker)
        balance = adapter.get_funds()
        positions = adapter.get_positions()
        holdings = adapter.get_holdings()
        trades = adapter.get_trades()
    """

    def __init__(self, broker: UpstoxBroker) -> None:
        """Initialize with broker facade.

        Args:
            broker: UpstoxBroker instance providing access to portfolio adapters
        """
        self._broker = broker

    def get_funds(self) -> Balance:
        """Fetch account fund limits and available balance.

        Returns:
            Balance dataclass with available_margin, used_margin, etc.
        """
        return self._broker.portfolio.get_fund_limits()

    def get_positions(self) -> list[Position]:
        """Fetch all open and closed positions.

        Returns:
            List of Position dataclasses with P&L data
        """
        return self._broker.portfolio.get_positions()

    def get_holdings(self) -> list[Holding]:
        """Fetch long-term equity holdings (CNC deliveries).

        Returns:
            List of Holding dataclasses with cost basis and current value
        """
        return self._broker.portfolio.get_holdings()

    def get_trades(self) -> list[Trade]:
        """Fetch today's trade book (executed trades).

        Returns:
            List of Trade dataclasses with execution details
        """
        return self._broker.order_query.get_trades()

    def get_orderbook(self) -> list:
        """Fetch current order book (all orders).

        Returns:
            List of Order dataclasses with order status
        """
        return self._broker.order_query.get_order_list()
