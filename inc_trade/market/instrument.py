"""Instrument domain entity — the primary abstraction of the platform.

The Instrument is the center of the architecture (Instrument-Centric Design).
Traders think in instruments. Strategies reference instruments.
Risk models operate on instrument portfolios. Broker APIs are implementation details.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

from inc_trade.domain.entities import AggregatedExposure, Position

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Instrument:
    """Canonical domain entity — a single tradeable instrument.

    This is the primary abstraction of the platform. Every operation in
    the system (quoting, trading, analysis) revolves around an Instrument.

    Attributes:
        symbol: Trading symbol (e.g., "RELIANCE", "NIFTY").
        exchange: Exchange code (e.g., "NSE", "BSE", "NFO").
        segment: Market segment. Free-form string; type detection is
            content-based (see :meth:`is_equity`, :meth:`is_future`,
            :meth:`is_option`, :meth:`is_index`) and does not depend on
            the segment value. Each adapter may store its broker-specific
            segment code here.
        name: Human-readable instrument name.
        lot_size: Minimum tradeable quantity.
        tick_size: Minimum price increment.
        isin: International Securities Identification Number.
        expiry: Expiry date for derivatives (None for equity).
        strike: Strike price for options (None for equity/futures).
        option_type: "CE" for calls, "PE" for puts, None for equity/futures.
    """

    symbol: str
    exchange: str
    segment: str = ""
    name: str = ""
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    isin: str = ""
    expiry: datetime | None = None
    strike: Decimal | None = None
    option_type: str | None = None

    # Canonical exchange codes for derivative exchanges (imply F&O).
    _DERIVATIVE_EXCHANGES: ClassVar[set[str]] = {"NFO", "BFO", "CDS", "BCD"}
    # Option type markers (CE = Call European, PE = Put European).
    _OPTION_SUFFIXES: ClassVar[set[str]] = {"CE", "PE"}

    @property
    def composite_key(self) -> str:
        """Unique identifier: ``{exchange}:{symbol}``."""
        return f"{self.exchange}:{self.symbol}"

    def display_name(self) -> str:
        """Human-readable name for display purposes."""
        if self.option_type and self.strike is not None:
            return f"{self.exchange}:{self.symbol} {self.strike} {self.option_type}"
        return self.composite_key

    def is_equity(self) -> bool:
        """Check if this is an equity (stock) instrument.

        Detection is content-based: an instrument is equity if it has
        no option_type, no expiry, no strike, and is not on a
        derivative exchange (NFO/BFO/CDS/BCD). This works regardless
        of the broker-specific ``segment`` value.
        """
        if self.option_type is not None:
            return False
        if self.expiry is not None:
            return False
        if self.strike is not None:
            return False
        if self.exchange in self._DERIVATIVE_EXCHANGES:
            return False
        return True

    def is_future(self) -> bool:
        """Check if this is a futures instrument.

        Detection: instrument is on a derivative exchange and has an
        expiry but no strike and no option_type.
        """
        if self.option_type is not None:
            return False
        if self.strike is not None:
            return False
        return self.expiry is not None and self.exchange in self._DERIVATIVE_EXCHANGES

    def is_option(self) -> bool:
        """Check if this is an options instrument.

        Detection: instrument has an option_type and a strike.
        """
        return self.option_type in self._OPTION_SUFFIXES and self.strike is not None

    def is_index(self) -> bool:
        """Check if this is an index instrument.

        Detection: instrument is on NSE or BSE (equity exchanges) but
        has no ``isin`` (index instruments are not ISIN-assigned).
        Index detection is heuristic — for precise detection, use
        ``brokers.config.indices.is_index(symbol)``.
        """
        # Indices typically trade on equity exchanges with no ISIN.
        return self.exchange in ("NSE", "BSE") and not self.isin and self.is_equity()

    def is_call(self) -> bool:
        """Check if this is a call option."""
        return self.option_type == "CE"

    def is_put(self) -> bool:
        """Check if this is a put option."""
        return self.option_type == "PE"

    def is_expired(self, as_of: datetime | None = None) -> bool:
        """Check if the instrument has expired (derivatives only)."""
        if self.expiry is None:
            return False
        check_time = as_of or datetime.now(UTC)
        return self.expiry < check_time

    def days_to_expiry(self, as_of: datetime | None = None) -> int | None:
        """Calendar days to expiry. ``None`` for non-derivatives.

        Args:
            as_of: Reference time (default: now UTC).

        Returns:
            Number of calendar days, or ``None`` for non-derivatives.
        """
        if self.expiry is None:
            return None
        check_time = as_of or datetime.now(UTC)
        # Normalize to date comparison
        if check_time.tzinfo is None:
            check_dt = check_time
        else:
            check_dt = check_time.replace(tzinfo=None) if self.expiry.tzinfo is None else check_time
        exp_date = self.expiry.date() if hasattr(self.expiry, "date") else self.expiry
        check_date = check_dt.date() if hasattr(check_dt, "date") else check_dt
        return (exp_date - check_date).days

    def is_expiring_soon(
        self,
        threshold_days: int = 7,
        as_of: datetime | None = None,
    ) -> bool:
        """Check if the instrument expires within ``threshold_days``.

        Args:
            threshold_days: Number of days for the warning threshold.
            as_of: Reference time (default: now UTC).

        Returns:
            True if derivative and expiry is within threshold.
            False for non-derivatives or further-out expiries.
        """
        days = self.days_to_expiry(as_of)
        if days is None:
            return False
        return 0 <= days <= threshold_days

    def validate_price(self, price: Decimal) -> bool:
        """Check that price is a valid multiple of tick_size.

        Returns:
            True if price is valid (positive and aligned to tick_size).
        """
        if price <= 0:
            return False
        if self.tick_size <= 0:
            return True  # No tick size constraint
        return price % self.tick_size == 0

    def validate_quantity(self, quantity: int) -> bool:
        """Check that quantity is a valid multiple of lot_size.

        Returns:
            True if quantity is positive and aligned to lot_size.
        """
        if quantity <= 0:
            return False
        if self.lot_size <= 0:
            return True  # No lot size constraint
        return quantity % self.lot_size == 0

    def aggregate_positions(
        self,
        positions: Sequence[Position],
    ) -> AggregatedExposure:
        """Filter and aggregate positions belonging to this instrument.

        A position belongs to this instrument when its ``(symbol, exchange)``
        matches ``self``. The function is pure: it does not mutate inputs
        and performs no I/O.

        Conventions for the Position quantity:
            - Positive quantity contributes to ``long_quantity``.
            - Negative quantity contributes its absolute value to
              ``short_quantity``.

        Args:
            positions: Sequence of Position entities (any exchange/symbol).

        Returns:
            AggregatedExposure summarising all positions matching this
            instrument. If none match, returns a zero-exposure result
            tagged with this instrument's ``(symbol, exchange)``.
        """
        long_qty = 0
        short_qty = 0
        count = 0
        for pos in positions:
            if pos.symbol != self.symbol or pos.exchange != self.exchange:
                continue
            count += 1
            if pos.quantity > 0:
                long_qty += pos.quantity
            elif pos.quantity < 0:
                short_qty += -pos.quantity
            # pos.quantity == 0 contributes nothing to long/short but is counted
        return AggregatedExposure(
            symbol=self.symbol,
            exchange=self.exchange,
            net_quantity=long_qty - short_qty,
            gross_quantity=long_qty + short_qty,
            long_quantity=long_qty,
            short_quantity=short_qty,
            position_count=count,
        )

    # ── Market Data Context (Instrument-Centric Access) ─────────────────
    #
    # ``_context`` (and its backward-compat alias ``_delegate_context``) is
    # set by ``MarketDataContext.instrument()`` or ``InstrumentFactory``
    # via ``object.__setattr__`` after construction.  This maintains the
    # frozen dataclass contract while enabling ``instrument.quote()``,
    # ``instrument.depth()``, etc. directly on the domain entity.
    #
    # ``_extensions`` is a dict of arbitrary extension data attached by
    # the factory or an adapter (e.g., fundamentals, broker metadata).
    #
    # These are intentionally NOT dataclass fields (no type annotation + no
    # ``field()``) so that they do not participate in ``__init__``,
    # ``__eq__``, or ``__hash__``.

    _delegate_context = None  # type: ignore  # set externally (backward compat)
    _context = None  # type: ignore  # canonical name, set externally
    _extensions: dict | None = None  # type: ignore  # set externally

    # ── Rich Instrument attributes (Phase 3) ──────────────────────────
    # Set via object.__setattr__ by InstrumentFactory or BrokerSession.
    # These enable the provider-injection pattern: instruments own their
    # data providers instead of delegating to an external context.
    _provider = None  # type: ignore  # InstrumentDataProvider protocol
    _historical_provider = None  # type: ignore  # HistoricalDataProvider protocol
    _streaming_provider = None  # type: ignore  # StreamingDataProvider protocol
    _depth_provider = None  # type: ignore  # DepthProvider protocol
    _order_provider = None  # type: ignore  # OrderProvider protocol
    _quote_state_obj = None  # type: ignore  # QuoteState instance
    _observers: list | None = None  # type: ignore  # list[QuoteObserver]
    _capabilities = None  # type: ignore  # InstrumentCapabilities

    # ── Delegate accessors (Instrument-Centric) ─────────────────────────

    def quote(self) -> Any:
        """Get current quote for this instrument.

        Checks ``_provider`` first (rich instrument path), falls back to
        ``_context`` (legacy path).

        Raises:
            RuntimeError: If neither provider nor context is available.
        """
        if self._provider is not None:
            return self._provider.quote(self.symbol, self.exchange)
        ctx = self._context or self._delegate_context
        if ctx is None:
            raise RuntimeError(
                "Instrument has no market data context. "
                "Obtain instruments via broker.market.instrument()"
            )
        return ctx.quote(self.symbol, self.exchange)

    def ltp(self) -> Decimal:
        """Get last traded price for this instrument."""
        if self._provider is not None:
            return self._provider.ltp(self.symbol, self.exchange)
        ctx = self._context or self._delegate_context
        if ctx is None:
            raise RuntimeError(
                "Instrument has no market data context. "
                "Obtain instruments via broker.market.instrument()"
            )
        return ctx.ltp(self.symbol, self.exchange)

    def depth(self, levels: int = 5) -> Any:
        """Get market depth (order book) for this instrument.

        Checks ``_depth_provider`` first (dedicated depth provider), then
        ``_provider`` (general provider), then ``_context`` (legacy path).

        Args:
            levels: Number of depth levels requested (default 5).
        """
        dp = self._depth_provider
        if dp is not None:
            return dp.depth(self.symbol, self.exchange, levels)
        if self._provider is not None:
            return self._provider.depth(self.symbol, self.exchange, levels)
        ctx = self._context or self._delegate_context
        if ctx is None:
            raise RuntimeError(
                "Instrument has no market data context. "
                "Obtain instruments via broker.market.instrument()"
            )
        return ctx.depth(self.symbol, self.exchange)

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
            List of Candle domain entities.
        """
        hp = self._historical_provider
        if hp is not None:
            return hp.get_candles(
                symbol=self.symbol,
                exchange=self.exchange,
                start_time=start_time,
                end_time=end_time,
                resolution=resolution,
            )
        ctx = self._context or self._delegate_context
        if ctx is None:
            raise RuntimeError(
                "Instrument has no market data context. "
                "Obtain instruments via broker.market.instrument()"
            )
        return ctx.ohlcv(
            symbol=self.symbol,
            exchange=self.exchange,
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
            OptionChain domain entity.
        """
        ctx = self._context or self._delegate_context
        if ctx is None:
            raise RuntimeError(
                "Instrument has no market data context. "
                "Obtain instruments via broker.market.instrument()"
            )
        return ctx.option_chain(
            underlying=self.symbol,
            exchange=self.exchange,
            expiry=expiry,
        )

    def subscribe(self, callback: Callable[[Any], Any]) -> Any:
        """Subscribe to live market data for this instrument.

        Args:
            callback: Callable invoked with each new Quote tick.

        Returns:
            StreamHandle for controlling the subscription.
        """
        sp = self._streaming_provider
        if sp is not None:
            return sp.subscribe(self, callback)
        ctx = self._context or self._delegate_context
        if ctx is None:
            raise RuntimeError(
                "Instrument has no market data context. "
                "Obtain instruments via broker.market.instrument()"
            )
        return ctx.subscribe(self.symbol, self.exchange, callback)

    def unsubscribe(self) -> None:
        """Unsubscribe from live market data for this instrument."""
        sp = self._streaming_provider
        if sp is not None:
            sp.unsubscribe(self)
            return
        ctx = self._context or self._delegate_context
        if ctx is None:
            raise RuntimeError(
                "Instrument has no market data context. "
                "Obtain instruments via broker.market.instrument()"
            )
        ctx.unsubscribe(self.symbol, self.exchange)

    def quote_state(self) -> Any:
        """Get mutable quote state for this instrument (auto-updated by
        streaming).

        When streaming is active, this state is automatically updated with
        each tick. Provides real-time access to LTP, bid, ask, volume, etc.
        without polling the broker API.
        """
        if self._quote_state_obj is not None:
            return self._quote_state_obj
        ctx = self._context or self._delegate_context
        if ctx is None:
            raise RuntimeError(
                "Instrument has no market data context. "
                "Obtain instruments via broker.market.instrument()"
            )
        return ctx.quote_state(self.symbol, self.exchange)

    def snapshot(self) -> Any:
        """Return an immutable snapshot of current quote state.

        Equivalent to ``self.quote()``.
        """
        return self.quote()

    # ── Observer Pattern (Phase 3) ──────────────────────────────────────

    def attach(self, observer: Any) -> None:
        """Attach a QuoteObserver to this instrument.

        The observer's ``on_quote(instrument, quote)`` method will be
        called on every tick after provider update.

        Args:
            observer: Object implementing QuoteObserver protocol.
        """
        if self._observers is None:
            object.__setattr__(self, "_observers", [])
        if observer not in self._observers:
            self._observers.append(observer)

    def detach(self, observer: Any) -> None:
        """Detach a QuoteObserver from this instrument.

        Args:
            observer: Previously attached observer.
        """
        if self._observers:
            try:
                self._observers.remove(observer)
            except ValueError:
                pass

    def _notify_observers(self, quote: Any) -> None:
        """Notify all attached observers of a new quote.

        Each observer is isolated — one failing observer does not block
        others. Slow observers (>1ms) are logged as warnings.
        """
        import time

        for obs in self._observers or []:
            try:
                t0 = time.monotonic()
                obs.on_quote(self, quote)
                elapsed = time.monotonic() - t0
                if elapsed > 0.001:  # 1ms threshold
                    logger.warning(
                        "slow_observer: %s took %.2fms for %s",
                        type(obs).__name__,
                        elapsed * 1000,
                        self.composite_key,
                    )
            except Exception as exc:
                logger.warning("observer_error: %s: %s", type(obs).__name__, exc)

    # ── Order Methods (Instrument-Centric Trading) ────────────────────────

    def buy(
        self,
        quantity: int,
        order_type: Any = None,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> Any:
        """Place a buy order for this instrument.

        Delegates to the injected order provider (``_order_provider``) or
        falls back to the general provider (``_provider``) if the dedicated
        order provider is not set.

        Args:
            quantity: Number of units to buy.
            order_type: ``OrderType`` enum value (default: ``OrderType.MARKET``).
            price: Limit price (required for LIMIT orders).
            trigger_price: Trigger price (required for STOP_LOSS orders).
            **kwargs: Additional broker-specific order parameters.

        Returns:
            ``OrderResponse`` from the broker adapter.

        Raises:
            RuntimeError: If no order provider is configured.
        """
        from inc_trade.domain.enums import OrderType as OT

        provider = self._order_provider or self._provider
        if provider is None:
            raise RuntimeError(
                f"No order provider configured for {self.composite_key}. "
                "Obtain instruments via broker.market.instrument() or "
                "set _order_provider."
            )
        return provider.place_order(
            symbol=self.symbol,
            exchange=self.exchange,
            side="BUY",
            quantity=quantity,
            order_type=order_type or OT.MARKET,
            price=price,
            trigger_price=trigger_price,
            **kwargs,
        )

    def sell(
        self,
        quantity: int,
        order_type: Any = None,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> Any:
        """Place a sell order for this instrument.

        Args:
            quantity: Number of units to sell.
            order_type: ``OrderType`` enum value (default: ``OrderType.MARKET``).
            price: Limit price (required for LIMIT orders).
            trigger_price: Trigger price (required for STOP_LOSS orders).
            **kwargs: Additional broker-specific order parameters.

        Returns:
            ``OrderResponse`` from the broker adapter.

        Raises:
            RuntimeError: If no order provider is configured.
        """
        from inc_trade.domain.enums import OrderType as OT

        provider = self._order_provider or self._provider
        if provider is None:
            raise RuntimeError(
                f"No order provider configured for {self.composite_key}. "
                "Obtain instruments via broker.market.instrument() or "
                "set _order_provider."
            )
        return provider.place_order(
            symbol=self.symbol,
            exchange=self.exchange,
            side="SELL",
            quantity=quantity,
            order_type=order_type or OT.MARKET,
            price=price,
            trigger_price=trigger_price,
            **kwargs,
        )

    # ── Capabilities (Phase 3) ──────────────────────────────────────────

    def capabilities(self) -> Any:
        """Get instrument capabilities (supported depth levels, features).

        Returns:
            InstrumentCapabilities or None if not set.
        """
        return self._capabilities

    def supports_depth(self, levels: int) -> bool:
        """Check if this instrument supports a specific depth level.

        Args:
            levels: Depth level to check (e.g., 5, 20, 30, 200).

        Returns:
            True if supported, False otherwise.
        """
        caps = self._capabilities
        if caps is not None:
            return caps.supports_depth(levels)
        return levels <= 5  # Default: only 5-level depth assumed

    # ── Extension Data  ─────────────────────────────────────────────────

    def _extension(self, name: str) -> Any:
        """Look up extension data attached by the factory or adapter.

        Args:
            name: Extension key (e.g., ``"fundamentals"``).

        Returns:
            The extension value, or ``None`` if not present.
        """
        if self._extensions is None:
            return None
        return self._extensions.get(name)

    # ── Lightweight convenience accessors (Instrument-Centric) ──────────

    def oi(self) -> int:
        """Open interest for derivatives. 0 for equity.

        Reads from ``QuoteState.oi`` which is auto-updated by streaming.
        """
        try:
            state = self.quote_state()
            return int(getattr(state, "oi", 0) or 0)
        except Exception:
            return 0

    def metadata(self) -> dict[str, Any]:
        """Return static metadata for this instrument.

        Includes symbol, exchange, segment, name, lot_size, tick_size,
        isin, expiry, strike, option_type.
        """
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "segment": self.segment,
            "name": self.name,
            "lot_size": self.lot_size,
            "tick_size": self.tick_size,
            "isin": self.isin,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "strike": self.strike,
            "option_type": self.option_type,
        }

    def market_status(self) -> str:
        """Return current market status.

        Uses the underlying quote's timestamp to infer status:
        - ``"closed"`` — no quote or very stale
        - ``"open"`` — fresh quote
        - ``"unknown"`` — otherwise

        For precise status, override via a broker-specific extension.
        """
        try:
            state = self.quote_state()
        except Exception:
            return "unknown"
        if state is None or state.timestamp is None:
            return "unknown"
        if state.is_stale(max_age_seconds=300):
            return "closed"
        return "open"

    def greeks(self) -> dict[str, Any]:
        """Greeks for option instruments. Empty dict for non-options.

        Reads from cached ``QuoteState`` if available. For full
        Greeks coverage use ``GreeksCalculator`` on ``OptionLeg`` data
        from the option chain.
        """
        if not self.is_option():
            return {}
        try:
            state = self.quote_state()
        except Exception:
            return {}
        return {
            "iv": None,
            "delta": None,
            "theta": None,
            "gamma": None,
            "vega": None,
            "ltp": state.ltp,
            "oi": state.oi,
            "volume": state.volume,
        }
