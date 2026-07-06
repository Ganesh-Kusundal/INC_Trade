"""Market data port — read-only market data access.

Narrow interface (ISP) for market data queries. Broker adapters
implement this to provide LTP, quotes, depth, and historical data.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from brokers.domain.constants.exchanges import DEFAULT_EQUITY_EXCHANGE
from brokers.domain.entities import MarketDepth, Quote


@runtime_checkable
class MarketDataPort(Protocol):
    def ltp(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE) -> Decimal: ...
    def quote(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE) -> Quote: ...
    def depth(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE) -> MarketDepth: ...
    def ltp_batch(
        self, symbols: list[str], exchange: str = DEFAULT_EQUITY_EXCHANGE
    ) -> dict[str, Decimal]: ...
    def quote_batch(
        self, symbols: list[str], exchange: str = DEFAULT_EQUITY_EXCHANGE
    ) -> dict[str, Quote]: ...
