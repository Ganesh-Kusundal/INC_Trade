"""Market data port — read-only market data access.

Narrow interface (ISP) for market data queries. Broker adapters
implement this to provide LTP, quotes, depth, and historical data.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from brokers.domain.entities import MarketDepth, Quote


class MarketDataPort(Protocol):
    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal: ...
    def quote(self, symbol: str, exchange: str = "NSE") -> Quote: ...
    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth: ...
