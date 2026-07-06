"""MarketDataQuery — query side of CQS for read-only market data operations.

Splits Instrument's query responsibilities into a dedicated application
service, enabling clean CQS separation while maintaining backward
compatibility through Instrument convenience delegates.

Usage::

    query = MarketDataQuery(instrument, provider=adapter)
    ltp = query.ltp()
    depth = query.depth(200)
    chain = query.option_chain("2025-01-30")
    handle = query.subscribe(on_quote)
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from inc_trade.domain.entities import Candle, MarketDepth, Quote
    from inc_trade.market.instrument import Instrument
    from inc_trade.ports.event_publisher import EventPublisherPort
    from inc_trade.ports.providers import (
        DepthProvider,
        HistoricalDataProvider,
        InstrumentDataProvider,
        StreamingDataProvider,
    )

logger = logging.getLogger(__name__)


class MarketDataQuery:
    """Read-only market data operations for an instrument.

    Pure query side of CQS. Every method is idempotent and
    side-effect-free. No system state is modified.

    Resolves providers in this order:
    1. Explicitly passed provider (highest priority)
    2. Instrument's ``_provider`` (attached by factory)
    3. Instrument's ``_context`` (legacy fallback)

    When ``event_publisher`` is provided, streaming ticks automatically
    publish ``QuoteTickEvent`` to the event bus.

    Args:
        instrument: The target Instrument.
        provider: ``InstrumentDataProvider`` for quote/LTP/depth.
        depth_provider: ``DepthProvider`` for extended depth.
        historical_provider: ``HistoricalDataProvider`` for candles.
        streaming_provider: ``StreamingDataProvider`` for live ticks.
        event_publisher: Optional ``EventPublisherPort`` for domain events.
        context: Legacy ``MarketDataContext`` fallback.
    """

    def __init__(
        self,
        instrument: Instrument,
        provider: InstrumentDataProvider | None = None,
        depth_provider: DepthProvider | None = None,
        historical_provider: HistoricalDataProvider | None = None,
        streaming_provider: StreamingDataProvider | None = None,
        event_publisher: EventPublisherPort | None = None,
        context: Any = None,
    ) -> None:
        self._instrument = instrument
        self._provider = provider
        self._depth_provider = depth_provider
        self._historical_provider = historical_provider
        self._streaming_provider = streaming_provider
        self._event_publisher = event_publisher
        self._context = context

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _resolve_provider(self) -> InstrumentDataProvider:
        """Resolve the primary data provider."""
        if self._provider is not None:
            return self._provider
        inst = self._instrument
        if inst._provider is not None:  # type: ignore[attr-defined]
            return inst._provider  # type: ignore[attr-defined]
        raise RuntimeError(
            f"No data provider for {inst.composite_key}. "
            "Set provider via constructor or instrument.with_providers()."
        )

    def _resolve_depth_provider(self) -> Any:
        """Resolve the depth provider."""
        if self._depth_provider is not None:
            return self._depth_provider
        inst = self._instrument
        if inst._depth_provider is not None:  # type: ignore[attr-defined]
            return inst._depth_provider  # type: ignore[attr-defined]
        return self._resolve_provider()

    def _resolve_historical_provider(self) -> Any:
        """Resolve the historical data provider."""
        if self._historical_provider is not None:
            return self._historical_provider
        inst = self._instrument
        if inst._historical_provider is not None:  # type: ignore[attr-defined]
            return inst._historical_provider  # type: ignore[attr-defined]
        return self._resolve_provider()

    def _resolve_streaming_provider(self) -> Any:
        """Resolve the streaming provider."""
        if self._streaming_provider is not None:
            return self._streaming_provider
        inst = self._instrument
        if inst._streaming_provider is not None:  # type: ignore[attr-defined]
            return inst._streaming_provider  # type: ignore[attr-defined]
        raise RuntimeError(f"No streaming provider for {self._instrument.composite_key}.")

    def _legacy_context(self) -> Any:
        """Resolve legacy MarketDataContext fallback."""
        ctx = self._context
        if ctx is not None:
            return ctx
        inst = self._instrument
        if inst._context is not None:  # type: ignore[attr-defined]
            return inst._context  # type: ignore[attr-defined]
        raise RuntimeError(
            f"No market data context for {self._instrument.composite_key}. "
            "Obtain instruments via broker.market.instrument()."
        )

    def _publish_quote_event(self, quote: Any) -> None:
        """Publish a QuoteTickEvent if event_publisher is configured."""
        if self._event_publisher is None:
            return
        try:
            from inc_trade.domain.events import QuoteTickEvent

            event = QuoteTickEvent(
                composite_key=self._instrument.composite_key,
                symbol=self._instrument.symbol,
                exchange=self._instrument.exchange,
                ltp=Decimal(str(getattr(quote, "ltp", "0") or "0")),
                bid=Decimal(str(getattr(quote, "bid", "0") or "0")),
                ask=Decimal(str(getattr(quote, "ask", "0") or "0")),
                volume=int(getattr(quote, "volume", 0) or 0),
                oi=int(getattr(quote, "oi", 0) or 0),
                source=getattr(self._streaming_provider, "broker_id", "unknown"),
            )
            self._event_publisher.publish(event)
        except Exception as exc:
            logger.warning("quote_event_publish_failed: %s", exc)

    # ── Public API ──────────────────────────────────────────────────────────

    def quote(self) -> Any:
        """Get current quote for this instrument.

        Returns:
            ``Quote`` domain entity from the provider/adapter.
        """
        try:
            provider = self._resolve_provider()
            return provider.quote(
                self._instrument.symbol,
                self._instrument.exchange,
            )
        except RuntimeError:
            return self._legacy_context().quote(
                self._instrument.symbol,
                self._instrument.exchange,
            )

    def ltp(self) -> Decimal:
        """Get last traded price for this instrument.

        Returns:
            ``Decimal`` LTP value.
        """
        try:
            provider = self._resolve_provider()
            return provider.ltp(
                self._instrument.symbol,
                self._instrument.exchange,
            )
        except RuntimeError:
            return self._legacy_context().ltp(
                self._instrument.symbol,
                self._instrument.exchange,
            )

    def depth(self, levels: int = 5) -> Any:
        """Get market depth (order book) for this instrument.

        Args:
            levels: Number of depth levels requested (default 5).

        Returns:
            ``MarketDepth`` domain entity.
        """
        try:
            provider = self._resolve_depth_provider()
            return provider.depth(
                self._instrument.symbol,
                self._instrument.exchange,
                levels,
            )
        except RuntimeError:
            return self._legacy_context().depth(
                self._instrument.symbol,
                self._instrument.exchange,
                levels,
            )

    def ohlcv(
        self,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Any]:
        """Fetch historical OHLCV candles for this instrument.

        Args:
            start_time: Start of time range.
            end_time: End of time range.
            resolution: Candle resolution (e.g., '1', '5', '15', '60', '1D').

        Returns:
            List of ``Candle`` domain entities.
        """
        try:
            provider = self._resolve_historical_provider()
            return provider.get_candles(
                symbol=self._instrument.symbol,
                exchange=self._instrument.exchange,
                start_time=start_time,
                end_time=end_time,
                resolution=resolution,
            )
        except RuntimeError:
            return self._legacy_context().ohlcv(
                symbol=self._instrument.symbol,
                exchange=self._instrument.exchange,
                start_time=start_time,
                end_time=end_time,
                resolution=resolution,
            )

    def history(
        self,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Any]:
        """Alias for ``ohlcv()``."""
        return self.ohlcv(start_time, end_time, resolution)

    def option_chain(self, expiry: str | None = None) -> Any:
        """Get option chain for this instrument (derivatives only).

        Args:
            expiry: Expiry date string (e.g., '2025-01-30'). If None,
                returns the chain for the nearest expiry.

        Returns:
            ``OptionChain`` or ``InstrumentOptionChain`` domain entity.
        """
        return self._legacy_context().option_chain(
            underlying=self._instrument.symbol,
            exchange=self._instrument.exchange,
            expiry=expiry,
        )

    def subscribe(self, callback: Callable[[Any], Any]) -> Any:
        """Subscribe to live market data for this instrument.

        When ``event_publisher`` is configured, each tick publishes a
        ``QuoteTickEvent`` on the event bus before calling the user callback.

        Args:
            callback: Callable invoked with each new Quote tick.

        Returns:
            StreamHandle for controlling the subscription.
        """
        sp = self._resolve_streaming_provider()

        # Wrap callback to publish events if configured
        if self._event_publisher is not None:
            user_callback = callback

            def event_wrapper(quote: Any) -> None:
                self._publish_quote_event(quote)
                user_callback(quote)

            return sp.subscribe(self._instrument, event_wrapper)

        return sp.subscribe(self._instrument, callback)

    def unsubscribe(self) -> None:
        """Unsubscribe from live market data for this instrument."""
        sp = self._resolve_streaming_provider()
        sp.unsubscribe(self._instrument)

    def snapshot(self) -> Any:
        """Return an immutable snapshot of current quote.

        Equivalent to ``self.quote()``.
        """
        return self.quote()

    @property
    def instrument(self) -> Any:
        """The instrument this query is bound to."""
        return self._instrument
