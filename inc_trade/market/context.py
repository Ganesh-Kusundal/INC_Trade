"""MarketDataContext — single entry point for the Market Data bounded context.

This is the public facade for all market data operations. It delegates to
the appropriate port implementations and returns rich domain objects
(``Instrument``, ``Quote``, ``OptionChain``, etc.) instead of raw broker DTOs.

Usage::

    context = MarketDataContext(
        registry=instrument_registry,
        market_data=dhan_market_data_port,
        historical=dhan_historical_port,
        options=dhan_options_port,
        streaming=dhan_streaming_port,
    )

    instrument = context.instrument("NSE:RELIANCE")
    quote = context.quote("RELIANCE")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from inc_trade.domain.entities import Candle, MarketDepth, OptionChain, Quote
from inc_trade.domain.events import QuoteTickEvent
from inc_trade.market.config import MarketDataConfig
from inc_trade.market.factory import InstrumentFactory
from inc_trade.market.instrument import Instrument
from inc_trade.market.instrument_registry import InstrumentRegistry
from inc_trade.market.quote_state import QuoteState
from inc_trade.market.subscription_manager import SubscriptionManager
from inc_trade.ports.event_publisher import EventPublisherPort
from inc_trade.ports.historical import HistoricalPort
from inc_trade.ports.instruments import InstrumentPort
from inc_trade.ports.market_data import MarketDataPort
from inc_trade.ports.options import OptionsPort
from inc_trade.ports.streaming import StreamingPort

logger = logging.getLogger(__name__)


class MarketDataContext:
    """Facade for all market data operations.

    Single entry point for the Market Data bounded context. Delegates
    all operations to injected port implementations.

    Args:
        registry: InstrumentRegistry for instrument lookups.
        market_data: MarketDataPort implementation (quotes, LTP, depth).
        config: Optional :class:`MarketDataConfig` grouping the remaining
            optional dependencies. When provided, it takes precedence over
            any of the individual kwargs below; when ``None`` (the default),
            the individual kwargs are used unchanged.
        historical: HistoricalPort implementation (OHLCV candles).
        options: OptionsPort implementation (option chains, expiries).
            Can be None for brokers that don't support options.
        streaming: StreamingPort implementation (live subscriptions).
            Can be None for brokers that don't support streaming.
        subscription_manager: Optional SubscriptionManager for deduplicated
            streaming subscriptions with reference counting. When provided,
            ``subscribe()`` uses this instead of calling ``streaming`` directly.
            Defaults to None for backward compatibility.
        streaming_router: Optional StreamingRouter for multi-backend streaming.
            When provided, ``subscribe()`` routes through the router.
            Defaults to None for backward compatibility.
    """

    def __init__(
        self,
        registry: InstrumentRegistry,
        market_data: MarketDataPort,
        config: MarketDataConfig | None = None,
        historical: HistoricalPort | None = None,
        historical_router: Any | None = None,
        options: OptionsPort | None = None,
        streaming: StreamingPort | None = None,
        instrument_port: InstrumentPort | None = None,
        subscription_manager: SubscriptionManager | None = None,
        streaming_router: Any | None = None,
        event_bus: EventPublisherPort | None = None,
        broker_id: str = "",
        market_router: Any | None = None,
        degraded_mode: Any | None = None,
    ) -> None:
        self._registry = registry
        self._market_data = market_data

        # Resolve effective config: an explicit MarketDataConfig object wins
        # over individual kwargs (the config takes precedence if both are
        # provided). When ``config`` is None, behavior is identical to the
        # pre-refactor keyword-argument path.
        if config is not None:
            self._historical = config.historical
            self._historical_router = config.historical_router
            self._options = config.options
            self._streaming = config.streaming
            self._instrument_port = config.instrument_port
            self._subscription_manager = config.subscription_manager
            self._streaming_router = config.streaming_router
            self._event_bus = config.event_bus
            self._broker_id = config.broker_id
            self._market_router = config.market_router

        else:
            self._historical = historical
            self._historical_router = historical_router
            self._options = options
            self._streaming = streaming
            self._instrument_port = instrument_port
            self._subscription_manager = subscription_manager
            self._streaming_router = streaming_router
            self._event_bus = event_bus
            self._broker_id = broker_id
            self._market_router = market_router

        # Degraded mode tracking
        if degraded_mode is not None:
            from inc_trade.market.degraded_mode import DegradedMode

            if isinstance(degraded_mode, DegradedMode):
                self._degraded_mode = degraded_mode
            else:
                self._degraded_mode = degraded_mode
        else:
            from inc_trade.market.degraded_mode import DegradedMode

            self._degraded_mode = DegradedMode()

        # Map of instrument_key -> QuoteState for auto-update on streaming ticks
        self._quote_states: dict[str, QuoteState] = {}

    # ── Instrument Lookup ──────────────────────────────────────────────

    def instrument(self, symbol: str, exchange: str = "NSE") -> InstrumentHandle:
        """Look up an instrument by symbol and exchange.

        Uses the InstrumentRegistry to guarantee one instance per
        ``{exchange}:{symbol}`` composite key. Returns an
        ``InstrumentHandle`` that wraps the raw ``Instrument`` with
        market data access methods (``quote()``, ``depth()``, …).

        The returned ``InstrumentHandle`` delegates to the underlying
        ``Instrument``, which now exposes the same methods directly
        (``instrument.quote()``, ``instrument.depth()``, …) for
        instrument-centric access patterns.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").
            exchange: Exchange code (e.g., "NSE", "BSE").

        Returns:
            InstrumentHandle instance.

        Raises:
            KeyError: If the instrument is not found in the registry.
        """
        key = f"{exchange}:{symbol}"
        inst = self._registry.get(key)
        if inst is None and self._instrument_port is not None:
            # Lazy resolve from the adapter port
            info = self._instrument_port.resolve(symbol, exchange)
            if info is not None:
                inst = self._registry.get_or_create(
                    key,
                    lambda: InstrumentFactory.create(
                        symbol=info.symbol,
                        exchange=info.exchange,
                        segment=info.segment,
                        name=info.name,
                        lot_size=info.lot_size,
                        context=self,
                    ),
                )
        if inst is None:
            raise KeyError(f"Instrument not found: {key}")
        # Ensure context is attached (cached instruments from registry
        # may not have it set if they were created before this method
        # was called, or if the MarketDataContext instance differs).
        if inst._delegate_context is None and inst._context is None:
            object.__setattr__(inst, "_context", self)
            object.__setattr__(inst, "_delegate_context", self)
        return InstrumentHandle(instrument=inst, context=self)

    # ── Quotes ─────────────────────────────────────────────────────────

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Get current quote for a symbol.

        When a ``market_router`` is configured, uses cache-first routing.
        Otherwise, falls back to direct ``MarketDataPort`` (legacy path).

        Args:
            symbol: Trading symbol.
            exchange: Exchange code (default: NSE).

        Returns:
            Quote domain entity.
        """
        if self._market_router is not None:
            return self._market_router.quote(symbol, exchange)
        return self._market_data.quote(symbol, exchange)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Get last traded price.

        When a ``market_router`` is configured, uses cache-first routing.
        Otherwise, falls back to direct ``MarketDataPort`` (legacy path).

        Args:
            symbol: Trading symbol.
            exchange: Exchange code (default: NSE).

        Returns:
            Last traded price as Decimal.
        """
        if self._market_router is not None:
            return self._market_router.ltp(symbol, exchange)
        return self._market_data.ltp(symbol, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        """Get quotes for multiple symbols.

        When a ``market_router`` is configured, uses cache-first routing.
        Otherwise, falls back to direct ``MarketDataPort`` (legacy path).

        Args:
            symbols: List of trading symbols.
            exchange: Exchange code (default: NSE).

        Returns:
            Dictionary mapping symbol to Quote.
        """
        if self._market_router is not None:
            return self._market_router.quote_batch(symbols, exchange)
        return self._market_data.quote_batch(symbols, exchange)

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Get LTP for multiple symbols.

        When a ``market_router`` is configured, uses cache-first routing.
        Otherwise, falls back to direct ``MarketDataPort`` (legacy path).

        Args:
            symbols: List of trading symbols.
            exchange: Exchange code (default: NSE).

        Returns:
            Dictionary mapping symbol to LTP.
        """
        if self._market_router is not None:
            return self._market_router.ltp_batch(symbols, exchange)
        return self._market_data.ltp_batch(symbols, exchange)

    # ── Depth ──────────────────────────────────────────────────────────

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Get market depth (order book).

        When a ``market_router`` is configured, uses cache-first routing.
        Otherwise, falls back to direct ``MarketDataPort`` (legacy path).

        Args:
            symbol: Trading symbol.
            exchange: Exchange code (default: NSE).

        Returns:
            MarketDepth domain entity.
        """
        if self._market_router is not None:
            return self._market_router.depth(symbol, exchange)
        return self._market_data.depth(symbol, exchange)

    # ── Historical Data ────────────────────────────────────────────────

    def ohlcv(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        """Fetch historical OHLCV candles.

        Args:
            symbol: Trading symbol.
            exchange: Exchange code.
            start_time: Start of time range.
            end_time: End of time range.
            resolution: Candle resolution (e.g., "1", "5", "15", "60", "1D").

        Returns:
            List of Candle domain entities.

        Raises:
            NotSupportedError: If historical data is not supported.
        """
        if self._historical is None:
            from inc_trade.domain.exceptions import NotSupportedError

            raise NotSupportedError("Historical data not supported by this broker")
        # Route through cache-first router if available
        if self._historical_router is not None:
            return self._historical_router.fetch_candles(
                symbol=symbol,
                exchange=exchange,
                start_time=start_time,
                end_time=end_time,
                resolution=resolution,
            )
        return self._historical.get_historical_candles(
            symbol=symbol,
            exchange=exchange,
            start_time=start_time,
            end_time=end_time,
            resolution=resolution,
        )

    # ── Options ────────────────────────────────────────────────────────

    def option_chain_raw(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        """Get the raw domain ``OptionChain`` (string symbols).

        This is the low-level method that returns the domain entity.
        Most callers should use :meth:`option_chain` which returns
        an ``InstrumentOptionChain`` with rich Instrument references.

        Args:
            underlying: Underlying symbol (e.g., "NIFTY").
            exchange: Exchange code (default: NFO).
            expiry: Expiry date string (e.g., "2024-01-25"). If None,
                the nearest expiry is used.

        Returns:
            ``OptionChain`` domain entity (string-based symbols).

        Raises:
            NotSupportedError: If options are not supported.
        """
        if self._options is None:
            from inc_trade.domain.exceptions import NotSupportedError

            raise NotSupportedError("Options not supported by this broker")
        return self._options.get_option_chain(
            underlying=underlying, exchange=exchange, expiry=expiry
        )

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> Any:
        """Get the full option chain with rich Instrument references.

        Resolves each option leg's string symbol into a real
        ``Instrument`` object so that you can call ``.quote()``,
        ``.buy()``, ``.sell()`` directly on chain legs.

        Args:
            underlying: Underlying symbol (e.g., "NIFTY").
            exchange: Exchange code (default: NFO).
            expiry: Expiry date string (e.g., "2024-01-25"). If None,
                the nearest expiry is used.

        Returns:
            ``InstrumentOptionChain`` with rich Instrument references.

        Raises:
            NotSupportedError: If options are not supported.
        """
        from inc_trade.market.option_chain import _build_instrument_chain

        raw = self.option_chain_raw(underlying, exchange, expiry)
        return _build_instrument_chain(self, raw)

    def expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        """Get available expiry dates for an underlying.

        Args:
            underlying: Underlying symbol.
            exchange: Exchange code (default: NFO).

        Returns:
            List of expiry date strings.
        """
        if self._options is None:
            from inc_trade.domain.exceptions import NotSupportedError

            raise NotSupportedError("Options not supported by this broker")
        return self._options.get_expiries(underlying=underlying, exchange=exchange)

    # ── Streaming ──────────────────────────────────────────────────────

    def subscribe(
        self,
        symbol: str,
        exchange: str,
        callback: Callable[[Quote], Any],
    ) -> Any:
        """Subscribe to live market data for a symbol.

        When a ``subscription_manager`` is configured (injected via constructor),
        uses it for deduplication and reference counting. Otherwise falls back
        to direct ``StreamingPort`` subscription (legacy path).

        Args:
            symbol: Trading symbol.
            exchange: Exchange code.
            callback: Callable invoked with each new Quote.

        Returns:
            StreamHandle for controlling the subscription.

        Raises:
            NotSupportedError: If streaming is not supported.
        """
        key = f"{exchange}:{symbol}"

        # Build the _quote_callback wrapper (shared across all paths)
        def _quote_callback(tick: Any) -> None:
            if isinstance(tick, dict):
                quote = Quote(
                    symbol=tick.get("symbol", symbol),
                    exchange=tick.get("exchange", exchange),
                    ltp=Decimal(str(tick.get("ltp", 0))),
                    open=Decimal(str(tick.get("open", 0))),
                    high=Decimal(str(tick.get("high", 0))),
                    low=Decimal(str(tick.get("low", 0))),
                    close=Decimal(str(tick.get("close", 0))),
                    volume=int(tick.get("volume", 0)),
                    seq_no=int(tick.get("seq_no", 0)),
                )
            else:
                quote = tick
            # Auto-update QuoteState
            if key in self._quote_states:
                self._quote_states[key].update_from_quote(quote)
            # Invalidate MarketRouter cache so next quote() fetches fresh data
            if self._market_router is not None:
                self._market_router.invalidate(symbol, exchange)
            # Publish QuoteTickEvent to EventBus (if wired)
            if self._event_bus is not None:
                tick_event = QuoteTickEvent(
                    composite_key=key,
                    symbol=quote.symbol,
                    exchange=quote.exchange,
                    ltp=quote.ltp,
                    bid=quote.bid if hasattr(quote, "bid") else Decimal("0"),
                    ask=quote.ask if hasattr(quote, "ask") else Decimal("0"),
                    volume=quote.volume,
                    oi=getattr(quote, "oi", 0),
                    source=self._broker_id,
                )
                self._event_bus.publish(tick_event)
            callback(quote)

        if self._subscription_manager is not None:
            # SubscriptionManager path: ref-counted deduplication
            self._subscription_manager.subscribe(
                key=key,
                exchange=exchange,
                callback=_quote_callback,
            )
            return SimpleSubscriptionHandle(
                manager=self._subscription_manager,
                key=key,
                exchange=exchange,
                callback=_quote_callback,
            )

        if self._streaming_router is not None:
            # StreamingRouter path: multi-backend (WebSocket, polling, etc.)
            self._streaming_router.subscribe(
                key=key,
                exchange=exchange,
                callback=_quote_callback,
            )
            return SimpleSubscriptionHandle(
                manager=self._streaming_router,
                key=key,
                exchange=exchange,
                callback=_quote_callback,
            )

        # Legacy path: direct StreamingPort subscription
        if self._streaming is None:
            from inc_trade.domain.exceptions import NotSupportedError

            raise NotSupportedError("Streaming not supported by this broker")

        import asyncio

        async def _subscribe() -> Any:
            await self._streaming.subscribe_quotes([symbol], exchange, callback)
            return None

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_subscribe())
            else:
                loop.run_until_complete(_subscribe())
        except RuntimeError:
            asyncio.run(_subscribe())

        return SimpleStreamHandle(self._streaming, [symbol], exchange)

    def unsubscribe(self, symbol: str, exchange: str) -> None:
        """Unsubscribe from live market data for a symbol.

        When a ``subscription_manager`` is configured, delegates to it.
        Otherwise falls back to direct ``StreamingPort`` unsubscription.

        Args:
            symbol: Trading symbol.
            exchange: Exchange code.
        """
        key = f"{exchange}:{symbol}"

        if self._subscription_manager is not None:
            self._subscription_manager.unsubscribe(key, exchange)
            return

        if self._streaming is None:
            return

        import asyncio

        async def _unsubscribe() -> None:
            await self._streaming.unsubscribe_quotes([symbol], exchange)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_unsubscribe())
            else:
                loop.run_until_complete(_unsubscribe())
        except RuntimeError:
            asyncio.run(_unsubscribe())

    # ── Quote State (Auto-Updated by Streaming) ────────────────────────

    def quote_state(self, symbol: str, exchange: str = "NSE") -> QuoteState:
        """Get the current QuoteState for an instrument (mutable, auto-updated).

        When streaming is active via the ``SubscriptionManager``, this state
        is automatically updated with each tick. Useful for strategies that
        need the current state without polling.

        Args:
            symbol: Trading symbol.
            exchange: Exchange code.

        Returns:
            QuoteState instance (same instance for same key — live updates).
        """
        key = f"{exchange}:{symbol}"
        if key not in self._quote_states:
            self._quote_states[key] = QuoteState(composite_key=key)
        return self._quote_states[key]

    # ── Backward compatibility aliases ─────────────────────────────────

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Backward-compatible alias for ``quote()``.

        Legacy consumers calling ``broker.market.get_quote()`` continue
        to work while migrating to the new ``quote()`` method.
        """
        return self.quote(symbol, exchange)

    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        """Backward-compatible alias for ``ohlcv()``.

        Legacy consumers calling ``broker.market.get_historical_candles()``
        continue to work while migrating to the new ``ohlcv()`` method.
        """
        return self.ohlcv(
            symbol=symbol,
            exchange=exchange,
            start_time=start_time,
            end_time=end_time,
            resolution=resolution,
        )


class InstrumentHandle:
    """Lightweight handle wrapping an Instrument with market data access.

    Returned by ``MarketDataContext.instrument()``. Provides read-oriented
    operations (quote, depth, history, option_chain, subscribe) by delegating
    to the parent ``MarketDataContext``.

    The underlying ``Instrument`` attributes (``symbol``, ``exchange``,
    ``is_equity()``, …) are accessible via automatic delegation — you can
    use ``handle.symbol``, ``handle.is_equity()``, etc. directly.
    """

    def __init__(self, instrument: Any, context: MarketDataContext) -> None:
        self._instrument = instrument
        self._context = context

    # ── Automatic delegation to Instrument ────────────────────────────

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying Instrument.

        This provides transparent access to all Instrument properties
        (``symbol``, ``exchange``, ``segment``, …) and methods
        (``is_equity()``, ``is_option()``, …) without boilerplate.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._instrument, name)

    # ── Context-backed operations ─────────────────────────────────────

    def quote(self) -> Any:
        """Get current quote for this instrument.

        Delegates to ``MarketDataContext.quote()``.
        """
        return self._context.quote(self.symbol, self.exchange)

    def depth(self) -> Any:
        """Get market depth (order book) for this instrument."""
        return self._context.depth(self.symbol, self.exchange)

    def ohlcv(
        self,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Any]:
        """Fetch historical OHLCV candles for this instrument."""
        return self._context.ohlcv(
            symbol=self.symbol,
            exchange=self.exchange,
            start_time=start_time,
            end_time=end_time,
            resolution=resolution,
        )

    def option_chain(self, expiry: str | None = None) -> Any:
        """Get option chain for this instrument (derivatives only)."""
        return self._context.option_chain(
            underlying=self.symbol,
            exchange=self.exchange,
            expiry=expiry,
        )

    def subscribe(self, callback: Callable[[Any], Any]) -> Any:
        """Subscribe to live market data for this instrument."""
        return self._context.subscribe(self.symbol, self.exchange, callback)

    def unsubscribe(self) -> None:
        """Unsubscribe from live market data for this instrument."""
        self._context.unsubscribe(self.symbol, self.exchange)

    def quote_state(self) -> QuoteState:
        """Get mutable quote state for this instrument (auto-updated by streaming).

        When streaming is active, this state is automatically updated with
        each tick. Provides real-time access to LTP, bid, ask, volume, etc.
        without polling the broker API.
        """
        return self._context.quote_state(self.symbol, self.exchange)

    def snapshot(self) -> Any:
        """Return an immutable snapshot of current quote state.

        Equivalent to calling ``self.quote()``.
        """
        return self.quote()

    def __repr__(self) -> str:
        return f"InstrumentHandle({self._instrument!r})"


class SimpleStreamHandle:
    """Minimal StreamHandle implementation for unsubscription (legacy path)."""

    def __init__(self, streaming: StreamingPort, symbols: list[str], exchange: str) -> None:
        self._streaming = streaming
        self._symbols = symbols
        self._exchange = exchange
        self._disconnected = False

    def disconnect(self) -> None:
        if self._disconnected:
            return
        self._disconnected = True
        import asyncio

        async def _unsubscribe() -> None:
            await self._streaming.unsubscribe_quotes(self._symbols, self._exchange)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_unsubscribe())
            else:
                loop.run_until_complete(_unsubscribe())
        except RuntimeError:
            asyncio.run(_unsubscribe())

    @property
    def is_connected(self) -> bool:
        return not self._disconnected and self._streaming.is_connected


class SimpleSubscriptionHandle:
    """StreamHandle returned when using SubscriptionManager (new path).

    Delegates unsubscription to the SubscriptionManager's reference counting.
    """

    def __init__(
        self,
        manager: SubscriptionManager,
        key: str,
        exchange: str,
        callback: Callable[[Any], None] | None = None,
    ) -> None:
        self._manager = manager
        self._key = key
        self._exchange = exchange
        self._callback = callback
        self._disconnected = False

    def disconnect(self) -> None:
        if self._disconnected:
            return
        self._disconnected = True
        self._manager.unsubscribe(
            key=self._key,
            exchange=self._exchange,
            callback=self._callback,
        )

    @property
    def is_connected(self) -> bool:
        return not self._disconnected
