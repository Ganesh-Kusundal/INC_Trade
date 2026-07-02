"""Upstox gateway adapters — extracted from god-class gateway.py.

Each adapter encapsulates a single responsibility:
- HistoricalAdapter: Historical candle fetching and timeframe mapping
- StreamManagerAdapter: WebSocket subscription lifecycle management
- TickTranslatorAdapter: Raw tick payload to canonical Quote translation
- PortfolioAdapter: Portfolio, positions, holdings, and funds queries

The main UpstoxBrokerGateway acts as a thin facade delegating to these adapters.

P-2.2: Removed duplicate MarketDataAdapter - use brokers.upstox.market_data.market_data_adapter
which implements the MarketDataProvider ABC correctly.
"""

from __future__ import annotations

from brokers.upstox.adapters.historical_adapter import HistoricalAdapter
from brokers.upstox.adapters.portfolio_adapter import PortfolioAdapter
from brokers.upstox.adapters.stream_manager import StreamManagerAdapter
from brokers.upstox.adapters.tick_translator import TickTranslatorAdapter

__all__ = [
    "HistoricalAdapter",
    "PortfolioAdapter",
    "StreamManagerAdapter",
    "TickTranslatorAdapter",
]
