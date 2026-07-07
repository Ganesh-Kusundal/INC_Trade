"""Provider protocols — interface-segregated by capability domain.

Following the Interface Segregation Principle, the single ``Provider``
protocol has been split into focused interfaces.  Consumers depend only
on the capabilities they need:

  - :class:`LifecycleProvider` — identity, connect, disconnect (base)
  - :class:`MarketDataProvider` — quotes, history, depth, instruments
  - :class:`ExecutionProvider` — orders, positions, portfolio
  - :class:`StreamingProvider` — real-time subscriptions

Full-service brokers (Dhan, Upstox, Paper) implement :class:`Provider`
which composes all four.  Data-only providers (CSV, Yahoo) implement
only ``MarketDataProvider`` — no ``NotSupportedError`` stubs needed.

All protocols are ``@runtime_checkable``, enabling ``isinstance()``
checks for auto-detection at ::

    if isinstance(provider, ExecutionProvider):
        account = Account(provider, ...)

The protocols use ``TYPE_CHECKING`` for forward references to domain
types to avoid circular imports.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from brokers.domain.account import Account
    from brokers.domain.capabilities import ProviderCapabilities
    from brokers.domain.historical import HistoricalSeries
    from brokers.domain.instrument import Instrument
    from brokers.domain.option_chain import FutureChain, OptionChain
    from brokers.domain.requests import ModifyOrderRequest, OrderRequest
    from brokers.domain.values import (
        Balance,
        Holding,
        MarketDepth,
        OrderResponse,
        Position,
        Quote,
        Subscription,
        Trade,
    )
    from brokers.provider.extensions import ExtensionAccess


# ── Base: identity + lifecycle ────────────────────────────────────────────


@runtime_checkable
class LifecycleProvider(Protocol):
    """Base protocol — identity, capabilities, and lifecycle.

    Every provider must expose at minimum broker identity and
    connect/disconnect semantics.
    """

    @property
    def broker_id(self) -> str:
        """Unique identifier for this provider (e.g. 'dhan', 'upstox')."""
        ...

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Declare what this provider supports."""
        ...

    @property
    def extensions(self) -> ExtensionAccess:
        """Typed access to broker-specific extensions."""
        ...

    @property
    def is_connected(self) -> bool:
        """Whether the provider is connected and ready."""
        ...

    async def connect(self) -> None:
        """Establish connection (HTTP session, WebSocket, auth)."""
        ...

    async def disconnect(self) -> None:
        """Close all connections."""
        ...


# ── Market data: quotes, history, depth, instruments, derivatives ──────────


@runtime_checkable
class MarketDataProvider(LifecycleProvider, Protocol):
    """Market data and instrument search.

    Implemented by all providers.  Data-only providers (CSV, Yahoo)
    implement *only* this interface — no execution stubs needed.
    """

    async def get_quote(self, instrument: Instrument) -> Quote:
        """Full quote (LTP + OHLCV)."""
        ...

    async def get_ltp(self, instrument: Instrument) -> Decimal:
        """Last traded price only."""
        ...

    async def get_depth(self, instrument: Instrument) -> MarketDepth:
        """Order book depth snapshot."""
        ...

    async def get_history(
        self,
        instrument: Instrument,
        *,
        timeframe: str = "1D",
        bars: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> HistoricalSeries:
        """Historical OHLCV bars."""
        ...

    async def search_instruments(self, query: str) -> list[Instrument]:
        """Fuzzy search for instruments by symbol or name."""
        ...

    async def get_instruments(
        self, exchange: str | None = None
    ) -> list[Instrument]:
        """Return all loaded instruments (instrument master)."""
        ...

    async def resolve_instrument(
        self, symbol: str, exchange: str
    ) -> Instrument:
        """Resolve a symbol to a full Instrument with broker-specific IDs."""
        ...

    async def get_option_chain(
        self,
        underlying: Instrument,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        """Get the option chain for an underlying instrument."""
        ...

    async def get_future_chain(
        self, underlying: Instrument
    ) -> FutureChain:
        """Get the futures chain for an underlying instrument."""
        ...


# ── Execution: orders, positions, portfolio ───────────────────────────────


@runtime_checkable
class ExecutionProvider(LifecycleProvider, Protocol):
    """Order placement, modification, cancellation, and portfolio.

    Full-service brokers (Dhan, Upstox) and paper trading implement
    this.  Data-only providers do NOT.

    ``default_account`` provides the integration point for
    ``Instrument.buy()`` — the instrument delegates to the account
    for risk-gated execution.
    """

    @property
    def default_account(self) -> Account:
        """The default account for this provider.

        Used by ``Instrument.buy()`` when no account is specified.
        """
        ...

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order. Returns OrderResponse.ok() or .fail()."""
        ...

    async def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an open order by broker ID."""
        ...

    async def modify_order(
        self, request: ModifyOrderRequest
    ) -> OrderResponse:
        """Modify price/quantity of an open order."""
        ...

    async def get_positions(self) -> list[Position]:
        """Return all open positions."""
        ...

    async def get_balance(self) -> Balance:
        """Return account balance and margin usage."""
        ...

    async def get_orders(self) -> list[Any]:
        """Return current order book."""
        ...

    async def get_trades(self) -> list[Trade]:
        """Return today's executed trades."""
        ...

    async def get_holdings(self) -> list[Holding]:
        """Return long-term equity holdings."""
        ...


# ── Streaming: real-time subscriptions ────────────────────────────────────


@runtime_checkable
class StreamingProvider(LifecycleProvider, Protocol):
    """Real-time market data and order streaming.

    Providers that support WebSocket streams implement this.
    Data-only providers may skip it.
    """

    async def subscribe_quotes(
        self,
        instruments: list[Instrument],
        *,
        on_tick: Callable[[Quote], None] | None = None,
    ) -> Subscription:
        """Subscribe to real-time quote updates."""
        ...

    async def subscribe_depth(
        self,
        instruments: list[Instrument],
        *,
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Subscription:
        """Subscribe to real-time depth updates."""
        ...

    async def subscribe_orders(
        self,
        *,
        on_update: Callable[[Any], None] | None = None,
    ) -> Subscription:
        """Subscribe to order status updates."""
        ...

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Cancel an active subscription."""
        ...


# ── Unified Provider (composes all four — backward compatible) ─────────────


@runtime_checkable
class Provider(
    MarketDataProvider,
    ExecutionProvider,
    StreamingProvider,
    Protocol,
):
    """Unified protocol for full-service brokers.

    Compose all four focused interfaces.  Full-service brokers
    (Dhan, Upstox, Paper) implement this.  Data-only providers
    may implement only the sub-protocols they support.

    Consumers should depend on the narrowest interface needed:
      - :class:`MarketDataProvider` for quotes/history
      - :class:`ExecutionProvider` for orders/portfolio
      - :class:`StreamingProvider` for real-time feeds
    """

    pass


__all__ = [
    "ExecutionProvider",
    "LifecycleProvider",
    "MarketDataProvider",
    "Provider",
    "StreamingProvider",
]
