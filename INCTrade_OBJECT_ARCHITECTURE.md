# INC Trade — Object-Centric Architecture

## Vision

**Instruments are the system.** Every stock, future, option, and index is a living object that knows how to fetch its own quotes, historical data, subscribe to live feeds, and compose into chains. Brokers are injected behaviors, not gateways.

---

## Core Principles

1. **Instrument = Object** — Rich objects with state + behavior, not passive data bags
2. **No Gateway** — Instruments talk to brokers directly via injected adapters
3. **Composition over Inheritance** — Options chains compose instruments, not inherit from them
4. **Decoration for Extensions** — Broker-specific features (depth 20/200) wrap instruments
5. **Protocol-based Adapters** — Structural typing, not concrete imports

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│  (Trading strategies, scanners, portfolio management)        │
├─────────────────────────────────────────────────────────────┤
│                    Instrument Layer                          │
│  Equity, Future, Option, Index, OptionChain                  │
│  (Rich objects with behavior: quote(), subscribe(), etc.)    │
├─────────────────────────────────────────────────────────────┤
│                    Adapter Layer                             │
│  DhanAdapter, UpstoxAdapter, PaperAdapter                    │
│  (Implement protocols, inject into instruments)              │
├─────────────────────────────────────────────────────────────┤
│                    Domain Layer                              │
│  Quote, Candle, OrderRequest, Order, Position, etc.          │
│  (Immutable value objects, zero dependencies)                │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Instrument Objects

### Base Instrument

```python
# inc_trade/instruments/base.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Protocol, runtime_checkable

from inc_trade.domain.entities import Candle, Quote, MarketDepth
from inc_trade.domain.enums import Side, OrderType


# ── Protocols (what instruments need from adapters) ──────────────────────

@runtime_checkable
class QuoteProvider(Protocol):
    """Can fetch quotes for an instrument."""
    def quote(self, symbol: str, exchange: str) -> Quote: ...
    def ltp(self, symbol: str, exchange: str) -> Decimal: ...

@runtime_checkable
class HistoricalProvider(Protocol):
    """Can fetch historical candles for an instrument."""
    def candles(
        self, symbol: str, exchange: str,
        start: datetime, end: datetime, resolution: str
    ) -> list[Candle]: ...

@runtime_checkable
class DepthProvider(Protocol):
    """Can fetch market depth for an instrument."""
    def depth(self, symbol: str, exchange: str, levels: int = 5) -> MarketDepth: ...

@runtime_checkable
class StreamProvider(Protocol):
    """Can subscribe to live ticks for an instrument."""
    def subscribe(self, symbol: str, exchange: str, callback: Callable[[Quote], None]) -> str: ...
    def unsubscribe(self, subscription_id: str) -> None: ...

@runtime_checkable
class OrderProvider(Protocol):
    """Can place/modify/cancel orders."""
    def place_order(self, **kwargs: Any) -> Any: ...
    def modify_order(self, order_id: str, **kwargs: Any) -> Any: ...
    def cancel_order(self, order_id: str) -> Any: ...

@runtime_checkable
class OptionsProvider(Protocol):
    """Can fetch option chains and expiries."""
    def expiries(self, underlying: str, exchange: str) -> list[str]: ...
    def option_chain(self, underlying: str, exchange: str, expiry: str) -> Any: ...


# ── Observer Protocol ────────────────────────────────────────────────────

class QuoteObserver(Protocol):
    """Receives quote updates from an instrument."""
    def on_quote(self, instrument: Instrument, quote: Quote) -> None: ...


# ── Base Instrument ──────────────────────────────────────────────────────

@dataclass(frozen=True, kw_only=True)
class Instrument(ABC):
    """Base class for all tradable instruments.

    An instrument is a rich object that knows how to:
    - Fetch its own quotes (current price, depth)
    - Fetch historical data (candles, OHLCV)
    - Subscribe to live streaming updates
    - Place orders (buy/sell)
    - Compose into chains (options -> underlying)

    Adapters are injected, not imported.
    """

    symbol: str
    exchange: str
    name: str = ""
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")

    # Injected providers (not part of equality/hashing)
    _quote_provider: QuoteProvider | None = field(default=None, repr=False)
    _historical_provider: HistoricalProvider | None = field(default=None, repr=False)
    _depth_provider: DepthProvider | None = field(default=None, repr=False)
    _stream_provider: StreamProvider | None = field(default=None, repr=False)
    _order_provider: OrderProvider | None = field(default=None, repr=False)
    _options_provider: OptionsProvider | None = field(default=None, repr=False)

    # Observer pattern
    _observers: list[QuoteObserver] = field(default_factory=list, repr=False)

    # ── Quote Methods ────────────────────────────────────────────────────

    def quote(self) -> Quote:
        """Fetch current quote for this instrument."""
        if self._quote_provider is None:
            raise RuntimeError(f"No quote provider configured for {self.symbol}")
        return self._quote_provider.quote(self.symbol, self.exchange)

    def ltp(self) -> Decimal:
        """Fetch last traded price."""
        if self._quote_provider is None:
            raise RuntimeError(f"No quote provider configured for {self.symbol}")
        return self._quote_provider.ltp(self.symbol, self.exchange)

    def depth(self, levels: int = 5) -> MarketDepth:
        """Fetch market depth."""
        if self._depth_provider is None:
            raise RuntimeError(f"No depth provider configured for {self.symbol}")
        return self._depth_provider.depth(self.symbol, self.exchange, levels)

    # ── Historical Methods ───────────────────────────────────────────────

    def candles(
        self,
        start: datetime,
        end: datetime | None = None,
        resolution: str = "1D",
    ) -> list[Candle]:
        """Fetch historical candles.

        Args:
            start: Start datetime
            end: End datetime (defaults to now)
            resolution: '1', '5', '15', '60', '1D', '1W', '1M'
        """
        if self._historical_provider is None:
            raise RuntimeError(f"No historical provider for {self.symbol}")
        if end is None:
            end = datetime.now()
        return self._historical_provider.candles(
            self.symbol, self.exchange, start, end, resolution
        )

    def ohlcv(
        self,
        days: int = 30,
        resolution: str = "1D",
    ) -> list[Candle]:
        """Convenience: fetch last N days of candles."""
        end = datetime.now()
        start = end - timedelta(days=days)
        return self.candles(start, end, resolution)

    # ── Streaming Methods ────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[Quote], None]) -> str:
        """Subscribe to live ticks. Returns subscription ID."""
        if self._stream_provider is None:
            raise RuntimeError(f"No stream provider for {self.symbol}")
        return self._stream_provider.subscribe(
            self.symbol, self.exchange, callback
        )

    def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from live ticks."""
        if self._stream_provider is None:
            return
        self._stream_provider.unsubscribe(subscription_id)

    def attach(self, observer: QuoteObserver) -> None:
        """Add a quote observer."""
        self._observers.append(observer)

    def detach(self, observer: QuoteObserver) -> None:
        """Remove a quote observer."""
        self._observers.remove(observer)

    def _notify_observers(self, quote: Quote) -> None:
        """Notify all observers of a new quote."""
        for observer in self._observers:
            try:
                observer.on_quote(self, quote)
            except Exception:
                pass  # Isolated failure

    # ── Order Methods ────────────────────────────────────────────────────

    def buy(
        self,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> Any:
        """Place a buy order for this instrument."""
        if self._order_provider is None:
            raise RuntimeError(f"No order provider for {self.symbol}")
        return self._order_provider.place_order(
            symbol=self.symbol,
            exchange=self.exchange,
            side=Side.BUY,
            quantity=quantity,
            order_type=order_type,
            price=price,
            trigger_price=trigger_price,
            **kwargs,
        )

    def sell(
        self,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> Any:
        """Place a sell order for this instrument."""
        if self._order_provider is None:
            raise RuntimeError(f"No order provider for {self.symbol}")
        return self._order_provider.place_order(
            symbol=self.symbol,
            exchange=self.exchange,
            side=Side.SELL,
            quantity=quantity,
            order_type=order_type,
            price=price,
            trigger_price=trigger_price,
            **kwargs,
        )

    # ── Identity ─────────────────────────────────────────────────────────

    @property
    def key(self) -> str:
        """Unique identifier: EXCHANGE:SYMBOL"""
        return f"{self.exchange}:{self.symbol}"

    def __hash__(self) -> int:
        return hash((self.symbol, self.exchange))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Instrument):
            return NotImplemented
        return self.symbol == other.symbol and self.exchange == other.exchange


# ── Instrument Types ─────────────────────────────────────────────────────

@dataclass(frozen=True, kw_only=True)
class Equity(Instrument):
    """Equity stock (e.g., RELIANCE, TCS)."""
    isin: str = ""

    def fundamentals(self) -> dict[str, Any]:
        """Fetch fundamental data (P/E, market cap, etc.)."""
        # Delegate to extension if available
        return {}


@dataclass(frozen=True, kw_only=True)
class Future(Instrument):
    """Futures contract."""
    expiry: datetime | None = None
    underlying: str = ""

    @property
    def is_expired(self) -> bool:
        if self.expiry is None:
            return False
        return datetime.now() > self.expiry

    def basis(self, spot_price: Decimal) -> Decimal:
        """Calculate basis (futures price - spot)."""
        return self.ltp() - spot_price


@dataclass(frozen=True, kw_only=True)
class Option(Instrument):
    """Option contract (call or put)."""
    expiry: datetime | None = None
    strike: Decimal = Decimal("0")
    option_type: str = ""  # "CE" or "PE"
    underlying: str = ""

    @property
    def is_call(self) -> bool:
        return self.option_type == "CE"

    @property
    def is_put(self) -> bool:
        return self.option_type == "PE"

    @property
    def is_itm(self) -> bool:
        """Check if option is in-the-money."""
        spot = self.ltp()
        if self.is_call:
            return spot > self.strike
        return spot < self.strike

    @property
    def is_otm(self) -> bool:
        """Check if option is out-of-the-money."""
        return not self.is_itm

    def option_chain(self, expiry: str | None = None) -> OptionChain:
        """Fetch option chain for the underlying."""
        if self._options_provider is None:
            raise RuntimeError(f"No options provider for {self.symbol}")
        return OptionChain(
            provider=self._options_provider,
            underlying=self.underlying or self.symbol,
            exchange=self.exchange,
            expiry=expiry,
        )


@dataclass(frozen=True, kw_only=True)
class Index(Instrument):
    """Market index (e.g., NIFTY, BANKNIFTY)."""
    pass
```

---

## 2. OptionChain as Composition

```python
# inc_trade/instruments/option_chain.py

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from inc_trade.domain.entities import OptionLeg, OptionStrike


@dataclass
class OptionChain:
    """Option chain — a composition of Option instruments.

    The chain fetches data from the provider and exposes it as
    a navigable structure of Option objects.
    """

    provider: Any  # OptionsProvider
    underlying: str
    exchange: str = "NFO"
    expiry: str | None = None

    # Cached state
    _data: Any = field(default=None, repr=False)
    _options: dict[str, Option] = field(default_factory=dict, repr=False)

    def _ensure_loaded(self) -> None:
        """Lazy-load the option chain data."""
        if self._data is None:
            self._data = self.provider.option_chain(
                self.underlying, self.exchange, self.expiry
            )

    @property
    def spot(self) -> Decimal:
        """Current spot price of the underlying."""
        self._ensure_loaded()
        return self._data.spot if self._data else Decimal("0")

    @property
    def expiries(self) -> list[str]:
        """Available expiry dates."""
        return self.provider.expiries(self.underlying, self.exchange)

    @property
    def strikes(self) -> list[OptionStrike]:
        """All strike prices with CE/PE legs."""
        self._ensure_loaded()
        return self._data.strikes if self._data else []

    def get_call(self, strike: Decimal) -> Option | None:
        """Get the Call option at a specific strike."""
        self._ensure_loaded()
        key = f"{strike}:CE"
        if key in self._options:
            return self._options[key]

        for s in self.strikes:
            if s.strike == strike:
                opt = Option(
                    symbol=s.call.symbol,
                    exchange=self.exchange,
                    name=f"{self.underlying} {strike} CE",
                    strike=strike,
                    option_type="CE",
                    underlying=self.underlying,
                    expiry=self._parse_expiry(),
                )
                self._options[key] = opt
                return opt
        return None

    def get_put(self, strike: Decimal) -> Option | None:
        """Get the Put option at a specific strike."""
        self._ensure_loaded()
        key = f"{strike}:PE"
        if key in self._options:
            return self._options[key]

        for s in self.strikes:
            if s.strike == strike:
                opt = Option(
                    symbol=s.put.symbol,
                    exchange=self.exchange,
                    name=f"{self.underlying} {strike} PE",
                    strike=strike,
                    option_type="PE",
                    underlying=self.underlying,
                    expiry=self._parse_expiry(),
                )
                self._options[key] = opt
                return opt
        return None

    def atm(self) -> tuple[Option | None, Option | None]:
        """Get ATM (at-the-money) call and put."""
        spot = self.spot
        if not self.strikes:
            return None, None

        # Find closest strike to spot
        closest = min(self.strikes, key=lambda s: abs(s.strike - spot))
        return self.get_call(closest.strike), self.get_put(closest.strike)

    def chain(self) -> list[dict[str, Any]]:
        """Get full chain as list of rows for display."""
        self._ensure_loaded()
        rows = []
        for strike_data in self.strikes:
            rows.append({
                "strike": strike_data.strike,
                "call_ltp": strike_data.call.ltp,
                "call_oi": strike_data.call.oi,
                "call_vol": strike_data.call.volume,
                "put_ltp": strike_data.put.ltp,
                "put_oi": strike_data.put.oi,
                "put_vol": strike_data.put.volume,
            })
        return rows

    def _parse_expiry(self) -> datetime | None:
        """Parse expiry string to datetime."""
        if self.expiry is None:
            return None
        try:
            return datetime.strptime(self.expiry, "%Y-%m-%d")
        except ValueError:
            return None
```

---

## 3. Decorator Pattern for Extensions

```python
# inc_trade/instruments/decorators.py

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

from inc_trade.domain.entities import MarketDepth, Quote
from inc_trade.instruments.base import Instrument


class InstrumentDecorator(Instrument):
    """Base decorator for instrument extensions.

    Wraps an instrument and delegates all methods to it,
    allowing subclasses to add behavior.
    """

    def __init__(self, wrapped: Instrument) -> None:
        # Copy all fields from wrapped instrument
        object.__setattr__(self, '_wrapped', wrapped)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._wrapped!r})"


# ── Depth Extension Decorators ──────────────────────────────────────────

@dataclass(frozen=True, kw_only=True)
class Depth20Instrument(InstrumentDecorator):
    """Extension: 20-level market depth (Dhan feature).

    Wraps an instrument to add 20-level depth support.
    """

    def depth(self, levels: int = 20) -> MarketDepth:
        """Fetch 20-level market depth."""
        # Dhan-specific implementation
        if self._wrapped._depth_provider is None:
            raise RuntimeError(f"No depth provider for {self.symbol}")
        return self._wrapped._depth_provider.depth(
            self.symbol, self.exchange, levels
        )

    @property
    def supported_depth_levels(self) -> int:
        return 20


@dataclass(frozen=True, kw_only=True)
class Depth200Instrument(InstrumentDecorator):
    """Extension: 200-level market depth (Dhan feature).

    Wraps an instrument to add 200-level depth support.
    """

    def depth(self, levels: int = 200) -> MarketDepth:
        """Fetch 200-level market depth."""
        if self._wrapped._depth_provider is None:
            raise RuntimeError(f"No depth provider for {self.symbol}")
        return self._wrapped._depth_provider.depth(
            self.symbol, self.exchange, levels
        )

    @property
    def supported_depth_levels(self) -> int:
        return 200


@dataclass(frozen=True, kw_only=True)
class Depth30Instrument(InstrumentDecorator):
    """Extension: 30-level market depth (Upstox feature).

    Wraps an instrument to add 30-level depth support.
    """

    def depth(self, levels: int = 30) -> MarketDepth:
        """Fetch 30-level market depth."""
        if self._wrapped._depth_provider is None:
            raise RuntimeError(f"No depth provider for {self.symbol}")
        return self._wrapped._depth_provider.depth(
            self.symbol, self.exchange, levels
        )

    @property
    def supported_depth_levels(self) -> int:
        return 30


# ── Caching Decorator ───────────────────────────────────────────────────

@dataclass(frozen=True, kw_only=True)
class CachedInstrument(InstrumentDecorator):
    """Extension: Caches quotes for a configurable TTL.

    Wraps an instrument to add quote caching.
    """

    cache_ttl_seconds: float = 2.0
    _cache: dict[str, Any] = field(default_factory=dict, repr=False)

    def quote(self) -> Quote:
        """Fetch quote with caching."""
        cache_key = f"quote:{self.symbol}:{self.exchange}"
        now = __import__('time').time()

        if cache_key in self._cache:
            cached_time, cached_quote = self._cache[cache_key]
            if now - cached_time < self.cache_ttl_seconds:
                return cached_quote

        quote = super().quote()
        self._cache[cache_key] = (now, quote)
        return quote


# ── Logging Decorator ───────────────────────────────────────────────────

@dataclass(frozen=True, kw_only=True)
class LoggedInstrument(InstrumentDecorator):
    """Extension: Logs all method calls for debugging.

    Wraps an instrument to add logging.
    """

    def quote(self) -> Quote:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Fetching quote for {self.symbol}:{self.exchange}")
        result = super().quote()
        logger.info(f"Quote for {self.symbol}: LTP={result.ltp}")
        return result

    def buy(self, quantity: int, **kwargs: Any) -> Any:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Buying {quantity} of {self.symbol}")
        return super().buy(quantity, **kwargs)

    def sell(self, quantity: int, **kwargs: Any) -> Any:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Selling {quantity} of {self.symbol}")
        return super().sell(quantity, **kwargs)


# ── Composition Helper ──────────────────────────────────────────────────

def with_depth(instrument: Instrument, levels: int) -> Instrument:
    """Add depth extension to an instrument.

    Factory function that selects the right decorator based on levels.
    """
    if levels <= 5:
        return instrument  # Base depth, no wrapper needed
    elif levels <= 20:
        return Depth20Instrument(wrapped=instrument)
    elif levels <= 30:
        return Depth30Instrument(wrapped=instrument)
    elif levels <= 200:
        return Depth200Instrument(wrapped=instrument)
    else:
        raise ValueError(f"Unsupported depth levels: {levels}")


def with_cache(instrument: Instrument, ttl: float = 2.0) -> Instrument:
    """Add caching to an instrument."""
    return CachedInstrument(wrapped=instrument, cache_ttl_seconds=ttl)


def with_logging(instrument: Instrument) -> Instrument:
    """Add logging to an instrument."""
    return LoggedInstrument(wrapped=instrument)
```

---

## 4. Broker Adapters (No Gateway)

```python
# inc_trade/adapters/base.py

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from inc_trade.domain.entities import (
    Candle, MarketDepth, Order, OrderResponse, Position, Quote
)
from inc_trade.domain.enums import Side, OrderType
from inc_trade.instruments.base import (
    HistoricalProvider, OrderProvider, QuoteProvider, DepthProvider,
    StreamProvider, OptionsProvider
)


class BrokerAdapter(ABC):
    """Base class for broker adapters.

    Each adapter implements the provider protocols and can be
    injected into instruments.
    """

    @property
    @abstractmethod
    def broker_id(self) -> str:
        """Unique broker identifier (e.g., 'dhan', 'upstox')."""
        ...

    @abstractmethod
    def connect(self, **credentials: Any) -> None:
        """Establish connection to the broker."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the broker."""
        ...


# ── Dhan Adapter ────────────────────────────────────────────────────────

class DhanAdapter(BrokerAdapter):
    """Dhan broker adapter.

    Implements all provider protocols for Dhan-specific API.
    """

    def __init__(self, client_id: str, access_token: str) -> None:
        self._client_id = client_id
        self._access_token = access_token
        self._client = None

    @property
    def broker_id(self) -> str:
        return "dhan"

    def connect(self, **credentials: Any) -> None:
        # Initialize Dhan API client
        self._client = self._create_client(
            client_id=credentials.get("client_id", self._client_id),
            access_token=credentials.get("access_token", self._access_token),
        )

    def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    # ── QuoteProvider ────────────────────────────────────────────────

    def quote(self, symbol: str, exchange: str) -> Quote:
        """Fetch quote from Dhan API."""
        # Dhan-specific implementation
        response = self._client.get_quote(symbol, exchange)
        return Quote(
            symbol=symbol,
            exchange=exchange,
            ltp=Decimal(str(response["ltp"])),
            open=Decimal(str(response["open"])),
            high=Decimal(str(response["high"])),
            low=Decimal(str(response["low"])),
            close=Decimal(str(response["close"])),
            volume=response["volume"],
        )

    def ltp(self, symbol: str, exchange: str) -> Decimal:
        """Fetch LTP from Dhan API."""
        response = self._client.get_ltp(symbol, exchange)
        return Decimal(str(response["ltp"]))

    # ── DepthProvider ────────────────────────────────────────────────

    def depth(self, symbol: str, exchange: str, levels: int = 5) -> MarketDepth:
        """Fetch market depth from Dhan API.

        Dhan supports up to 200 levels.
        """
        if levels > 200:
            raise ValueError(f"Dhan supports max 200 depth levels, got {levels}")

        response = self._client.get_depth(symbol, exchange, levels)
        bids = [
            DepthLevel(
                price=Decimal(str(b["price"])),
                quantity=b["quantity"],
                orders=b.get("orders", 0),
            )
            for b in response.get("bids", [])
        ]
        asks = [
            DepthLevel(
                price=Decimal(str(a["price"])),
                quantity=a["quantity"],
                orders=a.get("orders", 0),
            )
            for a in response.get("asks", [])
        ]
        return MarketDepth(symbol=symbol, bids=bids, asks=asks, exchange=exchange)

    # ── HistoricalProvider ──────────────────────────────────────────

    def candles(
        self, symbol: str, exchange: str,
        start: datetime, end: datetime, resolution: str
    ) -> list[Candle]:
        """Fetch historical candles from Dhan API."""
        response = self._client.get_candles(symbol, exchange, start, end, resolution)
        return [
            Candle(
                symbol=symbol,
                timestamp=datetime.fromisoformat(c["timestamp"]),
                open=Decimal(str(c["open"])),
                high=Decimal(str(c["high"])),
                low=Decimal(str(c["low"])),
                close=Decimal(str(c["close"])),
                volume=c["volume"],
            )
            for c in response
        ]

    # ── StreamProvider ──────────────────────────────────────────────

    def subscribe(
        self, symbol: str, exchange: str, callback: Callable[[Quote], None]
    ) -> str:
        """Subscribe to live ticks from Dhan WebSocket."""
        # Dhan-specific WebSocket subscription
        return self._client.subscribe(symbol, exchange, callback)

    def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from live ticks."""
        self._client.unsubscribe(subscription_id)

    # ── OrderProvider ───────────────────────────────────────────────

    def place_order(self, **kwargs: Any) -> OrderResponse:
        """Place order via Dhan API."""
        # Dhan-specific order placement
        response = self._client.place_order(**kwargs)
        return OrderResponse(
            order_id=response["order_id"],
            success=response["success"],
            message=response.get("message", ""),
        )

    def modify_order(self, order_id: str, **kwargs: Any) -> OrderResponse:
        """Modify order via Dhan API."""
        response = self._client.modify_order(order_id, **kwargs)
        return OrderResponse(
            order_id=order_id,
            success=response["success"],
            message=response.get("message", ""),
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel order via Dhan API."""
        response = self._client.cancel_order(order_id)
        return OrderResponse(
            order_id=order_id,
            success=response["success"],
            message=response.get("message", ""),
        )

    # ── OptionsProvider ─────────────────────────────────────────────

    def expiries(self, underlying: str, exchange: str) -> list[str]:
        """Get available option expiries."""
        return self._client.get_expiries(underlying, exchange)

    def option_chain(self, underlying: str, exchange: str, expiry: str) -> Any:
        """Get option chain."""
        return self._client.get_option_chain(underlying, exchange, expiry)

    # ── Factory Method ──────────────────────────────────────────────

    def instrument(
        self,
        symbol: str,
        exchange: str,
        instrument_type: str = "equity",
        **kwargs: Any,
    ) -> Instrument:
        """Create an instrument with this adapter's providers injected."""
        from inc_trade.instruments.factory import InstrumentFactory

        return InstrumentFactory.create(
            symbol=symbol,
            exchange=exchange,
            instrument_type=instrument_type,
            quote_provider=self,
            historical_provider=self,
            depth_provider=self,
            stream_provider=self,
            order_provider=self,
            options_provider=self,
            **kwargs,
        )


# ── Upstox Adapter ──────────────────────────────────────────────────────

class UpstoxAdapter(BrokerAdapter):
    """Upstox broker adapter.

    Upstox supports up to 30 depth levels.
    """

    def __init__(self, access_token: str) -> None:
        self._access_token = access_token
        self._client = None

    @property
    def broker_id(self) -> str:
        return "upstox"

    def connect(self, **credentials: Any) -> None:
        self._client = self._create_client(
            access_token=credentials.get("access_token", self._access_token),
        )

    def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def depth(self, symbol: str, exchange: str, levels: int = 5) -> MarketDepth:
        """Fetch market depth from Upstox API.

        Upstox supports up to 30 levels.
        """
        if levels > 30:
            raise ValueError(f"Upstox supports max 30 depth levels, got {levels}")

        # Upstox-specific implementation
        ...

    def instrument(
        self,
        symbol: str,
        exchange: str,
        instrument_type: str = "equity",
        **kwargs: Any,
    ) -> Instrument:
        """Create an instrument with this adapter's providers injected."""
        from inc_trade.instruments.factory import InstrumentFactory

        return InstrumentFactory.create(
            symbol=symbol,
            exchange=exchange,
            instrument_type=instrument_type,
            quote_provider=self,
            historical_provider=self,
            depth_provider=self,
            stream_provider=self,
            order_provider=self,
            options_provider=self,
            **kwargs,
        )
```

---

## 5. Instrument Factory

```python
# inc_trade/instruments/factory.py

from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Any

from inc_trade.instruments.base import (
    Equity, Future, Index, Instrument, Option,
    QuoteProvider, HistoricalProvider, DepthProvider,
    StreamProvider, OrderProvider, OptionsProvider
)


class InstrumentFactory:
    """Creates instrument instances with providers injected.

    Usage::

        # With a broker adapter
        adapter = DhanAdapter(client_id="123", access_token="abc")
        adapter.connect()

        # Create instruments
        reliance = adapter.instrument("RELIANCE", "NSE")
        nifty = adapter.instrument("NIFTY", "NSE", instrument_type="index")

        # Or use factory directly
        reliance = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            instrument_type="equity",
            quote_provider=adapter,
            historical_provider=adapter,
        )

        # Use the instrument
        quote = reliance.quote()
        candles = reliance.ohlcv(days=30)
        reliance.buy(quantity=10)
    """

    @staticmethod
    def create(
        symbol: str,
        exchange: str,
        instrument_type: str = "equity",
        quote_provider: QuoteProvider | None = None,
        historical_provider: HistoricalProvider | None = None,
        depth_provider: DepthProvider | None = None,
        stream_provider: StreamProvider | None = None,
        order_provider: OrderProvider | None = None,
        options_provider: OptionsProvider | None = None,
        **kwargs: Any,
    ) -> Instrument:
        """Create an instrument based on type.

        Args:
            symbol: Trading symbol
            exchange: Exchange code (NSE, BSE, NFO, etc.)
            instrument_type: 'equity', 'future', 'option', 'index'
            quote_provider: Provider for quotes
            historical_provider: Provider for historical data
            depth_provider: Provider for market depth
            stream_provider: Provider for live streaming
            order_provider: Provider for order placement
            options_provider: Provider for options data
            **kwargs: Additional fields for the instrument
        """
        common = {
            "symbol": symbol,
            "exchange": exchange,
            "name": kwargs.pop("name", ""),
            "lot_size": kwargs.pop("lot_size", 1),
            "tick_size": kwargs.pop("tick_size", Decimal("0.05")),
            "_quote_provider": quote_provider,
            "_historical_provider": historical_provider,
            "_depth_provider": depth_provider,
            "_stream_provider": stream_provider,
            "_order_provider": order_provider,
            "_options_provider": options_provider,
        }

        instrument_type = instrument_type.lower()

        if instrument_type == "equity":
            return Equity(
                **common,
                isin=kwargs.pop("isin", ""),
            )
        elif instrument_type == "future":
            return Future(
                **common,
                expiry=kwargs.pop("expiry", None),
                underlying=kwargs.pop("underlying", ""),
            )
        elif instrument_type == "option":
            return Option(
                **common,
                expiry=kwargs.pop("expiry", None),
                strike=kwargs.pop("strike", Decimal("0")),
                option_type=kwargs.pop("option_type", ""),
                underlying=kwargs.pop("underlying", ""),
            )
        elif instrument_type == "index":
            return Index(**common)
        else:
            raise ValueError(f"Unknown instrument type: {instrument_type}")

    @staticmethod
    def from_adapter(
        adapter: Any,
        symbol: str,
        exchange: str,
        instrument_type: str = "equity",
        **kwargs: Any,
    ) -> Instrument:
        """Create instrument from a broker adapter.

        Convenience method that extracts providers from the adapter.
        """
        return adapter.instrument(symbol, exchange, instrument_type, **kwargs)
```

---

## 6. Usage Examples

```python
# Example 1: Basic Usage

from inc_trade.adapters.dhan import DhanAdapter
from inc_trade.instruments.base import Equity
from inc_trade.instruments.decorators import with_depth, with_cache

# Create adapter and connect
adapter = DhanAdapter(client_id="123", access_token="abc")
adapter.connect()

# Create instrument with providers injected
reliance = adapter.instrument("RELIANCE", "NSE")

# Fetch data
quote = reliance.quote()
print(f"RELIANCE LTP: {quote.ltp}")

candles = reliance.ohlcv(days=30, resolution="1D")
print(f"Fetched {len(candles)} candles")

# Place order
response = reliance.buy(quantity=10)
print(f"Order placed: {response.order_id}")


# Example 2: Adding Extensions via Decoration

# Add 200-level depth support (Dhan feature)
reliance_200 = with_depth(reliance, levels=200)
depth = reliance_200.depth(levels=200)
print(f"Got {len(depth.bids)} bid levels")

# Add caching
reliance_cached = with_cache(reliance, ttl=5.0)
quote1 = reliance_cached.quote()  # Fetches from API
quote2 = reliance_cached.quote()  # Returns cached


# Example 3: Options Chain as Composition

from inc_trade.instruments.option_chain import OptionChain

# Create option chain
chain = OptionChain(
    provider=adapter,
    underlying="NIFTY",
    exchange="NFO",
    expiry="2024-01-25",
)

# Navigate the chain
print(f"Spot: {chain.spot}")
print(f"Expiries: {chain.expiries}")

# Get ATM options
call, put = chain.atm()
if call:
    print(f"ATM Call: {call.symbol} LTP={call.ltp()}")
if put:
    print(f"ATM Put: {put.symbol} LTP={put.ltp()}")

# Get specific strike
ce_24000 = chain.get_call(Decimal("24000"))
if ce_20000:
    print(f"24000 CE: {ce_24000.symbol}")


# Example 4: Streaming with Observer Pattern

from inc_trade.instruments.base import QuoteObserver

class PriceAlert(QuoteObserver):
    def __init__(self, instrument: Instrument, target: Decimal):
        self.instrument = instrument
        self.target = target

    def on_quote(self, instrument: Instrument, quote: Quote) -> None:
        if quote.ltp >= self.target:
            print(f"ALERT: {instrument.symbol} hit {quote.ltp}!")

# Set up streaming
reliance = adapter.instrument("RELIANCE", "NSE")
alert = PriceAlert(reliance, target=Decimal("2500"))
reliance.attach(alert)

# Subscribe to live ticks
sub_id = reliance.subscribe(callback=lambda q: print(f"LTP: {q.ltp}"))


# Example 5: Multi-Broker with Decorator Composition

from inc_trade.adapters.upstox import UpstoxAdapter

# Create instruments from different brokers
dhan = DhanAdapter(client_id="123", access_token="abc")
upstox = UpstoxAdapter(access_token="xyz")

reliance_dhan = dhan.instrument("RELIANCE", "NSE")
reliance_upstox = upstox.instrument("RELIANCE", "NSE")

# Compare quotes
quote_dhan = reliance_dhan.quote()
quote_upstox = reliance_upstox.quote()

print(f"Dhan: {quote_dhan.ltp}, Upstox: {quote_upstox.ltp}")


# Example 6: Strategy using Instruments

class MomentumStrategy:
    def __init__(self, instrument: Instrument, lookback: int = 20):
        self.instrument = instrument
        self.lookback = lookback

    def should_buy(self) -> bool:
        """Buy if price is above 20-day high."""
        candles = self.instrument.ohlcv(days=self.lookback)
        if not candles:
            return False

        high_20d = max(c.high for c in candles)
        current = self.instrument.ltp()

        return current > high_20d

    def execute(self) -> None:
        if self.should_buy():
            self.instrument.buy(quantity=10)
            print(f"Bought 10 of {self.instrument.symbol}")


# Run strategy
strategy = MomentumStrategy(reliance)
strategy.execute()
```

---

## 7. Key Design Patterns

| Pattern | Where Used | Purpose |
|---------|------------|---------|
| **Decorator** | `Depth20Instrument`, `CachedInstrument` | Add behavior without modifying base |
| **Composition** | `OptionChain` composes `Option` objects | Options chain as collection of instruments |
| **Strategy** | Provider protocols | Swap broker implementations |
| **Observer** | `QuoteObserver` | Reactive streaming updates |
| **Factory** | `InstrumentFactory` | Create correct instrument type |
| **Protocol** | All providers | Structural typing, no concrete deps |
| **Immutable** | All instruments | Thread-safe, hashable |

---

## 8. Migration Path

1. **Phase 1**: Create `inc_trade/instruments/` package with base classes
2. **Phase 2**: Implement `DhanAdapter` and `UpstoxAdapter`
3. **Phase 3**: Add decorator extensions (depth, cache, logging)
4. **Phase 4**: Implement `OptionChain` composition
5. **Phase 5**: Migrate existing code to use instrument objects
6. **Phase 6**: Remove gateway pattern (old `BrokerGateway`)

---

## 9. Benefits

| Before (Gateway) | After (Object-Centric) |
|-------------------|------------------------|
| `gateway.market_data.quote("RELIANCE", "NSE")` | `instrument.quote()` |
| `gateway.historical.get_candles(...)` | `instrument.ohlcv(days=30)` |
| `gateway.streaming.subscribe(...)` | `instrument.subscribe(callback)` |
| `extension_registry.resolve("dhan", MarginProvider)` | `instrument.margin()` (via decorator) |
| Scattered broker-specific code | Self-contained instrument objects |
| Tight coupling to gateway | Loose coupling via protocols |

---

## 10. Future Extensions

- **Margin Calculator**: `instrument.margin(quantity=10, side=Side.BUY)`
- **Greeks**: `option.greeks()` returns Delta, Gamma, Theta, Vega
- **Implied Volatility**: `option.iv()` returns current IV
- **P&L Calculator**: `position.pnl()` returns current P&L
- **Risk Metrics**: `portfolio.var(confidence=0.95)` returns VaR
- **Backtesting**: `instrument.backtest(strategy, start, end)` runs backtest
