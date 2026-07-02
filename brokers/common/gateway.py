"""MarketDataGateway — broker-agnostic contract.

This is the SINGLE interface that all broker adapters must implement.
No broker-specific fields are allowed in the contract.

Methods are grouped into:
  - Market Data (read-only): history, quote, ltp, depth, option_chain, future_chain, stream
  - Batch Market Data: ltp_batch, quote_batch, history_batch
  - Trading: place_order, cancel_order, get_orderbook, get_trade_book
  - Portfolio: positions, holdings, funds, trades
  - Instrument: search, load_instruments
  - Lifecycle: describe, capabilities, close

.. note:: Pre-v1.0 — method signatures may change without notice.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Callable

import pandas as pd

from brokers.common.capabilities import (
    BrokerCapabilities,
)
from brokers.common.gateway_interfaces import (
    BatchMarketDataProvider,
    DerivativesProvider,
    InstrumentProvider,
    LifecycleAware,
    MarketDataProvider,
    PortfolioReader,
    StreamProvider,
    TradingExecutor,
)
from domain.constants import DEFAULT_DERIVATIVES_EXCHANGE, DEFAULT_EXCHANGE, DEFAULT_LOOKBACK_DAYS
from domain.entities import (
    Balance,
    FutureChain,
    Holding,
    MarketDepth,
    OptionChain,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)

# ---------------------------------------------------------------------------
# MarketDataGateway v1.0
# ---------------------------------------------------------------------------


class MarketDataGateway(
    MarketDataProvider,
    DerivativesProvider,
    BatchMarketDataProvider,
    TradingExecutor,
    PortfolioReader,
    InstrumentProvider,
    StreamProvider,
    LifecycleAware,
    ABC,
):
    """Contract for broker-agnostic market data access — REF-028 ISP composition.

    This monolithic gateway is **composed** from eight narrow ISP interfaces
    (MarketDataProvider, DerivativesProvider, ...). Consumers that only need a
    subset of the contract can depend on the corresponding narrow interface
    instead of the full gateway.

    All broker adapters (Dhan, Upstox, Paper) must implement every method.
    No broker-specific fields are allowed in return types.
    """

    # -----------------------------------------------------------------------
    # Market Data (read-only)
    # -----------------------------------------------------------------------

    @abstractmethod
    def history(
        self,
        symbol: str | list[str],
        exchange: str = DEFAULT_EXCHANGE,
        timeframe: str = "1D",
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Return OHLCV candles as a canonical DataFrame.

        Schema: timestamp, open, high, low, close, volume, oi, symbol, exchange, timeframe

        Parameters
        ----------
        symbol : str or list[str]
            Single symbol or list of symbols.
        exchange : str
            Exchange identifier (NSE, BSE, NFO, etc.).
        timeframe : str
            Candle interval: 1m, 5m, 15m, 30m, 1h, 1D.
        lookback_days : int
            Number of days to look back (ignored if from_date/to_date set).
        from_date : str or None
            Start date (YYYY-MM-DD). Overrides lookback_days.
        to_date : str or None
            End date (YYYY-MM-DD). Defaults to today.
        """
        ...

    @abstractmethod
    def quote(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Quote:
        """Return a canonical Quote with: symbol, ltp, open, high, low, close, volume, change, bid, ask, timestamp."""
        ...

    @abstractmethod
    def ltp(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Decimal:
        """Return last traded price."""
        ...

    @abstractmethod
    def depth(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> MarketDepth:
        """Return canonical MarketDepth with bids and asks."""
        ...

    @abstractmethod
    def option_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
        expiry: str | None = None,
    ) -> OptionChain:
        """Return option chain with strikes, CE/PE data."""
        ...

    @abstractmethod
    def future_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
    ) -> FutureChain:
        """Return futures chain with expiry dates and prices."""
        ...

    @abstractmethod
    def stream(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Start WebSocket streaming for a symbol.

        Parameters
        ----------
        mode : str
            LTP, QUOTE, or DEPTH.
        on_tick : callable or None
            Callback invoked with tick dict for each update.

        Returns
        -------
        Stream handle with .connect(), .disconnect(), .is_connected.
        """
        ...

    @abstractmethod
    def stream_depth(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        depth_type: str = "DEPTH_5",
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Any:
        """Start WebSocket depth streaming for a symbol."""
        ...

    @abstractmethod
    def stream_order(self, on_order: Any | None = None) -> Any:
        """Start WebSocket order/portfolio updates streaming."""
        ...

    # -----------------------------------------------------------------------
    # Batch Market Data
    # -----------------------------------------------------------------------

    @abstractmethod
    def ltp_batch(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict[str, Decimal]:
        """Return LTP for multiple symbols.

        Returns dict mapping symbol -> Decimal LTP.
        """
        ...

    @abstractmethod
    def quote_batch(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict[str, Quote]:
        """Return quotes for multiple symbols.

        Returns dict mapping symbol -> Quote domain object.
        """
        ...

    @abstractmethod
    def history_batch(
        self,
        symbols: list[str],
        exchange: str = DEFAULT_EXCHANGE,
        timeframe: str = "1D",
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> pd.DataFrame:
        """Return historical data for multiple symbols.

        Returns concatenated DataFrame with 'symbol' column.
        """
        ...

    # -----------------------------------------------------------------------
    # Trading
    # -----------------------------------------------------------------------

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        side: str = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> OrderResponse:
        """Place an order. Returns OrderResponse with success, order_id, message."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an open order.

        Returns:
            :class:`OrderResponse` with ``success=True`` when the broker
            confirmed the cancellation. A response with
            ``success=False`` carries the broker's error message in
            :attr:`OrderResponse.message` and a diagnostic code in
            :attr:`OrderResponse.error_code`.

            The boolean-equivalent form ``bool(response)`` and
            ``response.is_success`` is preserved for backward compat
            — both are equivalent to ``response.success``.

        Notes:
            Implementations MUST NOT raise for non-existent or
            already-cancelled orders; they MUST return a structured
            failure response instead. The only acceptable exceptions
            are infrastructure failures (network, auth) which the
            caller is expected to retry.
        """
        ...

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        """Modify an open order. Not all brokers support this."""
        raise NotImplementedError(f"{type(self).__name__} does not support modify_order")

    @abstractmethod
    def get_orderbook(self) -> list[Order]:
        """Return all orders."""
        ...

    @abstractmethod
    def get_trade_book(self) -> list[Trade]:
        """Return all trades."""
        ...

    # -----------------------------------------------------------------------
    # Portfolio
    # -----------------------------------------------------------------------

    @abstractmethod
    def positions(self) -> list[Position]:
        """Return current positions."""
        ...

    @abstractmethod
    def holdings(self) -> list[Holding]:
        """Return holdings."""
        ...

    @abstractmethod
    def funds(self) -> Balance:
        """Return fund limits."""
        ...

    @abstractmethod
    def trades(self) -> list[Trade]:
        """Return trades (alias for get_trade_book)."""
        ...

    # -----------------------------------------------------------------------
    # Instrument
    # -----------------------------------------------------------------------

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        """Search instruments by symbol name."""
        ...

    @abstractmethod
    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        """Load instrument master data."""
        ...

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    @abstractmethod
    def capabilities(self) -> BrokerCapabilities:
        """Return broker capability matrix."""
        ...

    @abstractmethod
    def describe(self) -> dict:
        """Return broker metadata: name, version, connected, etc."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close all connections and clean up resources."""
        ...


# ---------------------------------------------------------------------------
# Observability Provider Protocol
# ---------------------------------------------------------------------------


class ObservabilityProvider:
    """Protocol for exposing broker-specific observability data.

    This protocol decouples the CLI observability layer from broker
    internals. Instead of using getattr() chains to probe private
    attributes like _conn, _client, _token_scheduler, brokers implement
    this protocol to expose canonical observability data.

    All methods have default implementations returning empty/no-op data,
    so brokers that don't support certain features (e.g., no WebSocket)
    don't need to implement anything.

    Usage:
        # In broker adapter (e.g., DhanGateway):
        def get_connection_status(self) -> dict[str, bool]:
            return {
                "market_feed": self.market_feed.is_connected if self.market_feed else False,
                "order_stream": self.order_stream.is_connected if self.order_stream else False,
            }

        # In CLI observability builder:
        status = gateway.get_connection_status()
        gauges["market_stream_connected"] = 1.0 if status.get("market_feed", False) else 0.0
    """

    def get_connection_status(self) -> dict[str, bool]:
        """Return connection status for all streams.

        Returns:
            Dict mapping stream name to connection status.
            Example: {"market_feed": True, "order_stream": False}
        """
        return {}  # Default: no streams

    def get_circuit_breaker_states(self) -> dict[str, int]:
        """Return circuit breaker states.

        Returns:
            Dict mapping circuit breaker name to state value.
            State values: 0=CLOSED, 1=OPEN, 2=HALF_OPEN
            Example: {"read_cb": 0, "write_cb": 1, "admin_cb": 0}
        """
        return {}  # Default: no circuit breakers

    def get_token_refresh_metrics(self) -> dict[str, int]:
        """Return token refresh metrics.

        Returns:
            Dict with token refresh statistics.
            Example: {"refresh_count": 42, "error_count": 0}
        """
        return {"refresh_count": 0, "error_count": 0}  # Default: no token refresh

    def get_rate_limiter_metrics(self) -> dict[str, int]:
        """Return rate limiter metrics.

        Returns:
            Dict with rate limiter statistics.
            Example: {"tokens_available": 10, "requests_throttled": 5}
        """
        return {"tokens_available": 0, "requests_throttled": 0}  # Default: no rate limiter
