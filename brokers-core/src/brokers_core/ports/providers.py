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
    data directly to Instruments.
    """

    def quote(self, symbol: str, exchange: str) -> Quote: ...
    def ltp(self, symbol: str, exchange: str) -> Decimal: ...
    def depth(self, symbol: str, exchange: str, levels: int = 5) -> MarketDepth: ...
    def quote_batch(self, symbols: list[str], exchange: str) -> dict[str, Quote]: ...

    def get_option_chain(
        self,
        underlying: str,
        exchange: str,
        expiry: str | None = None,
    ) -> OptionChain: ...


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


@runtime_checkable
class OrderProvider(Protocol):
    """Protocol for order placement, modification, and cancellation.

    Broker adapters implement this to allow Instruments to place orders
    directly without requiring a full OrderExecutionPort.
    """

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: str,
        quantity: int,
        order_type: Any = None,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> Any: ...

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> Any: ...

    def cancel_order(self, order_id: str) -> Any: ...
