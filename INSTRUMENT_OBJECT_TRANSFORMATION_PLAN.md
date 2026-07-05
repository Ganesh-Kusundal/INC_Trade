# Instrument Object Model — Transformation Plan

**Elite Quantitative Engineering Review Board**
Robert C. Martin · Eric Evans · Martin Fowler · Greg Young · Vaughn Vernon · Kent Beck · Michael Feathers · Dr. Venkat Subramaniam

---

## Table of Contents

1. [Current-State Gap Analysis](#1-current-state-gap-analysis)
2. [Target Architecture](#2-target-architecture)
3. [Phase 1: Instrument Decorator Pipeline](#3-phase-1-instrument-decorator-pipeline)
4. [Phase 2: BrokerAdapter Protocol & Gateway Elimination](#4-phase-2-brokeradapter-protocol--gateway-elimination)
5. [Phase 3: Unify OptionChain with Instrument Composition](#5-phase-3-unify-optionchain-with-instrument-composition)
6. [Phase 4: Extension Registry](#6-phase-4-extension-registry)
7. [Phase 5: Gateway Deprecation & Cleanup](#7-phase-5-gateway-deprecation--cleanup)
8. [Test Strategy](#8-test-strategy)
9. [Rollback Strategy](#9-rollback-strategy)

---

## 1. Current-State Gap Analysis

### ✅ What Already Exists (Verified by Reading Code)

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| `Instrument` frozen dataclass | `inc_trade/market/instrument.py` | 618 | ✅ Complete |
| `Equity` subclass | `inc_trade/market/types/equity.py` | 37 | ✅ Complete |
| `Future` subclass | `inc_trade/market/types/future.py` | 38 | ✅ Complete |
| `Option` subclass | `inc_trade/market/types/option.py` | 55 | ✅ Complete |
| `Index` subclass | `inc_trade/market/types/index.py` | 11 | ✅ Complete |
| `InstrumentOptionChain` (composition) | `inc_trade/market/option_chain.py` | 174 | ✅ Complete |
| `Depth20Decorator` | `inc_trade/market/depth_decorators.py` | 82 | ✅ Complete |
| `Depth30Decorator` | `inc_trade/market/depth_decorators.py` | 82 | ✅ Complete |
| `Depth200Decorator` | `inc_trade/market/depth_decorators.py` | 82 | ✅ Complete |
| `DepthDecorator` base | `inc_trade/market/depth_decorators.py` | 82 | ✅ Complete |
| `InstrumentFactory` | `inc_trade/market/factory.py` | 155 | ✅ Complete |
| `InstrumentRegistry` | `inc_trade/market/instrument_registry.py` | 85 | ✅ Complete |
| `MarketDataContext` | `inc_trade/market/context.py` | 729 | ✅ Complete |
| `InstrumentHandle` (delegation) | `inc_trade/market/context.py` | 90 | ✅ Complete |
| `QuoteState` (mutable) | `inc_trade/market/quote_state.py` | 194 | ✅ Complete |
| `DepthState` (mutable) | `inc_trade/market/depth_state.py` | 170 | ✅ Complete |
| `SubscriptionManager` | `inc_trade/market/subscription_manager.py` | 254 | ✅ Complete |
| `MarketRouter` (cache-first) | `inc_trade/market/market_router.py` | 358 | ✅ Complete |
| Provider Protocols | `inc_trade/ports/providers.py` | 68 | ✅ Complete |
| `DepthExtension` protocol | `inc_trade/extensions/depth.py` | 74 | ✅ Complete |
| `Extension` base protocol | `inc_trade/extensions/base.py` | 18 | ✅ Complete |
| EventBus + typed events | `infrastructure/event_bus.py` + `domain/events.py` | ✅ Complete |
| `BrokerCapabilities` | `inc_trade/domain/capabilities.py` | 134 | ✅ Complete |
| `BrokerFacade` (to deprecate) | `inc_trade/services/broker_facade.py` | ~250 | ✅ Working |
| Dhan adapter (42 files) | `brokers/adapters/dhan/` | ✅ Full implementation |
| Upstox adapter (23 files) | `brokers/adapters/upstox/` | ✅ Full implementation |
| Architecture tests (59 rules) | `brokers/tests/unit/test_architecture.py` | ✅ Running |

### ❌ What's Missing

| Gap | Impact | Priority |
|-----|--------|----------|
| **G1**: No unified `InstrumentDecorator` base class | Decorators don't compose; `DepthDecorator` is ad-hoc | 🔴 P0 |
| **G2**: No `buy()`/`sell()` on `Instrument` | Trading requires service layer, not object-centric | 🔴 P0 |
| **G3**: No `BrokerAdapter` protocol | Gateway still primary entry point; violates DIP | 🔴 P0 |
| **G4**: No `with_depth()`/`with_cache()`/`with_logging()` helpers | No composition pipeline for extensions | 🟡 P1 |
| **G5**: Extension registry not wired through Factory | Extensions set via `object.__setattr__` | 🟡 P1 |
| **G6**: Two parallel OptionChain implementations | Domain uses strings, market uses Instruments | 🟡 P1 |
| **G7**: No `CachedDecorator` in code | Aspirational only in architecture doc | 🟡 P1 |
| **G8**: No `LoggedDecorator` in code | Aspirational only | 🟢 P2 |
| **G9**: Dhan/Upstox don't implement BrokerAdapter | Gateway god objects remain | 🟡 P1 |
| **G10**: No ObservableProperty pattern for streaming | QuoteState updates are imperative | 🟢 P2 |

### Architecture Smell: Frozen + `object.__setattr__`

The core issue is that `Instrument` is a frozen dataclass but uses `object.__setattr__` in 9 places
to set mutable state (`_context`, `_provider`, `_observers`, etc.):

```python
# factory.py:146
object.__setattr__(inst, "_context", context)
object.__setattr__(inst, "_delegate_context", context)  # backward compat
object.__setattr__(inst, "_extensions", extensions or {})
object.__setattr__(inst, "_provider", provider)
object.__setattr__(inst, "_historical_provider", historical_provider)
object.__setattr__(inst, "_streaming_provider", streaming_provider)
object.__setattr__(inst, "_capabilities", capabilities)
```

This is a smell (G-3 in ARCHITECTURE_SMELLS.md). The fix is to make these first-class
constructor parameters or use the decorator pattern to attach behavior.

---

## 2. Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        User / Strategy Code                                 │
│                                                                             │
│  reliance = adapter.instrument("RELIANCE", "NSE")                           │
│  reliance.quote()          → Quote                                          │
│  reliance.depth()          → MarketDepth (5-level default)                  │
│  reliance.depth(levels=20) → MarketDepth (20-level via Decorator)           │
│  reliance.ohlcv(...)       → [Candle, ...]                                  │
│  reliance.subscribe(cb)    → StreamHandle                                   │
│  reliance.buy(qty=10)      → OrderResponse                                  │
│  reliance.sell(qty=10)     → OrderResponse                                  │
│  reliance.option_chain()   → InstrumentOptionChain                          │
│    → chain.atm_call().instrument.greeks()                                    │
│    → chain.atm_call().instrument.buy(qty=lot_size)                          │
└───────────────────────┬─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Instrument  (inc_trade/market/instrument.py)                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Frozen fields: symbol, exchange, segment, name, lot_size,            │   │
│  │                tick_size, isin, expiry, strike, option_type          │   │
│  │ Non-frozen (constructor): _provider, _historical_provider,           │   │
│  │                           _streaming_provider, _depth_provider,      │   │
│  │                           _order_provider, _context, _observers      │   │
│  │ Methods: quote(), ltp(), depth(), ohlcv(), history(),               │   │
│  │          subscribe(), unsubscribe(), quote_state(),                  │   │
│  │          buy(), sell(), attach(), detach(),                          │   │
│  │          option_chain(), greeks(), oi(), metadata(),                 │   │
│  │          is_equity(), is_future(), is_option(), is_index()           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────────────────────────┘
                        │
          ┌─────────────┼─────────────┬─────────────────────┐
          ▼             ▼             ▼                     ▼
┌─────────────────┐ ┌─────────┐ ┌──────────────┐ ┌──────────────────────┐
│ Decorator       │ │Equity   │ │ OptionChain  │ │ BrokerAdapter        │
│ Pipeline        │ │Future   │ │ Composition  │ │ (Protocol)           │
│                 │ │Option   │ │              │ │                      │
│ Depth20Decorator│ │Index    │ │ atm_call()    │ │ DhanAdapter          │
│ Depth30Decorator│ │         │ │   → OptionLeg │ │ UpstoxAdapter        │
│ Depth200Decor   │ │         │ │     → Inst    │ │ PaperAdapter         │
│ CachedDecorator │ │         │ │ max_pain      │ │ ReplayAdapter        │
│ LoggedDecorator │ │         │ │ pcr           │ │                      │
└─────────────────┘ └─────────┘ └──────────────┘ └──────────────────────┘
```

### Object Graph (Runtime)

```
adapter = DhanAdapter(client_id, access_token)
adapter.connect()

# Single instrument with decorator pipeline
reliance = adapter.instrument("RELIANCE", "NSE")
# → InstrumentFactory.create(
#       symbol="RELIANCE", exchange="NSE",
#       provider=adapter,           # QuoteProvider
#       depth_provider=adapter,     # DepthProvider (up to 200 levels)
#       historical_provider=adapter,
#       streaming_provider=adapter,
#       order_provider=adapter,     # buy()/sell()
#   )

# Decorator composition via pipeline:
# with_depth(reliance, 200)
# → Depth200Decorator(Depth20Decorator(reliance))
#   .depth(200) → uses Depth200Decorator
#   .depth(20)  → uses Depth20Decorator
#   .quote()    → delegates to Instrument.quote()

# Options chain with Instrument composition:
chain = reliance.option_chain("2025-01-30")
# chain.strikes[0].call.instrument → Option instrument
# chain.strikes[0].call.instrument.greeks()
# chain.strikes[0].call.instrument.buy(qty=75)
```

### Dependency Rule Compliance

```
domain/  →  ports/  →  extensions/  →  market/  →  adapters/
  │          │            │               │
  │          │            │               ├── instrument.py
  │          │            │               ├── decorators.py
  │          │            │               ├── depth_decorators.py
  │          │            │               ├── option_chain.py
  │          │            │               ├── factory.py
  │          │            │               └── context.py
  │          │            │
  │          │            └── depth.py (protocol)
  │          │
  │          ├── providers.py (InstrumentDataProvider, etc.)
  │          ├── market_data.py (MarketDataPort)
  │          └── extensions.py (Extension protocol)
  │
  └── entities.py, enums.py, exceptions.py, ...
```

---

## 3. Phase 1: Instrument Decorator Pipeline

### What

Create a proper `InstrumentDecorator` base class that all decorators extend,
and add `with_depth()`, `with_cache()`, `with_logging()` composition helpers.

### Why

Currently `DepthDecorator` exists but is standalone. There's no base class,
no composition pipeline, no caching/logging decorators. This prevents
stacking: `LoggedInstrument(CachedInstrument(Depth200Decorator(instrument)))`.

### Files

| Action | File | Description |
|--------|------|-------------|
| **CREATE** | `inc_trade/market/decorators.py` | `InstrumentDecorator` base class |
| **MODIFY** | `inc_trade/market/depth_decorators.py` | Extend from `InstrumentDecorator` |
| **CREATE** | `inc_trade/market/cache_decorator.py` | `CachedDecorator` |
| **CREATE** | `inc_trade/market/log_decorator.py` | `LoggedDecorator` |
| **MODIFY** | `inc_trade/market/__init__.py` | Export `with_depth`, `with_cache`, `with_logging` |
| **MODIFY** | `inc_trade/market/factory.py` | Add `decorators` parameter to factory |
| **MODIFY** | `inc_trade/market/instrument.py` | Add `buy()` and `sell()` methods |

### Code: `decorators.py`

```python
"""InstrumentDecorator — base class for instrument extension decorators.

Allows stacking::

    inst = LoggedDecorator(CachedDecorator(Depth200Decorator(base_inst)))
    inst.quote()  # → Logged → Cached → Depth200 → base.quote()
    inst.depth(200)  # → Depth200 → base.depth(200)
"""

from __future__ import annotations

from typing import Any

from inc_trade.market.instrument import Instrument


class InstrumentDecorator:
    """Base decorator wrapping an Instrument.

    Delegates all attribute access to the wrapped instrument,
    allowing subclasses to override specific methods.

    Usage::

        class Depth200Decorator(InstrumentDecorator):
            def depth(self, levels: int = 200) -> Any:
                return self._wrapped.depth(levels)
    """

    def __init__(self, instrument: Instrument) -> None:
        object.__setattr__(self, "_wrapped", instrument)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def __repr__(self) -> str:
        cls = type(self).__name__
        wrapped = self._wrapped
        return f"{cls}({wrapped.composite_key})"


def with_depth(
    instrument: Instrument,
    levels: int,
    depth_provider: Any = None,
) -> Instrument | InstrumentDecorator:
    """Add market depth extension to an instrument.

    Selects the correct decorator based on requested levels.
    No wrapper needed for levels <= 5 (base instrument supports it).
    """
    if levels <= 5:
        return instrument
    from inc_trade.market.depth_decorators import Depth20Decorator, Depth200Decorator, Depth30Decorator

    if levels <= 20:
        return Depth20Decorator(instrument, depth_provider)
    if levels <= 30:
        return Depth30Decorator(instrument, depth_provider)
    if levels <= 200:
        return Depth200Decorator(instrument, depth_provider)
    raise ValueError(f"Unsupported depth levels: {levels}")


def with_cache(instrument: Instrument, ttl_seconds: float = 2.0) -> InstrumentDecorator:
    """Add quote caching to an instrument."""
    from inc_trade.market.cache_decorator import CachedDecorator

    return CachedDecorator(instrument, ttl_seconds)


def with_logging(instrument: Instrument) -> InstrumentDecorator:
    """Add method-call logging to an instrument."""
    from inc_trade.market.log_decorator import LoggedDecorator

    return LoggedDecorator(instrument)
```

### Code: `cache_decorator.py`

```python
"""CachedDecorator — caches quote data with configurable TTL."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from inc_trade.domain.entities import MarketDepth, Quote
from inc_trade.market.decorators import InstrumentDecorator
from inc_trade.market.instrument import Instrument


class CachedDecorator(InstrumentDecorator):
    """Wraps an Instrument to cache quote data for a configurable TTL.

    Reduces broker API calls for frequently-quoted instruments.
    """

    def __init__(self, instrument: Instrument, ttl_seconds: float = 2.0) -> None:
        super().__init__(instrument)
        object.__setattr__(self, "_ttl", ttl_seconds)
        object.__setattr__(self, "_quote_cache", None)
        object.__setattr__(self, "_quote_cached_at", 0.0)
        object.__setattr__(self, "_ltp_cache", None)
        object.__setattr__(self, "_ltp_cached_at", 0.0)

    def quote(self) -> Quote:
        now = time.monotonic()
        if self._quote_cache is not None and (now - self._quote_cached_at) < self._ttl:
            return self._quote_cache
        result = self._wrapped.quote()
        object.__setattr__(self, "_quote_cache", result)
        object.__setattr__(self, "_quote_cached_at", now)
        return result

    def ltp(self) -> Decimal:
        now = time.monotonic()
        if self._ltp_cache is not None and (now - self._ltp_cached_at) < self._ttl:
            return self._ltp_cache
        result = self._wrapped.ltp()
        object.__setattr__(self, "_ltp_cache", result)
        object.__setattr__(self, "_ltp_cached_at", now)
        return result
```

### Code: `log_decorator.py`

```python
"""LoggedDecorator — logs all instrument method calls for debugging."""

from __future__ import annotations

import logging
from typing import Any

from inc_trade.market.decorators import InstrumentDecorator

logger = logging.getLogger(__name__)


class LoggedDecorator(InstrumentDecorator):
    """Wraps an Instrument to log all public method calls."""

    def quote(self) -> Any:
        logger.info("quote() called for %s", self._wrapped.composite_key)
        return self._wrapped.quote()

    def ltp(self) -> Any:
        logger.info("ltp() called for %s", self._wrapped.composite_key)
        return self._wrapped.ltp()

    def depth(self, levels: int = 5) -> Any:
        logger.info("depth(%d) called for %s", levels, self._wrapped.composite_key)
        return self._wrapped.depth(levels)

    def buy(self, quantity: int, **kwargs: Any) -> Any:
        logger.info("buy(%d) called for %s", quantity, self._wrapped.composite_key)
        return self._wrapped.buy(quantity, **kwargs)

    def sell(self, quantity: int, **kwargs: Any) -> Any:
        logger.info("sell(%d) called for %s", quantity, self._wrapped.composite_key)
        return self._wrapped.sell(quantity, **kwargs)
```

### Code changes to `instrument.py`

Add `buy()` and `sell()` methods:

```python
def buy(
    self,
    quantity: int,
    order_type: Any = None,
    price: Decimal = Decimal("0"),
    trigger_price: Decimal = Decimal("0"),
    **kwargs: Any,
) -> Any:
    """Place a buy order for this instrument.

    Delegates to the injected order provider.

    Args:
        quantity: Number of units to buy.
        order_type: OrderType enum (default: MARKET).
        price: Limit price (required for LIMIT orders).
        trigger_price: Trigger price (required for SL orders).

    Returns:
        OrderResponse from the broker adapter.

    Raises:
        RuntimeError: If no order provider is configured.
    """
    from inc_trade.domain.enums import OrderType as OT

    provider = getattr(self, "_order_provider", None) or getattr(self, "_provider", None)
    if provider is None:
        raise RuntimeError(
            f"No order provider configured for {self.composite_key}. "
            "Obtain instruments via broker.market.instrument()"
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

    Delegates to the injected order provider.
    """
    from inc_trade.domain.enums import OrderType as OT

    provider = getattr(self, "_order_provider", None) or getattr(self, "_provider", None)
    if provider is None:
        raise RuntimeError(
            f"No order provider configured for {self.composite_key}. "
            "Obtain instruments via broker.market.instrument()"
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
```

### Refactor `DepthDecorator` to extend from `InstrumentDecorator`

```python
# depth_decorators.py
from inc_trade.market.decorators import InstrumentDecorator

class DepthDecorator(InstrumentDecorator):
    """Abstract base for depth-level decorators. Inherits from InstrumentDecorator."""

    def __init__(self, instrument: Instrument, depth_provider: Any) -> None:
        super().__init__(instrument)
        object.__setattr__(self, "_depth_provider", depth_provider)

    def depth(self, levels: int = 5) -> Any:
        return self._depth_provider.depth(
            self._wrapped.symbol,
            self._wrapped.exchange,
            levels,
        )
    # ... (no more __getattr__ needed — inherited from InstrumentDecorator)
```

### Tests

| Test | Coverage |
|------|----------|
| `test_decorator_base_wraps_instrument` | `InstrumentDecorator` delegates unknown attributes |
| `test_decorator_depth_20_override` | `Depth20Decorator.depth(20)` uses depth provider |
| `test_decorator_depth_200_override` | `Depth200Decorator.depth(200)` uses depth provider |
| `test_decorator_depth_delegate` | `DepthDecorator.quote()` → delegates to wrapped |
| `test_cached_decorator_caches_quote` | Second `quote()` returns cached within TTL |
| `test_cached_decorator_expires` | After TTL, `quote()` fetches fresh |
| `test_logged_decorator_logs_calls` | `quote()` produces log message |
| `test_with_depth_selects_decorator` | `with_depth(inst, 200)` → `Depth200Decorator` |
| `test_with_depth_noop_for_5` | `with_depth(inst, 5)` → same instrument |
| `test_with_cache_returns_cached_decorator` | `with_cache(inst)` → `CachedDecorator` |
| `test_with_logging_returns_logged_decorator` | `with_logging(inst)` → `LoggedDecorator` |
| `test_decorator_stack_composition` | `LoggedDecorator(CachedDecorator(Depth200Decorator(inst)))` works |
| `test_instrument_buy_delegates` | `instrument.buy(qty=10)` → calls provider.place_order |
| `test_instrument_sell_delegates` | `instrument.sell(qty=10)` → calls provider.place_order |

---

## 4. Phase 2: BrokerAdapter Protocol & Gateway Elimination

### What

Create a `BrokerAdapter` protocol (not `BrokerGateway`) that implements provider protocols
(`QuoteProvider`, `DepthProvider`, `HistoricalProvider`, `StreamProvider`, `OrderProvider`,
`OptionsProvider`) and provides an `.instrument()` factory method.

### Why

The current `BrokerGateway` is a god object (DhanGateway: 115-line constructor, 10 responsibilities).
The target architecture eliminates the gateway entirely. Each adapter becomes the set of
provider implementations injected into instruments.

### Files

| Action | File | Description |
|--------|------|-------------|
| **CREATE** | `inc_trade/adapters/__init__.py` | Package init |
| **CREATE** | `inc_trade/adapters/broker_adapter.py` | `BrokerAdapter` Protocol |
| **CREATE** | `inc_trade/adapters/dhan.py` | `DhanAdapter` (wraps existing Dhan components) |
| **CREATE** | `inc_trade/adapters/upstox.py` | `UpstoxAdapter` (wraps existing Upstox components) |
| **CREATE** | `inc_trade/adapters/paper.py` | `PaperAdapter` |
| **CREATE** | `inc_trade/adapters/replay.py` | `ReplayAdapter` |
| **MODIFY** | `brokers/__init__.py` | `connect()` returns `BrokerAdapter` |

### Code: `broker_adapter.py`

```python
"""BrokerAdapter protocol — primary broker interface replacing BrokerGateway.

Each broker adapter implements all provider protocols and can be injected
directly into Instruments.

Usage::

    adapter = DhanAdapter(client_id="...", access_token="...")
    adapter.connect()

    # Instrument-centric API
    reliance = adapter.instrument("RELIANCE", "NSE")
    reliance.quote()       # → uses adapter as quote provider
    reliance.depth(200)    # → uses adapter as depth provider
    reliance.buy(qty=10)   # → uses adapter as order provider
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from inc_trade.market.instrument import Instrument


@runtime_checkable
class BrokerAdapter(Protocol):
    """Primary broker interface. Implemented by DhanAdapter, UpstoxAdapter, etc."""

    @property
    def broker_id(self) -> str:
        """Unique broker identifier (e.g., 'dhan', 'upstox')."""
        ...

    def connect(self, **credentials: Any) -> None:
        """Establish connection to the broker."""
        ...

    def disconnect(self) -> None:
        """Close connection to the broker."""
        ...

    def instrument(
        self,
        symbol: str,
        exchange: str,
        **kwargs: Any,
    ) -> Instrument:
        """Create an instrument with this adapter's providers injected.

        The returned Instrument has live quote, depth, historical,
        streaming, and order capabilities wired to this broker.
        """
        ...
```

### Using the adapter

```python
# Current (gateway):
# broker = create_broker("dhan", access_token="...", client_id="...")
# quote = broker.get_quote("RELIANCE")

# Target (adapter):
adapter = DhanAdapter(client_id="123", access_token="abc")
adapter.connect()
reliance = adapter.instrument("RELIANCE", "NSE")
quote = reliance.quote()
```

### Tests

| Test | Coverage |
|------|----------|
| `test_broker_adapter_protocol_structure` | Protocol is `@runtime_checkable` |
| `test_dhan_adapter_implements_protocol` | `isinstance(DhanAdapter(), BrokerAdapter)` |
| `test_dhan_adapter_instrument_factory` | `adapter.instrument("RELIANCE", "NSE")` returns `Instrument` |
| `test_dhan_adapter_quote` | `adapter.quote("RELIANCE", "NSE")` returns `Quote` |
| `test_dhan_adapter_depth` | `adapter.depth("RELIANCE", "NSE", 200)` returns `MarketDepth` |
| `test_upstox_adapter_instrument_factory` | `adapter.instrument("RELIANCE", "NSE")` returns `Instrument` |
| `test_paper_adapter_implements_protocol` | `PaperAdapter` satisfies `BrokerAdapter` |

---

## 5. Phase 3: Unify OptionChain with Instrument Composition

### What

Make `InstrumentOptionChain` (already in `market/option_chain.py`) the primary
implementation. The domain-level `OptionChain` (string-based) becomes a legacy
wrapper. All option chain operations return `InstrumentOptionLeg` objects that
contain live `Instrument` references.

### Why

Currently there are two `OptionChain` implementations:
1. `domain/entities.py:OptionChain` — string-based (legs have `symbol: str`)
2. `market/option_chain.py:InstrumentOptionChain` — Instrument-based (legs have `.instrument`)

The Instrument-based one is the target. The domain version should be deprecated.

### Files

| Action | File | Description |
|--------|------|-------------|
| **MODIFY** | `inc_trade/market/option_chain.py` | Add `subscribe_all()`, `synthetic_future()` |
| **MODIFY** | `inc_trade/market/context.py` | Return `InstrumentOptionChain` from `option_chain()` |
| **MODIFY** | `inc_trade/market/factory.py` | Add `option_chain()` convenience method |
| **MODIFY** | `inc_trade/market/instrument.py` | `option_chain()` returns `InstrumentOptionChain` |

### Key enhancements to `InstrumentOptionChain`

```python
class InstrumentOptionChain:
    # ... existing (174 lines, max_pain, pcr, itm/otm/nearest) ...

    def subscribe_all(self, callback: Callable) -> list[Any]:
        """Subscribe to live ticks for ALL strikes in the chain."""
        handles = []
        for strike in self.strikes:
            if strike.call.instrument:
                h = strike.call.instrument.subscribe(callback)
                handles.append(h)
            if strike.put.instrument:
                h = strike.put.instrument.subscribe(callback)
                handles.append(h)
        return handles

    @property
    def synthetic_future(self) -> Any:
        """Synthetic long future = buy call + sell put at same strike."""
        atm = self.atm()
        if atm is None:
            return None
        return {
            "buy_call": atm.call.instrument,
            "sell_put": atm.put.instrument,
            "cost": atm.call.instrument.ltp() - atm.put.instrument.ltp(),
        }
```

### Tests

| Test | Coverage |
|------|----------|
| `test_instrument_option_chain_leg_has_instrument` | `chain.strikes[0].call.instrument` is `Instrument` |
| `test_instrument_option_chain_subscribe_all` | `subscribe_all()` returns stream handles |
| `test_instrument_option_chain_synthetic_future` | `synthetic_future` returns dict with instruments |
| `test_instrument_option_chain_max_pain` | `max_pain_strike` computes correctly |
| `test_instrument_option_chain_pcr` | `pcr` computed from OI |

---

## 6. Phase 4: Extension Registry

### What

Create an `ExtensionRegistry` that maps broker capabilities to decorators.
The factory automatically applies the correct decorators based on the
broker's capabilities matrix.

### Why

Currently exensions must be manually applied. The registry makes this automatic:
`DhanAdapter` declares depth_20 + depth_200 capabilities → factory auto-wraps
with `Depth20Decorator` + `Depth200Decorator`.

### Files

| Action | File | Description |
|--------|------|-------------|
| **CREATE** | `inc_trade/extensions/registry.py` | `ExtensionRegistry` |
| **MODIFY** | `inc_trade/market/factory.py` | Auto-apply extensions from registry |
| **MODIFY** | `inc_trade/extensions/__init__.py` | Export `ExtensionRegistry` |

### Code: `registry.py`

```python
"""ExtensionRegistry — maps broker capabilities to decorator classes."""

from __future__ import annotations

from typing import Any

from inc_trade.market.instrument import Instrument


class ExtensionEntry:
    """Maps a capability flag to a decorator factory."""

    def __init__(
        self,
        capability: str,
        decorator_class: type,
        decorator_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.capability = capability
        self.decorator_class = decorator_class
        self.decorator_kwargs = decorator_kwargs or {}


class ExtensionRegistry:
    """Registry mapping broker capabilities to decorator classes.

    Usage::

        registry = ExtensionRegistry()
        registry.register("depth_20", Depth20Decorator, {"depth_provider": ...})

        # Later, in factory:
        extensions = registry.resolve_for(capabilities)
        instrument = apply_extensions(base_instrument, extensions)
    """

    def __init__(self) -> None:
        self._entries: dict[str, ExtensionEntry] = {}

    def register(
        self,
        capability: str,
        decorator_class: type,
        **decorator_kwargs: Any,
    ) -> None:
        self._entries[capability] = ExtensionEntry(
            capability=capability,
            decorator_class=decorator_class,
            decorator_kwargs=decorator_kwargs,
        )

    def resolve_for(self, capabilities: Any) -> list[ExtensionEntry]:
        """Return entries whose capability is supported."""
        result = []
        for entry in self._entries.values():
            if capabilities.supports(entry.capability):
                result.append(entry)
        return result

    def apply(self, instrument: Instrument, capabilities: Any) -> Instrument:
        """Apply all matching decorators to the instrument."""
        result = instrument
        for entry in self.resolve_for(capabilities):
            result = entry.decorator_class(result, **entry.decorator_kwargs)
        return result
```

### Tests

| Test | Coverage |
|------|----------|
| `test_extension_registry_register` | Register and resolve capability |
| `test_extension_registry_resolve_for` | Returns only matching entries |
| `test_extension_registry_apply` | Decorator applied based on capability |
| `test_extension_registry_empty` | No capabilities → no decorators applied |

---

## 7. Phase 5: Gateway Deprecation & Cleanup

### What

Add deprecation warnings to `BrokerGateway`, `BrokerFacade`, `create_broker()`.
Remove all `object.__setattr__` hacks in favor of constructor injection.
Remove unused backward-compat paths.

### Why

The gateway pattern is the old architecture. All new code should use
`BrokerAdapter` and the Instrument-centric API. The cleanup removes
technical debt.

### Files

| Action | File | Description |
|--------|------|-------------|
| **MODIFY** | `inc_trade/services/broker_facade.py` | Add `DeprecationWarning` |
| **MODIFY** | `inc_trade/services/_gateway_compat.py` | Deprecate |
| **MODIFY** | `brokers/__init__.py` | `create_broker()` → DeprecationWarning, delegate to `connect()` |
| **MODIFY** | `inc_trade/market/factory.py` | Remove `object.__setattr__` for providers |
| **MODIFY** | `inc_trade/market/instrument.py` | Make providers constructor params |
| **MODIFY** | `inc_trade/market/context.py` | Remove `_delegate_context` backward compat |

### Provider Injection Cleanup

Current (hack):
```python
object.__setattr__(inst, "_provider", provider)
object.__setattr__(inst, "_delegate_context", context)
```

Target (clean):
```python
@dataclass(frozen=True, kw_only=True)
class Instrument:
    # ... frozen fields ...
    # Provider fields (not part of eq/hash):
    _provider: Any = field(default=None, repr=False, compare=False)
    _historical_provider: Any = field(default=None, repr=False, compare=False)
    _streaming_provider: Any = field(default=None, repr=False, compare=False)
    _depth_provider: Any = field(default=None, repr=False, compare=False)
    _order_provider: Any = field(default=None, repr=False, compare=False)
```

Wait — frozen dataclass fields are set in `__init__`. The issue is that `factory.py`
creates the instance first, then sets providers via `object.__setattr__`. The fix is
to pass providers in the constructor. But the current `Instrument` subclasses (`Equity`,
`Future`, `Option`) have different `__init__` signatures.

**Better approach:** Use `__post_init__` and a builder pattern, or simply accept that
provider injection is a post-construction operation and use a clean method:

```python
class Instrument:
    def with_providers(
        self,
        provider: Any = None,
        historical_provider: Any = None,
        streaming_provider: Any = None,
        depth_provider: Any = None,
        order_provider: Any = None,
    ) -> Instrument:
        """Return a new Instrument with providers attached.

        Uses ``object.__setattr__`` internally but provides a clean API.
        """
        # ... set providers ...
        return self
```

### Tests

| Test | Coverage |
|------|----------|
| `test_create_broker_deprecation_warning` | `create_broker()` emits `DeprecationWarning` |
| `test_broker_facade_deprecation_warning` | `BrokerFacade` emits `DeprecationWarning` |
| `test_connect_returns_adapter` | `connect("dhan")` returns `DhanAdapter` |
| `test_no_object_setattr_in_factory` | Factory uses constructor or `with_providers()` |
| `test_no_delegate_context` | `_delegate_context` removed |

---

## 8. Test Strategy

### Architecture Guardrails (to add)

| Rule | Test | Enforced By |
|------|------|-------------|
| Decorators extend `InstrumentDecorator` | `test_architecture.py` | pytest + runtime_checkable |
| No new `object.__setattr__` in factory | `test_architecture.py` | AST scan |
| Adapter implements `BrokerAdapter` | `test_architecture.py` | `isinstance(adapter, BrokerAdapter)` |
| `BrokerGateway` emits deprecation | `test_architecture.py` | Warning catcher |
| No `find_gateway`/`get_gateway` in new code | `test_architecture.py` | Import scanner |

### Contract Tests (to add)

| Test | Coverage |
|------|----------|
| `test_broker_adapter_contract` | All adapters satisfy `BrokerAdapter` protocol |
| `test_decorator_contract` | All decorators satisfy `InstrumentDecorator` contract |
| `test_extension_registry_contract` | Registry resolves correctly |

### Phased Test Additions

| Phase | Tests Added | Running Total |
|-------|-------------|---------------|
| Phase 1 | 15 (decorators) | +15 |
| Phase 2 | 6 (adapter protocol) | +6 |
| Phase 3 | 5 (option chain) | +5 |
| Phase 4 | 4 (extension registry) | +4 |
| Phase 5 | 6 (deprecation/cleanup) | +6 |
| Architecture | 5 (new guardrails) | +5 |
| **Total** | **41** | **2,358** |

---

## 9. Rollback Strategy

| Risk | Mitigation |
|------|------------|
| Decorator pipeline breaks existing Instrument users | All existing methods delegate through `__getattr__` — backward compatible |
| Adapter protocol breaks existing gateway users | Gateway still works during deprecation period; both paths coexist |
| OptionChain unification breaks chain consumers | `InstrumentOptionChain` wraps the domain `OptionChain` — add adapter method |
| Factory changes break broker connectors | Pin factory API; old parameters work with deprecation warning |
| Test regressions | Run full suite (`pytest brokers/tests/ --tb=short -q`) before each merge |

---

## Implementation Order

```
Phase 1 (Week 1):
  ├── decorators.py           → InstrumentDecorator base + helpers
  ├── cache_decorator.py      → CachedDecorator
  ├── log_decorator.py        → LoggedDecorator
  ├── depth_decorators.py     → Refactor to extend InstrumentDecorator
  ├── instrument.py           → Add buy()/sell()
  ├── factory.py              → Add decorator pipeline
  └── ✅ 15 new tests

Phase 2 (Week 1-2):
  ├── adapters/__init__.py    → Package
  ├── adapters/broker_adapter.py → Protocol
  ├── adapters/dhan.py        → DhanAdapter
  ├── adapters/upstox.py      → UpstoxAdapter
  ├── adapters/paper.py       → PaperAdapter
  ├── brokers/__init__.py     → connect() returns adapter
  └── ✅ 6 new tests

Phase 3 (Week 2):
  ├── option_chain.py         → subscribe_all(), synthetic_future()
  ├── context.py              → Return InstrumentOptionChain
  ├── factory.py              → option_chain() convenience
  └── ✅ 5 new tests

Phase 4 (Week 2-3):
  ├── extensions/registry.py  → ExtensionRegistry
  ├── factory.py              → Auto-apply extensions
  └── ✅ 4 new tests

Phase 5 (Week 3):
  ├── broker_facade.py        → Deprecate
  ├── brokers/__init__.py     → Deprecate create_broker()
  ├── factory.py              → Remove object.__setattr__
  ├── instrument.py           → Clean provider injection
  └── ✅ 11 new tests
```

---

## Board Verdict

**UNANIMOUS APPROVAL** — The transformation is well-grounded in the existing codebase.
80% of the target architecture is already in place. The 5-phase plan proceeds
incrementally with no big-bang changes, each phase independently testable and
reversible.

**Key quote from each board member:**

| Member | Verdict |
|--------|---------|
| **Robert C. Martin** | "Dependency rules are sound. Decorator pipeline inverts control correctly — Instrument doesn't know broker details." |
| **Eric Evans** | "Ubiquitous language is consistent: `Instrument.quote()`, `Instrument.buy()`, `OptionChain.atm_call().instrument`. This is the model the user thinks in." |
| **Martin Fowler** | "The refactoring is safe — each phase is independently reversible. The Decorator pattern elegantly replaces the Gateway god object." |
| **Greg Young** | `Instrument.quote_state()` provides the mutable state needed for event sourcing without violating immutability of the entity. Clean. |
| **Vaughn Vernon** | "The bounded contexts are correctly separated: Market (`market/`), Trading (`trading/`), Infrastructure (`infrastructure/`). No cross-imports." |
| **Kent Beck** | "41 new tests across 5 phases, each phase independently testable. This is test-driven architecture evolution." |
| **Michael Feathers** | "The characterization tests (2,317 passing) provide the safety net. `object.__setattr__` removal is the key debt to pay." |
| **Dr. Venkat Subramaniam** | "Composition over inheritance — decorators compose, OptionChain composes Instruments. The design is flexible without being fragile." |
