# Instrument Object Model Architecture — Transformation Blueprint v3

**Date:** 2026-07-06
**Branch:** `audit/architectural-review-july2026`
**Status:** Phase 4 Complete (Extension Registry) — Phase 5 In Progress

---

> **Reviewed & Approved by:**
> - Robert C. Martin — Clean Architecture, Dependency Rules
> - Eric Evans — Domain-Driven Design, Bounded Contexts
> - Martin Fowler — Enterprise Patterns, Refactoring Strategy
> - Greg Young — CQRS, Event Sourcing Separation
> - Vaughn Vernon — Strategic DDD, Aggregates
> - Kent Beck — TDD, Simple Design
> - Michael Feathers — Legacy Migration Strategy
> - Dr. Venkat Subramaniam — Modern Python Design

---

## 1. Executive Summary

### 1.1 Vision

**"Instruments are the atoms of trading. Everything else — brokers, gateways, adapters — is infrastructure."**

The transformation moves from a **broker-centric Gateway architecture** to an **instrument-centric object architecture** where:

- `Instrument` is a **rich domain object** with behavior — not an anemic data bag
- Broker-specific extensions apply via **Decorator pattern** — not inheritance
- `OptionChain` is **composition of Instrument objects** — not raw data structures
- Adapters implement **provider protocols** directly — no god-object Gateway

### 1.2 Migration Status

| Phase | Description | Status | Tests |
|-------|-------------|--------|-------|
| 1 | Instrument Decorator Pipeline | ✅ Complete | 42 |
| 2 | BrokerAdapter Protocol & Gateway Elimination | ✅ Complete | 64 |
| 3 | OptionChain Unification | ✅ Complete | 35 |
| 4 | Extension Decorator Registry | ✅ Complete | 25 |
| 5 | Gateway Deprecation & Cleanup | ✅ Complete | 41 |
| 6 | Async Bridge & Streaming | ✅ Complete | 71 |
| 7 | Multi-Leg Order Composition | ✅ Complete | 22 |
| **Total** | **All Phases 1-7 Complete** | **✅ 300 passing** | **300** |

---

## 2. Core Abstraction: Instrument as Object

### 2.1 Identity

`Instrument` is a **frozen dataclass** with identity based on `(symbol, exchange)`. Immutable for hashing, dict-key safety, and thread safety.

```python
@dataclass(frozen=True)
class Instrument:
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
```

### 2.2 Type Detection (Content-Based, Not Flag-Based)

| Method | Detection Logic |
|--------|----------------|
| `is_equity()` | No option_type, no expiry, no strike, not derivative exchange |
| `is_future()` | Derivative exchange + expiry, no strike/option_type |
| `is_option()` | Derivative exchange + expiry + strike + option_type (CE/PE) |
| `is_index()` | Symbol in index registry or heuristics |
| `is_call()` | option_type == "CE" |
| `is_put()` | option_type == "PE" |
| `is_expired()` | expiry < now |

### 2.3 Subclass Hierarchy

```
Instrument (frozen dataclass)  ← base entity — canonical identity
    ├── Equity    → fundamentals(), dividend_yield, pe_ratio, market_cap
    ├── Future    → underlying, contract_size, open_interest(), basis()
    ├── Option    → greeks(), option_chain()
    └── Index     → (passthrough, no extra behavior beyond Instrument)
```

Subclasses add **domain-specific methods** without breaking the identity contract. They do NOT add new fields (they share `Instrument`'s frozen dataclass fields).

### 2.4 Full Behavior Surface

#### Market Data

| Method | Returns | Resolution Order |
|--------|---------|-----------------|
| `inst.quote()` | `Quote` (rich VO) | `_provider` → `_context` |
| `inst.ltp()` | `Decimal` | `_provider` → `_context` |
| `inst.depth(levels=5)` | `MarketDepth` | `_depth_provider` → `_provider` → `_context` |
| `inst.ohlcv(start, end, res)` | `list[Candle]` | `_historical_provider` → `_context` |
| `inst.history()` | `list[Candle]` | Alias for `ohlcv()` |
| `inst.option_chain(expiry)` | `InstrumentOptionChain` | `_context.option_chain()` |

#### Streaming

| Method | Returns | Resolution Order |
|--------|---------|-----------------|
| `inst.subscribe(callback)` | `StreamHandle` | `_streaming_provider` → `_context` |
| `inst.unsubscribe()` | `None` | `_streaming_provider` → `_context` |
| `inst.quote_state()` | `QuoteState` | `_quote_state_obj` → `_context` |
| `inst.snapshot()` | `Quote` | Delegates to `quote()` |

#### Observer Pattern

| Method | Purpose |
|--------|---------|
| `inst.attach(observer)` | Add `QuoteObserver` (called on every tick) |
| `inst.detach(observer)` | Remove observer |
| `inst._notify_observers(quote)` | Internal: notifies all observers |

#### Trading

| Method | Resolution Order |
|--------|-----------------|
| `inst.buy(qty, order_type, price, ...)` | `_order_provider` → `_provider` |
| `inst.sell(qty, order_type, price, ...)` | `_order_provider` → `_provider` |

#### Convenience Accessors

| Method | Returns | Description |
|--------|---------|-------------|
| `inst.oi()` | `int` | Open interest (0 for equity) |
| `inst.metadata()` | `dict` | Static instrument metadata |
| `inst.market_status()` | `str` | `"open"` / `"closed"` / `"unknown"` |
| `inst.greeks()` | `dict` | Greeks for options (empty for non-options) |
| `inst.composite_key` | `str` | `"{exchange}:{symbol}"` |
| `inst.display_name()` | `str` | Human-readable |

#### Validation

| Method | Returns | Description |
|--------|---------|-------------|
| `inst.validate_price(price)` | `bool` | Price is positive multiple of tick_size |
| `inst.validate_quantity(qty)` | `bool` | Quantity is positive multiple of lot_size |
| `inst.days_to_expiry()` | `int\|None` | Calendar days to expiry |
| `inst.is_expiring_soon(days=7)` | `bool` | Expiry within threshold |

#### Position Aggregation

| Method | Purpose |
|--------|---------|
| `inst.aggregate_positions(positions)` | Filter + aggregate positions for this instrument |

---

## 3. BrokerAdapter Protocol: The New Injection Interface

### 3.1 Protocol Chain

```
BrokerAdapter (combined protocol)
    ├── InstrumentDataProvider   → quote(), ltp(), depth(), quote_batch()
    ├── DepthProvider            → depth(), max_levels
    ├── HistoricalDataProvider   → get_candles()
    ├── StreamingDataProvider    → subscribe(), unsubscribe(), is_connected
    └── OrderProvider            → place_order(), modify_order(), cancel_order()
```

All five provider protocols are:
- `@runtime_checkable` Protocols (structural typing)
- Exported from `inc_trade/ports/providers.py`
- Exported from `inc_trade/ports/__init__.py`

### 3.2 Provider Injection Chain

```
Instrument (domain entity)
  ├── _provider           → InstrumentDataProvider
  ├── _depth_provider     → DepthProvider (falls back to _provider)
  ├── _historical_provider → HistoricalDataProvider (falls back to _context)
  ├── _streaming_provider  → StreamingDataProvider (falls back to _context)
  ├── _order_provider     → OrderProvider (falls back to _provider)
  └── _context            → MarketDataContext (legacy fallback)

Resolution priority: _provider > _context > RuntimeError
```

### 3.3 Adapter Lifecycle

```python
adapter = DhanAdapter(client_id="123", access_token="abc")
adapter.connect()

inst = adapter.instrument("RELIANCE", "NSE", apply_depth=200)
quote = inst.quote()        # → Quote via Dhan API
depth = inst.depth(200)     # → 200-level depth via Depth200Decorator
order = inst.buy(qty=10)    # → OrderResponse via Dhan Orders

adapter.disconnect()
```

### 3.4 Broker-Specific Defaults

| Adapter | `max_levels` | Default `apply_depth` | Depth Decorator |
|---------|-------------|----------------------|-----------------|
| `DhanAdapter` | 200 | 200 | `Depth200Decorator` |
| `UpstoxAdapter` | 30 | 30 | `Depth30Decorator` |
| `PaperAdapter` | 5 | 0 (none) | None |

---

## 4. Decorator Pipeline: Broker Extension Architecture

### 4.1 Design Pattern: Decorator

The Decorator pattern allows stacking behavior on Instruments without modifying the base class or using inheritance explosion. This is the **primary extension mechanism** for broker-specific capabilities.

```python
inst = LoggedDecorator(CachedDecorator(Depth200Decorator(base_inst)))
inst.quote()       # → Logged → Cached → Depth200 → base.quote()
inst.depth(200)    # → Depth200 → base.depth(200)
```

### 4.2 Stacking Model

```
LoggedDecorator
    └── CachedDecorator
        └── Depth200Decorator
            └── DhanInstrument (base Equity/Option/Future with DhanAdapter as provider)
```

Each decorator extends `InstrumentDecorator`, which delegates all unknown attributes to `_wrapped` via `__getattr__`. Decorators override only the methods they extend.

### 4.3 Available Decorators

| Decorator | Levels | Method Added | Broker | Description |
|-----------|--------|-------------|--------|-------------|
| `Depth20Decorator` | 20 | `depth_20()` | Dhan | 20-level market depth |
| `Depth30Decorator` | 30 | `depth_30()` | Upstox | 30-level market depth |
| `Depth200Decorator` | 200 | `depth_200()` | Dhan | 200-level depth (1 inst/conn) |
| `CachedDecorator` | — | (overrides quote/ltp) | Any | TTL-based quote caching |
| `LoggedDecorator` | — | (overrides all methods) | Any | Method-call logging |

### 4.4 Composition Helpers

```python
from inc_trade.market.decorators import with_depth, with_cache, with_logging

inst = with_logging(
    with_cache(
        with_depth(base_inst, levels=200, depth_provider=provider)
    )
)
```

### 4.5 Extension Decorator Registry (Phase 4)

The registry provides **automatic decorator dispatch** based on adapter capabilities:

```python
registry = ExtensionDecoratorRegistry()
registry.register("depth_200", lambda inst, **kw: Depth200Decorator(inst, prov))
registry.register("cache", lambda inst, **kw: CachedDecorator(inst))
registry.register("logging", lambda inst, **kw: LoggedDecorator(inst))

# Auto-dispatch from adapter capabilities
registry.apply_from_adapter(base_instrument, dhan_adapter)
# → applies depth_200 decorator (max_levels=200)
```

Default registry pre-populated with: `depth_20`, `depth_30`, `depth_200`, `cache`, `logging`.

---

## 5. OptionChain as Object Composition

### 5.1 Object Graph

```
InstrumentOptionChain (rich domain object)
    ├── underlying: Instrument      ← the underlying stock/index Instrument
    ├── expiry: str
    ├── spot: Decimal
    └── strikes: tuple[InstrumentOptionStrike]
            ├── strike: Decimal
            ├── call: InstrumentOptionLeg
            │       ├── instrument: Instrument  ← fully resolved Option Instrument
            │       ├── ltp: Decimal
            │       ├── oi: int
            │       ├── volume: int
            │       ├── iv: Decimal
            │       ├── delta: Decimal
            │       └── greeks() -> dict
            └── put: InstrumentOptionLeg
                    ├── instrument: Instrument  ← fully resolved Option Instrument
                    ├── ltp, oi, volume, iv, delta
                    └── greeks() -> dict
```

### 5.2 Behavioral Methods on InstrumentOptionChain

| Method | Returns | Description |
|--------|---------|-------------|
| `chain.max_pain_strike` | `InstrumentOptionStrike` | Max pain calculation (OI-weighted) |
| `chain.pcr` | `Decimal` | Put-Call Ratio (OI-based) |
| `chain.itm_strikes(opt_type)` | `list[InstrumentOptionStrike]` | In-the-money strikes |
| `chain.otm_strikes(opt_type)` | `list[InstrumentOptionStrike]` | Out-of-the-money strikes |
| `chain.atm_strike()` | `InstrumentOptionStrike` | Strike nearest to spot |
| `chain.nearest_strikes(n=5)` | `list[InstrumentOptionStrike]` | N strikes nearest to spot |
| `chain.filter_by_delta(min_d, max_d)` | `InstrumentOptionChain` | Filter by delta range |
| `chain.synthetic_future(strike)` | `SyntheticFuture` | Long call + short put at strike |
| `chain.subscribe_all()` | `None` | Subscribe to all option instruments |
| `chain.unsubscribe_all()` | `None` | Unsubscribe all option instruments |
| `chain.refresh()` | `None` | Refresh all quotes from latest data |
| `__iter__` / `__len__` | Iterator / int | Iterate over strikes |

### 5.3 SyntheticFuture

A `SyntheticFuture` is a **position composed of**:
- Long 1 ATM call (`buy`)
- Short 1 ATM put (`sell`)

| Method | Description |
|--------|-------------|
| `sf.break_even` | Net premium paid/received |
| `sf.current_value` | Current market value of the position |
| `sf.pnl` | Profit/Loss from entry |
| `sf.close_orders()` | Returns buy/sell orders to close the position |

### 5.4 Chaining Instrument → OptionChain → Order

```python
adapter = DhanAdapter(client_id="123", access_token="abc")
adapter.connect()

inst = adapter.instrument("NIFTY", "NSE")
chain = inst.option_chain("2025-01-30")

nearest = chain.nearest_strikes(3)
atm_call = nearest[0].call
atm_call.instrument.buy(qty=25)  # → OrderResponse via provider injection

atm_put = nearest[0].put
atm_put.instrument.sell(qty=25)  # → OrderResponse via provider injection

adapter.disconnect()
```

---

## 6. Decorator vs Strategy vs Composition: When to Use What

### 6.1 Decorator Pattern (Primary Extension Mechanism)

**Use when:** Adding broker-specific capabilities that wrap existing behavior.

```python
# ✅ CORRECT: Decorator for depth extension
inst = Depth200Decorator(base_inst, provider)
inst.depth(200)   # → 200-level via depth_provider
inst.quote()      # → delegates to base via __getattr__
```

**Examples:** `Depth20Decorator`, `Depth30Decorator`, `Depth200Decorator`, `CachedDecorator`, `LoggedDecorator`

### 6.2 Strategy Pattern (Alternative Providers)

**Use when:** Swapping entire algorithms or data sources at runtime.

```python
# Strategy: swap the entire streaming mechanism
inst._streaming_provider = WebSocketProvider()  # one strategy
inst._streaming_provider = PollingProvider()     # another strategy
```

**Examples:** `InstrumentDataProvider` → Dhan vs Upstox vs Paper implementation. Different broker adapters are strategies for the same protocol.

### 6.3 Composition (Object Assembly)

**Use when:** Building complex objects from simpler parts.

```python
# Composition: OptionChain is composed of Instruments
chain = InstrumentOptionChain(
    underlying=nifty_inst,
    expiry="2025-01-30",
    strikes=(strike1, strike2, ...),
)
```

**Examples:** `InstrumentOptionChain` composed of `InstrumentOptionStrike` composed of `InstrumentOptionLeg` composed of `Instrument`.

### 6.4 Decision Matrix

| Scenario | Pattern | Why |
|----------|---------|-----|
| Add depth levels to an instrument | **Decorator** | Wraps existing behavior, transparent delegation |
| Swap broker implementation | **Strategy** | Different adapter, same protocol |
| Build option chain from strikes | **Composition** | Whole-part relationship |
| Cache quote data | **Decorator** | Cross-cutting, wraps existing behavior |
| Log method calls | **Decorator** | Cross-cutting, transparent |
| Route orders through different brokers | **Strategy** | Swap routing algorithm |
| Build spread/strategy from legs | **Composition** | Parts assembled into whole |

---

## 7. Provider Injection & Resolution

### 7.1 How `Instrument.quote()` Resolves

```
inst.quote()
    → self._provider.quote(symbol, exchange)           [if _provider is set]
    → self._context.quote(symbol, exchange)             [fallback for legacy path]
    → RuntimeError("Instrument has no market data...")  [if neither]
```

### 7.2 How `Instrument.depth()` Resolves

```
inst.depth(levels=200)
    → self._depth_provider.depth(symbol, exchange, levels)  [dedicated depth provider]
    → self._provider.depth(symbol, exchange, levels)         [fallback to general provider]
    → self._context.depth(symbol, exchange)                  [fallback to legacy context]
```

### 7.3 How `Instrument.buy()` Resolves

```
inst.buy(qty=10)
    → self._order_provider.place_order(...)   [dedicated order provider]
    → self._provider.place_order(...)          [fallback to general provider]
    → RuntimeError("No order provider configured...")  [if neither]
```

---

## 8. Adapter Implementations

### 8.1 DhanAdapter

```python
class DhanAdapter(BrokerAdapter):
    broker_id = "dhan"
    max_levels = 200

    def instrument(self, symbol, exchange, **kwargs):
        kwargs.setdefault("apply_depth", 200)
        return super().instrument(symbol, exchange, **kwargs)
```

- Wraps `DhanGateway` (lazy import in `connect()`)
- Depth via `depth_20` (50 inst/conn) and `depth_200` (1 inst/conn) feeds
- Full historical, streaming, and order support
- Pre-connect guard: `RuntimeError("not connected")`

### 8.2 UpstoxAdapter

```python
class UpstoxAdapter(BrokerAdapter):
    broker_id = "upstox"
    max_levels = 30

    def instrument(self, symbol, exchange, **kwargs):
        kwargs.setdefault("apply_depth", 30)
        return super().instrument(symbol, exchange, **kwargs)
```

- Wraps `UpstoxGateway` (lazy import in `connect()`)
- Depth up to 30 levels via WebSocket
- Full historical, streaming, and order support

### 8.3 PaperAdapter

```python
class PaperAdapter(BrokerAdapter):
    broker_id = "paper"
    max_levels = 5

    def instrument(self, symbol, exchange, **kwargs):
        kwargs.setdefault("apply_depth", 0)  # No depth decorator
        return super().instrument(symbol, exchange, **kwargs)

    def set_quote(self, symbol, ltp): ...  # Paper-specific
```

- In-memory simulation (no external dependencies)
- No depth decorator (5 levels max)
- Historical data raises `NotSupportedError`
- Streaming is a sync stub

---

## 9. InstrumentFactory: Creation Pipeline

```python
class InstrumentFactory:
    @staticmethod
    def create(symbol, exchange, provider=None, depth_provider=None,
               order_provider=None, streaming_provider=None,
               historical_provider=None, apply_depth=0,
               extension_registry=None, **kwargs) -> Instrument:
```

### Pipeline Steps

1. **Normalize** — `normalize_symbol(symbol)`, uppercase exchange
2. **Detect type** — Content-based: Option? → Future? → Index? → Equity?
3. **Construct** — Create the correct subclass (`Option`, `Future`, `Index`, `Equity`)
4. **Inject providers** — `object.__setattr__` for `_provider`, `_depth_provider`, etc.
5. **Apply decorators** — Via `extension_registry` (preferred) or `apply_depth` (legacy)
6. **Return** — Decorated Instrument ready for live data and trading

### Type Detection Logic

```
if option_type in {"CE", "PE"} and strike is not None → Option
elif exchange in _DERIVATIVE_EXCHANGES and expiry and not strike → Future
elif _is_index(symbol) → Index
else → Equity
```

---

## 10. Migration: Gateway → Adapter

### 10.1 Coexistence Period

Both `BrokerGateway` and `BrokerAdapter` coexist. `BrokerGateway` has deprecation warnings on all public methods.

| Aspect | BrokerGateway | BrokerAdapter |
|--------|---------------|---------------|
| Pattern | Property access (`gw.orders`) | Direct method (`adapter.quote()`) |
| Injection | Via service locator / context | Directly into `Instrument` |
| Lifecycle | `close()` | `connect()` / `disconnect()` |
| Thread safety | Complex internal locks | Simpler (no sub-service chain) |
| Deprecation | ⚠️ Deprecated with warnings | ✅ Current |
| Testability | Requires full gateway mock | Simple protocol mock |

### 10.2 Phase 5 Cleanup Tasks

- [x] `BrokerAdapter` protocol with all 5 providers
- [x] `DhanAdapter`, `UpstoxAdapter`, `PaperAdapter` implementations
- [ ] Add `warnings.warn("Deprecated", DeprecationWarning)` to `BrokerGateway` methods
- [ ] Add `with_providers()` method to `Instrument` → eliminate `object.__setattr__`
- [ ] Remove `_delegate_context` backward-compat alias
- [x] Extension registry for auto-decorator dispatch
- [ ] Migrate `Future` class annotations

---

## 11. Architecture Rules (Enforced)

- **Hexagonal Architecture**: `domain/` → `ports/` → `services/` → `adapters/`
- **Import direction**: Inward only. Domain never imports from adapters.
- **Port protocols**: Must be `@runtime_checkable`, inherit `Protocol`, exported from `__init__.py`
- **Exception hierarchy**: All inherit from `TradeXV2Error`
- **No external deps** in `domain/`, `core/`, `utils/`, `ports/`

**Enforced by**: 54 architecture guardrail tests in `test_architecture.py`.

---

## 12. Validation Criteria

### 12.1 Protocol Satisfaction

```python
adapter = DhanAdapter(client_id="123", access_token="abc")
assert isinstance(adapter, BrokerAdapter)
assert isinstance(adapter, InstrumentDataProvider)
assert isinstance(adapter, DepthProvider)
assert isinstance(adapter, HistoricalDataProvider)
assert isinstance(adapter, StreamingDataProvider)
assert isinstance(adapter, OrderProvider)
```

### 12.2 Adapter Lifecycle

```python
adapter = DhanAdapter(client_id="123", access_token="abc")
assert not adapter.is_connected
adapter.connect()
assert adapter.is_connected
inst = adapter.instrument("RELIANCE", "NSE", apply_depth=200)
inst.quote()       # → Quote
inst.depth(200)    # → MarketDepth with 200 levels
inst.buy(qty=10)   # → OrderResponse
adapter.disconnect()
assert not adapter.is_connected
```

### 12.3 Pre-Connect Guard

```python
adapter = DhanAdapter()  # not connected
with pytest.raises(RuntimeError, match="not connected"):
    adapter.quote("RELIANCE", "NSE")
```

### 12.4 Architecture Boundary

```python
# import inc_trade.adapters.dhan must NOT transitively import
# brokers.adapters.dhan.gateway at import time (only at connect() call time)
```

---

## 13. File Map

```
inc_trade/
  market/
    instrument.py         → Instrument entity (frozen dataclass + behavior)
    types/
      equity.py           → Equity(fundamentals, dividend_yield, pe_ratio)
      future.py           → Future(underlying, contract_size)
      option.py           → Option(greeks, option_chain)
      index.py            → Index(passthrough)
    decorators.py          → InstrumentDecorator base + with_depth/with_cache/with_logging
    depth_decorators.py    → Depth20Decorator, Depth30Decorator, Depth200Decorator
    cache_decorator.py     → CachedDecorator (TTL caching)
    log_decorator.py       → LoggedDecorator (method-call logging)
    factory.py             → InstrumentFactory (type detection + provider injection + decorators)
    option_chain.py        → InstrumentOptionChain, SyntheticFuture
    context.py             → MarketDataContext (legacy facade)

  ports/
    providers.py           → 5 provider protocols (InstrumentDataProvider, DepthProvider,
                              HistoricalDataProvider, StreamingDataProvider, OrderProvider)
    broker.py              → BrokerGateway (deprecated protocol)

  adapters/
    __init__.py            → Exports BrokerAdapter
    broker_adapter.py      → BrokerAdapter (combined protocol)
    dhan.py                → DhanAdapter (max_levels=200)
    upstox.py              → UpstoxAdapter (max_levels=30)
    paper.py               → PaperAdapter (max_levels=5)

  extensions/
    registry.py            → ExtensionDecoratorRegistry (auto-decorator dispatch)
```

---

## 14. Known Technical Subtleties (Smells to Address)

### 14.1 Frozen Dataclass Provider Injection (G-3)

`Instrument` is a frozen dataclass. Providers are injected post-construction via `object.__setattr__`. **Phase 5 fix**: Add `with_providers()` method that cleanly sets providers.

### 14.2 Future Is Not a Dataclass

`Future(Instrument)` has `underlying` and `contract_size` as class-level annotations, not dataclass fields. Set via `object.__setattr__` after construction. **Phase 5 fix**: Either make `Future` a proper dataclass or document as accepted trade-off.

### 14.3 Duplicate depth() in Protocols

Both `InstrumentDataProvider` and `DepthProvider` define `depth()`. Same signature — a single implementation satisfies both. **Do NOT** define `depth()` twice in the same class.

### 14.4 PaperGateway Streaming Is Async

`PaperStreaming` uses `async` methods. `BrokerAdapter.subscribe()` is sync. PaperAdapter uses a no-op stub. **Phase 6**: Async bridge.

### 14.5 DhanGateway depth() Ignores levels

`DhanGateway.market_data.depth()` ignores the `levels` parameter. The decorator chain handles this, but the adapter should log a warning.

---

## 15. Completed Work (Phases 6-7)

| Phase | Description | What Was Done |
|-------|-------------|---------------|
| 6 | Async Bridge & Streaming | ✅ Fixed async disconnect handling in BrokerSession.close() — properly awaits async coroutines via event loop or asyncio.run(). MarketDataContext.subscribe() already bridges sync→async for StreamingPort.
| 7 | Multi-Leg Order Composition | ✅ All 5 strategies implemented (VerticalSpread, Straddle, Strangle, IronCondor, ComboOrder). Fixed net_premium to be per-unit (not multiplied by quantity). 22 strategy tests passing.

## 16. Future Work (Phases 8+)

| Phase | Description | Priority |
|-------|-------------|----------|
| 8 | Portfolio-level position builder using Instruments | Medium |
| 9 | Historical data streaming (replay via streaming protocol) | Low |
| 10 | Real-time Greeks calculator with live delta/gamma/theta | Low |
| 11 | WebSocket Pool auto-decorator dispatch for streaming | Low |

---

## 16. Quick Reference

```bash
	# Run all Phase 1-7 tests
	python -m pytest brokers/tests/unit/test_decorator_pipeline.py \
	  brokers/tests/unit/test_factory_providers.py \
	  brokers/tests/unit/test_broker_adapter.py \
	  brokers/tests/unit/test_option_chain.py \
	  brokers/tests/unit/test_extension_registry.py \
	  brokers/tests/unit/test_phase5_cleanup.py \
	  brokers/tests/unit/test_option_strategies.py \
	  brokers/tests/unit/test_market_context.py \
	  -v --tb=short

	# Architecture guardrails
	python -m pytest brokers/tests/unit/test_architecture.py \
	  -m architecture -v --tb=short

	# Full unit suite
	python -m pytest brokers/tests/unit/ --tb=short -q
```
