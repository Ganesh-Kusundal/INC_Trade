# Instrument Object Model Architecture — Transformation Blueprint

**Date:** 2026-07-06
**Branch:** `audit/architectural-review-july2026`
**Phase:** 2 (BrokerAdapter Protocol & Gateway Elimination)

---

## 1. Philosophy: Instrument-Centric Design

> **"Instruments are the atoms of trading. Everything else — brokers, gateways, adapters — is infrastructure."**

The old architecture was **broker-centric**: you got a `BrokerGateway`, asked it for `.market_data`, then called methods with string symbols. The new architecture is **instrument-centric**: you get an `Instrument` object and call methods on it directly.

```python
# OLD (broker-centric)
gw = DhanGateway(client_id="123", access_token="abc")
quote = gw.market_data.quote("RELIANCE", "NSE")
order = gw.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)

# NEW (instrument-centric)
adapter = DhanAdapter(client_id="123", access_token="abc")
inst = adapter.instrument("RELIANCE", "NSE")
quote = inst.quote()
order = inst.buy(qty=10)
```

---

## 2. Core Abstraction: Instrument as Object

### 2.1 Identity

`Instrument` is a **frozen dataclass** with identity based on `(symbol, exchange)`. It is immutable for hashing, dict-key safety, and thread safety.

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

### 2.2 Type Detection (Content-Based)

Type is detected from fields, not from a type flag:

| Method | Detection Logic |
|--------|----------------|
| `is_equity()` | No option_type, no expiry, no strike, not derivative exchange |
| `is_future()` | Derivative exchange + expiry, no strike/option_type |
| `is_option()` | Derivative exchange + expiry + strike + option_type (CE/PE) |
| `is_index()` | Symbol in index registry |

### 2.3 Subclass Hierarchy

```
Instrument (frozen dataclass)  ← base entity
    ├── Equity    → fundamentals(), dividend_yield, pe_ratio, market_cap
    ├── Future    → underlying, contract_size, open_interest(), basis()
    ├── Option    → greeks(), option_chain()
    └── Index     → (passthrough, no extra behavior)
```

Subclasses add domain-specific methods without breaking the identity contract.

### 2.4 State & Behavior

Every `Instrument` has:

**Market Data:**
- `inst.quote()` → `Quote` (rich value object with LTP, bid/ask, volume, OI, VWAP, etc.)
- `inst.ltp()` → `Decimal` (last traded price)
- `inst.depth(levels=5)` → `MarketDepth` (order book with configurable levels)
- `inst.ohlcv(start, end, resolution)` → `list[Candle]` (historical OHLCV)
- `inst.subscribe(callback)` → `StreamHandle` (live tick subscription)
- `inst.unsubscribe()` → `None`

**Trading:**
- `inst.buy(qty, order_type, price, ...)` → `OrderResponse`
- `inst.sell(qty, order_type, price, ...)` → `OrderResponse`

**Observability:**
- `inst.attach(observer)` → observer pattern for quote ticks
- `inst.detach(observer)` → remove observer
- `inst.capabilities()` → `InstrumentCapabilities`
- `inst.supports_depth(levels)` → `bool`

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

`BrokerAdapter` is a `@runtime_checkable` Protocol that combines all five provider protocols. An adapter that satisfies `BrokerAdapter` can be injected directly into an `Instrument` as every provider.

### 3.2 Default `instrument()` Factory Method

`BrokerAdapter` provides a concrete `instrument()` method that creates `Instrument` objects with the adapter wired in:

```python
class BrokerAdapter(Protocol):
    def instrument(self, symbol, exchange, **kwargs) -> Instrument:
        return InstrumentFactory.create(
            symbol=symbol,
            exchange=exchange,
            provider=self,
            depth_provider=self,
            historical_provider=self,
            streaming_provider=self,
            order_provider=self,
            **kwargs,
        )
```

### 3.3 Adapter Lifecycle

```python
adapter = DhanAdapter(client_id="123", access_token="abc")
adapter.connect()

inst = adapter.instrument("RELIANCE", "NSE", apply_depth=200)
quote = inst.quote()
depth = inst.depth(200)
order = inst.buy(qty=10)

adapter.disconnect()
```

### 3.4 Broker-Specific Extensions

Adapters override `instrument()` to provide broker-specific defaults:

| Adapter | Default `apply_depth` | Max Levels |
|---------|----------------------|------------|
| `DhanAdapter` | 200 | 200 |
| `UpstoxAdapter` | 30 | 30 |
| `PaperAdapter` | 5 | 5 |

---

## 4. Decorator Pipeline

### 4.1 Stacking Model

```
LoggedDecorator
    └── CachedDecorator
        └── Depth200Decorator
            └── DhanInstrument (base with DhanAdapter as provider)
```

Each decorator extends `InstrumentDecorator`, which delegates all unknown attributes to `_wrapped` via `__getattr__`. Decorators override only the methods they extend.

### 4.2 Depth Decorators

| Decorator | Levels | Method Added | Broker |
|-----------|--------|-------------|--------|
| `Depth20Decorator` | 20 | `depth_20()` | Dhan |
| `Depth30Decorator` | 30 | `depth_30()` | Upstox |
| `Depth200Decorator` | 200 | `depth_200()` | Dhan (inherits depth_20) |

### 4.3 Cross-Cutting Decorators

| Decorator | Purpose | TTL/Config |
|-----------|---------|------------|
| `CachedDecorator` | Cache quote/LTP with TTL | `ttl_seconds=2.0` |
| `LoggedDecorator` | Log all method calls | via standard logging |

### 4.4 Composition Helpers

```python
from inc_trade.market.decorators import with_depth, with_cache, with_logging

inst = with_logging(
    with_cache(
        with_depth(base_inst, levels=200, depth_provider=provider)
    )
)
```

---

## 5. OptionChain as Composition

### 5.1 Object Graph

```
InstrumentOptionChain
    ├── underlying: Instrument  (the underlying stock/index)
    ├── expiry: str
    ├── spot: Decimal
    └── strikes: tuple[InstrumentOptionStrike]
            ├── strike: Decimal
            ├── call: InstrumentOptionLeg
            │       ├── instrument: Instrument  (the call option)
            │       ├── ltp, oi, volume, iv, delta
            │       └── greeks() -> dict
            └── put: InstrumentOptionLeg
                    ├── instrument: Instrument  (the put option)
                    ├── ltp, oi, volume, iv, delta
                    └── greeks() -> dict
```

### 5.2 Behavioral Methods

- `chain.max_pain_strike` — max pain calculation
- `chain.pcr` — put-call ratio (OI-based)
- `chain.itm_strikes("CE")` — in-the-money strikes
- `chain.otm_strikes("PE")` — out-of-the-money strikes
- `chain.nearest_strikes(n=5)` — strikes nearest to spot

### 5.3 Chaining

```python
adapter = DhanAdapter(...)
inst = adapter.instrument("NIFTY", "NSE")
chain = inst.option_chain("2025-01-30")
nearest = chain.nearest_strikes(3)
atm_call = nearest[0].call
atm_call.instrument.buy(qty=25)  # → OrderResponse
atm_put  = nearest[0].put
atm_put.instrument.sell(qty=25)  # → OrderResponse
```

---

## 6. Migration: Gateway → Adapter

### 6.1 Coexistence Period

Both `BrokerGateway` and `BrokerAdapter` coexist. `BrokerGateway` has a deprecation warning. New code should use `BrokerAdapter`.

| Aspect | BrokerGateway | BrokerAdapter |
|--------|---------------|---------------|
| Pattern | Property access (`gw.orders`) | Direct method (`adapter.quote()`) |
| Injection | Via service locator / context | Directly into `Instrument` |
| Lifecycle | `close()` | `connect()` / `disconnect()` |
| Deprecation | ⚠️ Deprecated | ✅ Current |

### 6.2 Wrapping Strategy

Each adapter wraps the existing gateway:

```python
class DhanAdapter(BrokerAdapter):
    def __init__(self, client_id, access_token, **kwargs):
        self._gw = None
        self._gateway_kwargs = kwargs
        ...

    def connect(self, **credentials):
        from brokers.adapters.dhan.gateway import DhanGateway
        self._gw = DhanGateway(
            client_id=credentials.get("client_id"),
            access_token=credentials.get("access_token"),
            **self._gateway_kwargs,
        )

    def quote(self, symbol, exchange="NSE"):
        return self._gw.market_data.quote(symbol, exchange)
```

---

## 7. Provider Injection Chain

### 7.1 How `Instrument.quote()` Resolves

```
inst.quote()
    → _provider.quote(symbol, exchange)   [if _provider is set]
    → _context.quote(symbol, exchange)    [fallback for legacy path]
    → RuntimeError                        [if neither]
```

### 7.2 How `Instrument.depth()` Resolves

```
inst.depth(levels=200)
    → _depth_provider.depth(symbol, exchange, levels)   [dedicated depth provider]
    → _provider.depth(symbol, exchange, levels)          [fallback to general provider]
    → _context.depth(symbol, exchange)                   [fallback to legacy context]
```

### 7.3 How `Instrument.buy()` Resolves

```
inst.buy(qty=10)
    → _order_provider.place_order(...)   [dedicated order provider]
    → _provider.place_order(...)          [fallback to general provider]
    → RuntimeError                        [if neither]
```

---

## 8. Known Technical Subtleties

### 8.1 Frozen Dataclass Provider Injection

Since `Instrument` is a frozen dataclass, providers cannot be set in `__init__`. They are injected post-construction via `object.__setattr__`. This is a known smell (G-3) to be addressed in Phase 5 via a `with_providers()` method.

### 8.2 `Future` Is Not a Dataclass

`Future(Instrument)` has `underlying` and `contract_size` as class-level annotations, not dataclass fields. They are set via `object.__setattr__` after construction. This is safe because `Future` doesn't add its own `__init__`.

### 8.3 Duplicate `depth()` in Protocols

Both `InstrumentDataProvider` and `DepthProvider` define `depth()`. Since they have identical signatures, a single implementation satisfies both. Do NOT define `depth()` twice in the same adapter class.

### 8.4 PaperGateway Streaming Port Is Async

`PaperStreaming` uses `async` methods. `BrokerAdapter.subscribe()` is sync. The `PaperAdapter` handles this with a no-op stub.

---

## 9. File Map

```
inc_trade/
  market/
    instrument.py         → Base Instrument entity (frozen dataclass)
    types/
      equity.py           → Equity(fundamentals, dividend_yield, pe_ratio)
      future.py           → Future(underlying, contract_size, open_interest, basis)
      option.py           → Option(greeks, option_chain)
      index.py            → Index(passthrough)
    decorators.py          → InstrumentDecorator base + with_depth/with_cache/with_logging
    depth_decorators.py    → Depth20Decorator, Depth30Decorator, Depth200Decorator
    cache_decorator.py     → CachedDecorator(TTL-based caching)
    log_decorator.py       → LoggedDecorator(method-call logging)
    factory.py             → InstrumentFactory(type detection + provider injection + decorator pipeline)
    option_chain.py        → InstrumentOptionChain(Instrument composition for options)
    context.py             → MarketDataContext(legacy facade)

  ports/
    providers.py           → InstrumentDataProvider, DepthProvider, HistoricalDataProvider,
                             StreamingDataProvider, OrderProvider (protocols)
    broker.py              → BrokerGateway(deprecated protocol)

  adapters/
    __init__.py            → Exports BrokerAdapter
    broker_adapter.py      → BrokerAdapter(combined protocol)
    dhan.py                → DhanAdapter(max_levels=200)
    upstox.py              → UpstoxAdapter(max_levels=30)  [NEW]
    paper.py               → PaperAdapter(max_levels=5)    [NEW]
```

---

## 10. Validation Criteria

### 10.1 Protocol Satisfaction

```python
adapter = DhanAdapter(...)
assert isinstance(adapter, BrokerAdapter)        # Structural typing
assert isinstance(adapter, InstrumentDataProvider)
assert isinstance(adapter, DepthProvider)
assert isinstance(adapter, HistoricalDataProvider)
assert isinstance(adapter, StreamingDataProvider)
assert isinstance(adapter, OrderProvider)
```

### 10.2 Adapter Lifecycle

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

### 10.3 Pre-Connect Guard

```python
adapter = DhanAdapter()  # not connected
with pytest.raises(RuntimeError, match="not connected"):
    adapter.quote("RELIANCE", "NSE")
```

### 10.4 Architecture Boundary

`import inc_trade.adapters.dhan` should not transitively import `brokers.adapters.dhan.gateway` at import time (only at `connect()` call time).
