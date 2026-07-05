"""Provider protocols for the Rich Instrument architecture.

These protocols define the contracts that broker adapters must satisfy
to be injected into Instruments. All are @runtime_checkable for
structural type checking.

ADR-005: Provider protocols replace service pass-through wrappers.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from inc_trade.domain.entities import Candle, MarketDepth, OptionChain, Quote


@runtime_checkable
class InstrumentDataProvider(Protocol):
    """Protocol for real-time market data access.

    Broker adapters implement this to provide quote, LTP, and depth
    data to Instruments without requiring a full BrokerGateway.
    """

    def quote(self, symbol: str, exchange: str) -> Quote: ...
    def ltp(self, symbol: str, exchange: str) -> Decimal: ...
    def depth(self, symbol: str, exchange: str, levels: int = 5) -> MarketDepth: ...
    def quote_batch(self, symbols: list[str], exchange: str) -> dict[str, Quote]: ...


@runtime_checkable
class HistoricalDataProvider(Protocol):
    """Protocol for historical OHLCV candle data."""

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        resolution: str,
    ) -> list[Candle]: ...


@runtime_checkable
class StreamingDataProvider(Protocol):
    """Protocol for live streaming subscriptions."""

    def subscribe(self, instrument: Any, callback: Any) -> Any: ...
    def unsubscribe(self, instrument: Any) -> None: ...

    @property
    def is_connected(self) -> bool: ...


@runtime_checkable
class DepthProvider(Protocol):
    """Protocol for market depth with configurable levels.

    Broker-specific implementations provide 5, 20, 30, or 200 levels.
    """

    def depth(self, symbol: str, exchange: str, levels: int = 5) -> MarketDepth: ...

    @property
    def max_levels(self) -> int: ...
