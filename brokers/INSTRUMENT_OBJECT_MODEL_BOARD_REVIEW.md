# Instrument Object Model — Elite Board Review & Plan

> **Board:** R.C. Martin · E. Evans · M. Fowler · G. Young · V. Vernon · K. Beck · M. Feathers · Dr. V. Subramaniam
> **Scope:** `brokers/` (adapters) + `inc_trade/` (domain/market/ports/services/extensions) — the actual home of the instrument-centric code
> **Mandate:** Treat Instrument (Equity/Option/Future/Spot/Index) as a rich object with state + behavior (quotes, historical data, live subscriptions), extended per-broker via Decorator/Composition (Dhan depth-20/200, Upstox depth-30, …), with `OptionChain` composed of Instrument objects — **no gateway indirection**, objects expose the API directly.

---

## 0. Correction to prior planning docs

`brokers/MASTER_INSTRUMENT_CENTRIC_PLAN.md`, `ELITE_REVIEW_BOARD_PLAN.md`, and `ARCHITECTURE_BLUEPRINT_V3.md` describe `market/instrument.py`, `market/context.py`, etc. as if they lived under `brokers/`. **They don't.** `brokers/` today contains only adapters (`dhan/`, `upstox/`, `paper/`) plus these planning docs. The instrument-centric domain model those docs describe was actually built under the sibling package **`inc_trade/`** (`inc_trade/market/`, `inc_trade/domain/`, `inc_trade/ports/`, `inc_trade/services/`, `inc_trade/extensions/`). Any plan that references `brokers/market/...` is stale — treat `inc_trade/` as the real "other folder." This review is grounded in what actually exists there today, not in the aspirational paths from earlier docs.

---

## 1. What already exists (verified by reading code, not docs)

| Piece | File | Verdict |
|---|---|---|
| `Instrument` frozen dataclass, content-based `is_equity/is_future/is_option/is_index` | `inc_trade/market/instrument.py` | **Good domain modeling** (Evans would approve of behavior-rich value object) |
| `Equity`, `Option`, `Future`, `Index` subclasses | `inc_trade/market/types/{equity,option,future,index}.py` | Subtype hierarchy exists — **Spot/Underlying is missing** |
| `Instrument.quote()/depth()/ohlcv()/subscribe()/option_chain()` | `instrument.py:264-403` | Methods live *on* the object ✅, but every one of them does `ctx = self._context or self._delegate_context; ctx.quote(...)` |
| `MarketDataContext` / `InstrumentHandle` | `inc_trade/market/context.py` | This **is** a gateway by another name — a session facade the Instrument must reach through for every operation. Worse: `InstrumentHandle` is a *second* delegation layer wrapping `Instrument` that re-implements `quote()/depth()/ohlcv()/option_chain()/subscribe()` by calling back into the same `MarketDataContext` — both classes proxy the identical call, so a caller holding an `InstrumentHandle` pays two indirections to reach one port method. |
| `BrokerCapabilities.supports(feature)` | `inc_trade/domain/capabilities.py:85` | `return bool(getattr(self, f"supports_{feature}", False))` — string-keyed reflection over boolean fields, not a polymorphic Strategy/capability object. Fine for "can I?" checks; wrong tool for "give me the depth-200 behavior," which is why depth ended up needing a separate registry/extension path instead of composing naturally. |
| `DepthExtension` Protocol (Strategy, not Decorator) | `inc_trade/extensions/depth.py` | Broker-agnostic depth capability contract — good idea, wrong pattern for "wrap the base behavior" |
| `Extension` marker Protocol + `ExtensionRegistryPort` / `DictExtensionRegistry` | `inc_trade/extensions/base.py`, `inc_trade/ports/extension_registry.py` | A typed **Service Locator** (`registry.resolve(broker_id, ExtType)`) — better than `hasattr()`, still indirection through a registry rather than composition on the object |
| `OptionChain` | `inc_trade/domain/entities.py:414` | `@dataclass(frozen=True)` holding `strikes: tuple[OptionStrike, ...]` — **flat data, not composed of `Option` instrument objects.** No behavior (`atm()`, `synthetic_future()`, `iter_calls()`…). |
| Dhan `DhanDepth20Stream` / `DhanDepth200Stream` | `brokers/adapters/dhan/depth20.py`, `depth200.py` | Concrete streaming classes, both subclass `BinaryDepthFeed` — broker-owned, never touch `Instrument` |
| Upstox depth (30-level) | `brokers/adapters/upstox/market_data.py`; `capabilities.py:26-27,56` | No dedicated depth20/200 files — depth is folded into `market_data.py`, capability flags say `max_depth_levels=30` |
| Dhan-only extension protocols (`SuperOrderProvider`, `SliceOrderProvider`, …) | `brokers/adapters/dhan/extensions/protocols.py` (new, staged) | Confirms the intended pattern is **Protocol + registry resolve**, not Decorator-wrapping of the instrument |

**Net assessment:** ~60% of the requested object model is already built (rich subtypes, content-based type detection, capability protocols). The two structural gaps that matter are:

1. **Every instrument method is a one-line proxy to a context/session object** (`ctx.quote(self.symbol, ...)`). That context is functionally a gateway — it just isn't named one. It also means an `Instrument` is inert until something else injects `_context` into it via `object.__setattr__`, which is a mutable-backdoor into a frozen dataclass (Feathers: "this is a seam you'll regret — nothing stops two callers from re-stamping `_context` on a shared instance").
2. **`OptionChain` is anemic data, not composition of `Instrument`/`Option` objects.** The user explicitly wants option chain built from Stock/Option objects via composition, with chain-level behavior.

---

## 2. Target design

### 2.1 Instrument hierarchy (unchanged shape, corrected internals)

```
Instrument (ABC)                         # state: symbol, exchange, segment, lot_size, tick_size, isin
├── Equity                               # + sector, isin-backed corp actions
├── Future(Instrument)                   # + expiry, underlying
├── Option(Future)                       # + strike, option_type, underlying  (Option IS-A derivative-with-expiry)
├── Spot(Instrument)                     # NEW — index/underlying without a tradeable contract (NIFTY, cash-VIX)
└── Index(Instrument)                    # existing — kept distinct from Spot (index ≠ always spot-tradeable)
```

Every instrument is constructed with a **`MarketDataProvider`** (a small object, not a session/context/gateway):

```python
class MarketDataProvider(Protocol):
    def quote(self, instrument: Instrument) -> Quote: ...
    def depth(self, instrument: Instrument, mode: str = "depth_5") -> MarketDepth: ...
    def ohlcv(self, instrument: Instrument, start, end, resolution) -> list[Candle]: ...
    def subscribe(self, instrument: Instrument, callback) -> StreamHandle: ...
```

`Instrument.__init__` takes `provider: MarketDataProvider` as a constructor argument (composition, set once, immutable) instead of a post-hoc `object.__setattr__(instrument, "_context", ctx)`. This is the same capability, minus the mutable-backdoor smell:

```python
reliance = Equity("RELIANCE", "NSE", provider=dhan_provider)
reliance.quote()        # -> provider.quote(self)
reliance.depth()        # -> provider.depth(self, mode="depth_5")
```

**Why this isn't "a gateway with extra steps":** a gateway/session centralizes *all* broker operations (orders, funds, auth, market data) behind one wide object that every domain entity must ask permission from. `MarketDataProvider` is narrow (4 methods), owned per-instrument, replaceable per-instrument (a `Future` and an `Equity` from different brokers can each hold their own provider), and injected at construction — it's the classic **Bridge pattern** (GoF), separating "what an Instrument is" from "how its data is fetched." Fowler: this is the difference between a Facade (gateway) and a Strategy — same call count, opposite coupling direction.

### 2.2 Broker-specific extension via Decorator, not Service Locator

Depth-20/200 (Dhan) and depth-30 (Upstox) are **decorators around a `MarketDataProvider`**, each adding one capability without the base provider or the `Instrument` knowing about it:

```python
class BaseMarketDataProvider:                       # broker's plain 5-level depth
    def depth(self, instrument, mode="depth_5"): ...

class DepthDecorator(MarketDataProvider):             # abstract decorator
    def __init__(self, wrapped: MarketDataProvider): self._wrapped = wrapped
    def quote(self, i): return self._wrapped.quote(i)
    def ohlcv(self, i, *a): return self._wrapped.ohlcv(i, *a)
    def subscribe(self, i, cb): return self._wrapped.subscribe(i, cb)

class DhanDepth20Decorator(DepthDecorator):
    def depth(self, instrument, mode="depth_5"):
        if mode == "depth_20":
            return self._depth20_stream.get_depth(instrument.symbol, instrument.exchange)
        return super().depth(instrument, mode)

class DhanDepth200Decorator(DepthDecorator):
    def depth(self, instrument, mode="depth_5"):
        if mode == "depth_200":
            return self._depth200_stream.get_depth(instrument.symbol, instrument.exchange)
        return super().depth(instrument, mode)
```

Wiring per broker (in the adapter's factory, e.g. `brokers/adapters/dhan/factories/streaming_factory.py`):

```python
provider = BaseMarketDataProvider(dhan_client)
provider = DhanDepth20Decorator(provider, depth20_stream=DhanDepth20Stream(...))
provider = DhanDepth200Decorator(provider, depth200_stream=DhanDepth200Stream(...))
# instrument.depth(mode="depth_200") now resolves through the decorator chain
```

Upstox gets its own two-line stack (`UpstoxDepth30Decorator`), no shared inheritance with Dhan's decorators — each broker composes only the depths it actually has. This directly replaces the existing `DepthExtension` + `ExtensionRegistryPort.resolve()` indirection: no registry lookup at call time, no `isinstance`/`resolve` branch in `Instrument`, just a decorator chain built once at connect-time. `ExtensionRegistryPort` can stay for genuinely orthogonal broker features (Dhan `SuperOrderProvider`, `SliceOrderProvider` — order-side, not instrument-side), which is a legitimate use of Service Locator since those aren't per-instrument state.

### 2.3 OptionChain as composition of Instrument objects

Replace the flat `OptionChain` dataclass with a composite that *holds* `Option` instances (which are themselves `Instrument`s, each with their own provider/quote/depth):

```python
@dataclass(frozen=True)
class OptionStrikePair:
    strike: Decimal
    call: Option | None      # Option IS-A Instrument — full quote()/depth()/greeks() available
    put: Option | None

class OptionChain:
    """Composite over Option instruments for one underlying+expiry."""
    def __init__(self, underlying: Instrument, expiry: str, pairs: Sequence[OptionStrikePair]):
        self._underlying = underlying
        self._expiry = expiry
        self._pairs = tuple(sorted(pairs, key=lambda p: p.strike))

    def calls(self) -> list[Option]: ...
    def puts(self) -> list[Option]: ...
    def atm(self) -> OptionStrikePair: ...          # nearest strike to underlying.ltp()
    def strikes_within(self, pct: float) -> list[OptionStrikePair]: ...
    def max_pain(self) -> Decimal: ...               # chain-level analytics using .oi() on each leg
    def synthetic_future(self, strike: Decimal) -> Decimal: ...  # call - put + strike
    def subscribe_all(self, callback) -> list[StreamHandle]:     # bulk-subscribe every leg
        return [leg.subscribe(callback) for pair in self._pairs for leg in (pair.call, pair.put) if leg]
```

`Instrument.option_chain(expiry)` builds this by asking the same `MarketDataProvider` for the raw strike list, then wrapping each row as a real `Option(...)` instrument sharing the parent's provider — no separate `OptionsService`/`OptionsPort` round trip needed once the chain is materialized; each leg is independently live.

### 2.4 Where the existing pieces land

| Existing file | Action |
|---|---|
| `inc_trade/market/instrument.py` | Change `_context`/`_delegate_context` backdoor → constructor-injected `provider: MarketDataProvider`. Keep all the `is_*`/`days_to_expiry`/`validate_*` behavior as-is (Evans-approved). |
| `inc_trade/market/types/*.py` | Keep `Equity`, `Future`, `Option`, `Index`; add `Spot`. |
| `inc_trade/market/context.py` (`MarketDataContext`, `InstrumentHandle`) | **Delete.** Its only job — routing `symbol/exchange` calls to a provider — is now the constructor-injected `MarketDataProvider` on each instrument. `SimpleStreamHandle`/`SimpleSubscriptionHandle` survive as the return type of `subscribe()`. |
| `inc_trade/extensions/depth.py` (`DepthExtension` Protocol) | Superseded by the `DepthDecorator` chain (§2.2). Keep the Protocol only as the interface a decorator must satisfy for `mode` dispatch, drop the registry-resolve call path. |
| `inc_trade/ports/extension_registry.py` | Keep — repurpose strictly for non-instrument, broker-account-level extensions (super/slice orders, margin, alerts). Not for depth. |
| `inc_trade/domain/entities.py::OptionChain` | Replace with the composite class in §2.3; keep `OptionStrike`/`OptionChain` dataclass names only as the wire-level DTO returned by the broker HTTP layer, renamed `OptionChainDTO`, consumed once by the factory that builds the real `OptionChain`. |
| `inc_trade/services/options_service.py` | Becomes the one-time DTO→domain-object assembly step (build `Option` instruments + `OptionChain` from `OptionsPort.get_option_chain()`), not a pass-through called on every access. |
| `brokers/adapters/dhan/depth20.py`, `depth200.py` | Unchanged internals; only consumed by a new `DhanDepth20Decorator`/`DhanDepth200Decorator` in `brokers/adapters/dhan/extensions/`. |
| `brokers/adapters/upstox/market_data.py` | Extract its depth-30 path into an `UpstoxDepth30Decorator` alongside a plain `BaseMarketDataProvider` for Upstox. |
| `brokers/adapters/dhan/extensions/protocols.py` | Keep as-is — correct home for `SuperOrderProvider`/`SliceOrderProvider`/etc., which are **not** part of this instrument-object redesign. |

---

## 3. Board findings, ranked

0. **[High] `InstrumentHandle` is a redundant second gateway layer.** `context.py:573` wraps an `Instrument` and re-implements every market-data method purely to call back into the same `MarketDataContext` the wrapped `Instrument` already holds — confirmed via full read of `context.py`: both classes proxy the identical port call. A repo-wide grep for `Decorator|Composite|Strategy` class names found exactly one hit (`ReconnectStrategy`, unrelated to instruments/depth, and itself flagged in `MASTER_BLUEPRINT_V2.md:77` as not yet true Strategy pattern) — confirming no Decorator/Composite exists anywhere today for this problem. → Deleted outright in P4; `Instrument` (holding its own `provider`) is sufficient, no handle wrapper needed.
1. **[High] Mutable backdoor into a frozen dataclass.** `object.__setattr__(instrument, "_context", ctx)` after construction (`instrument.py:246-260`) breaks the frozen-dataclass invariant and creates a race if the same `Instrument` value is shared across threads/brokers before the context is stamped. → Fixed by constructor injection (§2.1).
2. **[High] `OptionChain` has no behavior and doesn't compose `Instrument`.** Chain-level questions (ATM strike, synthetic future, max pain) currently have nowhere to live; callers reimplement them ad hoc against the flat tuple. → Fixed by §2.3.
3. **[Medium] Depth capability resolved via registry lookup at call time, not decided once at connect-time.** `ExtensionRegistryPort.resolve()` on every `.depth()` call is an extra indirection with no compile-time guarantee the mode is supported; `DepthExtension.supported_depth_modes` has to be checked manually by the caller. → Fixed by Decorator chain built once in the broker factory (§2.2); `mode` dispatch becomes an ordinary method-resolution chain.
4. **[Low] `Spot` type is missing** — cash index / underlying-without-a-contract (e.g., NIFTY spot vs. NIFTY futures) has no home; currently forced into `Index` or `Equity` by convention. → Add `Spot(Instrument)`.
5. **[Low] Thirteen overlapping planning docs in `brokers/`** (`MASTER_PLAN.md`, `MASTER_BLUEPRINT_V2.md`, `MASTER_INSTRUMENT_CENTRIC_PLAN.md`, `ARCHITECTURE_BLUEPRINT_V3.md`, `MIGRATION_PLAN.md`, `REFACTOR_PLAN.md`, `PHASE3_ACTION_PLAN.md`, …) reference paths (`brokers/market/...`) that don't exist. Recommend consolidating to this document + one living `HANDOFF.md` once the migration below lands, and archiving the rest.

---

## 4. Migration plan

| Phase | Work | Depends on |
|---|---|---|
| **P1 — Provider seam** | Define `MarketDataProvider` Protocol in `inc_trade/ports/market_data_provider.py`. Change `Instrument.__init__` to accept `provider`, remove `_context`/`_delegate_context`/`object.__setattr__` backdoor. Update `Equity/Future/Option/Index` subclasses (no signature change needed — inherited). Add `Spot`. | none |
| **P2 — Decorator depth** | Write `BaseMarketDataProvider` (plain 5-level) per broker. Write `DhanDepth20Decorator`, `DhanDepth200Decorator` in `brokers/adapters/dhan/extensions/`; `UpstoxDepth30Decorator` in `brokers/adapters/upstox/extensions/`. Wire the decorator stack in each broker's `factories/streaming_factory.py` (Dhan) / equivalent (Upstox). | P1 |
| **P3 — OptionChain composite** | Add `OptionChain`/`OptionStrikePair` composite classes to `inc_trade/market/`. Rename current dataclass to `OptionChainDTO` in `domain/entities.py`. Update `OptionsService` to assemble `Option` instruments (sharing the underlying's provider) from the DTO. | P1 |
| **P4 — Delete gateway remnants** | Remove `MarketDataContext`/`InstrumentHandle` from `inc_trade/market/context.py`. Update `connect()`/bootstrap in `brokers/__init__.py` to build a provider (with decorators applied) and hand it to `Instrument` constructors directly, instead of building a context object. | P2, P3 |
| **P5 — Extension registry narrowing** | Restrict `ExtensionRegistryPort` usage to account/order-level extensions only (`SuperOrderProvider`, `SliceOrderProvider`, `MarginProvider`, `AlertsProvider`). Remove `DepthExtension` Protocol resolve-path. | P2 |
| **P6 — Doc consolidation** | Archive `MASTER_PLAN.md`, `MASTER_BLUEPRINT_V2.md`, `ARCHITECTURE_BLUEPRINT_V3.md`, `MIGRATION_PLAN.md`, `REFACTOR_PLAN.md`, `PHASE3_ACTION_PLAN.md`, `MASTER_INSTRUMENT_CENTRIC_PLAN.md` under `brokers/archive/` (pattern already used at repo root `archive/`). Keep this file + `HANDOFF.md` as the live references. | P1-P5 |

## 5. Fitness functions to add

- `test_instrument_is_frozen_no_backdoor_setattr` — fails if any code path calls `object.__setattr__` on an `Instrument` after construction outside `__init__`.
- `test_depth_decorator_chain_resolves_deepest_mode` — Dhan instrument with both decorators applied returns `depth_200` data for `mode="depth_200"` and falls through to base for `mode="depth_5"`.
- `test_option_chain_legs_are_live_instruments` — every `OptionChain.calls()/puts()` entry is an `Option` instance whose `.quote()` works independently.
- `test_no_gateway_facade_in_market_package` — architecture test asserting `MarketDataContext`/`InstrumentHandle` classes are absent from `inc_trade/market/` after P4.

## 6. Board verdict

**Approved to proceed**, phased P1→P6. The domain modeling instinct already in the codebase (content-based type detection, subtype hierarchy, capability protocols) is sound and should be kept; the two real defects are the mutable-backdoor context injection and the anemic `OptionChain`. Both are targeted, low-blast-radius changes — this is a refinement of working code, not a rewrite.
