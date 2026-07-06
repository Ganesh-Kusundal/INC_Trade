"""BrokerSession — single entry point for an authenticated broker connection.

A BrokerSession represents ONE authenticated connection to ONE broker.
It owns the lifecycle of the adapter, instrument registry, query/command
factories, and event bus.

Usage::

    session = BrokerSession(adapter)
    await session.connect()

    # Get instruments
    rel = session.equity("RELIANCE")
    nifty = session.future("NIFTY", expiry=datetime(2025, 6, 26))

    # Query market data
    query = session.query(rel)
    ltp = query.ltp()

    # Place orders
    cmd = session.command(rel)
    result = cmd.buy(quantity=10)

    # Subscribe to live data
    handle = query.subscribe(on_quote_callback)

    # Cleanup
    await session.disconnect()
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from inc_trade.infrastructure.event_bus import EventBus
from inc_trade.market.instrument_registry import InstrumentRegistry
from inc_trade.market.order import OrderCommand
from inc_trade.market.query import MarketDataQuery

logger = logging.getLogger(__name__)


class MarketDataQueryFactory:
    """Creates MarketDataQuery instances with shared infrastructure.

    Wires the event bus, streaming provider, and depth provider
    into every query automatically.
    """

    def __init__(
        self,
        registry: InstrumentRegistry,
        adapter: Any,
        event_bus: EventBus | None = None,
    ) -> None:
        self._registry = registry
        self._adapter = adapter
        self._event_bus = event_bus

    def create(self, instrument: Instrument) -> MarketDataQuery:
        """Create a MarketDataQuery for the given instrument.

        The query inherits the adapter's providers and event bus.
        Adapter is passed directly — MarketDataQuery's resolution logic
        will attempt to call the adapter methods. If the adapter doesn't
        implement a method, it falls back to instrument._provider or
        _context (legacy path).
        """
        return MarketDataQuery(
            instrument=instrument,
            provider=self._adapter,
            depth_provider=self._adapter,
            historical_provider=self._adapter,
            streaming_provider=self._adapter,
            event_publisher=self._event_bus,
        )


class OrderCommandFactory:
    """Creates OrderCommand instances with shared infrastructure."""

    def __init__(
        self,
        registry: InstrumentRegistry,
        adapter: Any,
        event_bus: EventBus | None = None,
    ) -> None:
        self._registry = registry
        self._adapter = adapter
        self._event_bus = event_bus

    def create(self, instrument: Instrument) -> OrderCommand:
        """Create an OrderCommand for the given instrument."""
        return OrderCommand(
            instrument=instrument,
            order_provider=self._adapter,
            event_publisher=self._event_bus,
        )


class BrokerSession:
    """A single authenticated broker session.

    Manages the lifecycle of adapters, instrument identity,
    CQS query/command factories, and the event bus.

    Args:
        adapter: A ``BrokerAdapter`` implementation.
    """

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self._registry = InstrumentRegistry()
        self._event_bus = EventBus()
        self._query_factory = MarketDataQueryFactory(self._registry, adapter, self._event_bus)
        self._command_factory = OrderCommandFactory(self._registry, adapter, self._event_bus)

    # ── Connection Lifecycle ─────────────────────────────────────────────────

    async def connect(self) -> None:
        """Authenticate and establish connections to the broker.

        Idempotent: if the adapter is already connected, this is a no-op.
        Handles both sync and async adapters: calls the connect function,
        then awaits the result if it's awaitable.
        """
        if getattr(self._adapter, "is_connected", False):
            logger.debug(
                "Session already connected: %s", getattr(self._adapter, "broker_id", "unknown")
            )
            return
        import inspect

        connect_fn = getattr(self._adapter, "connect", None)
        if connect_fn is not None:
            result = connect_fn()
            if inspect.isawaitable(result):
                await result
        logger.info("Session connected: %s", getattr(self._adapter, "broker_id", "unknown"))

    async def disconnect(self) -> None:
        """Close all connections and release resources.

        Handles both sync and async adapters.
        """
        import inspect

        disconnect_fn = getattr(self._adapter, "disconnect", None)
        if disconnect_fn is not None:
            result = disconnect_fn()
            if inspect.isawaitable(result):
                await result
        self._registry.clear()
        logger.info("Session disconnected: %s", getattr(self._adapter, "broker_id", "unknown"))

    @property
    def is_connected(self) -> bool:
        """Check if the session is currently connected."""
        return bool(getattr(self._adapter, "is_connected", False))

    @property
    def adapter(self) -> Any:
        """The underlying broker adapter."""
        return self._adapter

    @property
    def registry(self) -> InstrumentRegistry:
        """The instrument identity registry."""
        return self._registry

    @property
    def event_bus(self) -> EventBus:
        """The session event bus for domain events."""
        return self._event_bus

    # ── Instrument Access ─────────────────────────────────────────────────────

    def equity(self, symbol: str, exchange: str = "NSE") -> Instrument:
        """Get or create an Equity instrument.

        Guarantees the same object for the same ``(symbol, exchange)``.

        Args:
            symbol: Trading symbol (e.g., ``"RELIANCE"``).
            exchange: Exchange code (e.g., ``"NSE"``).

        Returns:
            An Instrument with type detection for equity.
        """
        from inc_trade.market.instrument import Instrument

        key = f"{exchange}:{symbol}"

        def factory() -> Instrument:
            inst = Instrument(symbol=symbol, exchange=exchange)
            return inst

        return self._registry.get_or_create(key, factory)

    def future(
        self,
        symbol: str,
        expiry: datetime,
        exchange: str = "NFO",
    ) -> Instrument:
        """Get or create a Future instrument.

        Args:
            symbol: Underlying symbol (e.g., ``"NIFTY"``).
            expiry: Expiry date.
            exchange: Exchange code (default: ``"NFO"``).

        Returns:
            An Instrument with type detection for future.
        """
        from inc_trade.market.instrument import Instrument

        expiry_date = expiry.date() if hasattr(expiry, "date") else expiry
        key = f"{exchange}:{symbol}:{expiry_date}"

        def factory() -> Instrument:
            return Instrument(
                symbol=symbol,
                exchange=exchange,
                expiry=expiry,
                lot_size=1,
                tick_size=Decimal("0.05"),
            )

        return self._registry.get_or_create(key, factory)

    def option(
        self,
        symbol: str,
        expiry: datetime,
        strike: Decimal,
        option_type: str,
        exchange: str = "NFO",
    ) -> Instrument:
        """Get or create an Option instrument.

        Args:
            symbol: Underlying symbol (e.g., ``"NIFTY"``).
            expiry: Expiry date.
            strike: Strike price.
            option_type: ``"CE"`` for call, ``"PE"`` for put.
            exchange: Exchange code (default: ``"NFO"``).

        Returns:
            An Instrument with type detection for option.
        """
        from inc_trade.market.instrument import Instrument

        expiry_date = expiry.date() if hasattr(expiry, "date") else expiry
        key = f"{exchange}:{symbol}:{expiry_date}:{strike}:{option_type}"

        def factory() -> Instrument:
            return Instrument(
                symbol=symbol,
                exchange=exchange,
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                lot_size=1,
                tick_size=Decimal("0.05"),
            )

        return self._registry.get_or_create(key, factory)

    # ── CQS Access ───────────────────────────────────────────────────────────

    def query(self, instrument: Instrument) -> MarketDataQuery:
        """Create a MarketDataQuery for the given instrument.

        The query inherits the adapter's data providers and the event bus.
        Read-only operations only.
        """
        return self._query_factory.create(instrument)

    def command(self, instrument: Instrument) -> OrderCommand:
        """Create an OrderCommand for the given instrument.

        The command inherits the adapter's order provider.
        Write-only operations only.
        """
        return self._command_factory.create(instrument)

    # ── Utility ──────────────────────────────────────────────────────────────

    def search(self, query: str) -> list[Instrument]:
        """Search registered instruments by symbol or name.

        Args:
            query: Search string (case-insensitive).

        Returns:
            List of matching instruments.
        """
        return self._registry.search(query)

    def instruments(self) -> dict[str, Instrument]:
        """Return a snapshot of all registered instruments.

        Returns:
            Dict mapping composite key → Instrument.
        """
        return self._registry.get_all()

    def __repr__(self) -> str:
        adapter_id = getattr(self._adapter, "broker_id", "unknown")
        return f"BrokerSession(adapter={adapter_id}, instruments={len(self._registry)})"
