# Broker SDK — Architecture Review & Redesign Blueprint

**Prepared by:** Architecture Review Board
**Date:** July 2026
**Status:** Draft for Review
**Classification:** Foundation Architecture Document

---

## Table of Contents

- [Phase 1 — Architecture Review](#phase-1--architecture-review)
- [Phase 2 — Domain Model](#phase-2--domain-model)
- [Phase 3 — Package Structure](#phase-3--package-structure)
- [Phase 4 — Public SDK API](#phase-4--public-sdk-api)
- [Phase 5 — Internal Architecture](#phase-5--internal-architecture)
- [Phase 6 — Event Flow](#phase-6--event-flow)
- [Phase 7 — Broker Provider Framework](#phase-7--broker-provider-framework)
- [Phase 8 — Testing Architecture](#phase-8--testing-architecture)
- [Phase 9 — Implementation Roadmap](#phase-9--implementation-roadmap)
- [Phase 10 — Future Trading Operating System](#phase-10--future-trading-operating-system)

---

## Phase 1 — Architecture Review

### 1.1 Critique of the Current Concept

Your proposal centers on making **Instrument** the primary Aggregate Root with rich
behavior: `history()`, `quote`, `depth`, `subscribe()`, `buy()`, `sell()`,
`option_chain()`, `statistics()`. You want "intelligent domain objects" that feel
like interacting with financial entities, not broker APIs.

This is an ambitious and intuitively appealing vision. Let us dissect it critically.

#### Strengths of Your Proposal

| # | Strength | Why It Matters |
|---|----------|---------------|
| 1 | **Instrument-centric, not broker-centric** | Correct instinct. StockSharp's `Security`, QuantConnect's `Symbol`/`Security`, and IB's `Contract` all place the instrument at the center. Code that says `instrument.history()` is more readable than `broker.get_history(symbol, exchange)`. |
| 2 | **Provider abstraction over Broker** | Excellent. Decoupling data/execution source from "broker" allows CSV, Replay, Paper, Yahoo, FIX providers to coexist. This is exactly what QuantConnect does with `IDataQueueHandler` separate from `IBrokerage`. |
| 3 | **Extensions for broker-specific features** | Right approach. `instrument.extensions.depth20` is cleaner than `if broker == "dhan"`. Your existing `CapabilitySurface` manifest and `extended()` facade already implement this pattern well. |
| 4 | **OptionChain as Aggregate Root** | Correct. An option chain is a coherent aggregate — it owns its options, and every option is itself an instrument. This maps naturally to how exchanges structure derivatives. |
| 5 | **Composition over inheritance for instrument types** | Correct. Equity, Future, Option, ETF, Index should NOT be subclasses of Instrument. They should be Instrument + type-specific Value Objects composed in. Inheritance trees for instrument types create combinatorial explosion (Is a currency future an Equity or a Currency or a Future?). |
| 6 | **Immutable where appropriate** | Good principle for the identity layer. Your existing frozen dataclasses are already on the right track. |

#### Weaknesses and Risks

**W1 — Instrument as God Object (CRITICAL)**

Your proposed Instrument exposes:

- **State:** Quote, Historical Series, Market Depth, Subscription State, Metadata, Exchange, Market Session, Statistics, Corporate Actions, Broker Capabilities, Extensions
- **Behavior:** history(), quote, depth, subscribe(), unsubscribe(), refresh(), snapshot(), buy(), sell(), option_chain(), statistics()

This is **11 state responsibilities and 10 behavioral responsibilities** in a single
class. By any measure — SRP, cognitive load, test surface, coupling — this is a God
Object. It violates:

- **Single Responsibility Principle:** Instrument would be responsible for identity, market data retrieval, historical data retrieval, subscription management, order execution, option chain construction, and statistics computation.
- **Interface Segregation Principle:** A consumer that only wants `history()` would depend on a class that also exposes `buy()`, `subscribe()`, `depth`, etc.
- **Open/Closed Principle:** Every new data type (e.g., Greeks, IV surface, PCR) would require modifying the Instrument class.

**Reference comparison:** Neither StockSharp nor QuantConnect makes Security/Symbol
own behavior. In StockSharp, the `Connector` handles all IO. In LEAN, `IBrokerage`
handles execution and `IDataQueueHandler` handles data. The Security/Symbol is an
identity + state holder, not an actor.

**W2 — buy()/sell() on Instrument Couples Data and Execution (HIGH)**

This is the most dangerous design decision. Market data and order execution have
fundamentally different:

- **Reliability requirements:** Market data can be lossy (dropped ticks are tolerable). Order execution cannot be lossy (a lost order is a financial incident).
- **Threading models:** Market data is pub/sub (many consumers, fire-and-forget). Order execution is request/response with confirmation, reconciliation, and idempotency.
- **Security/risk concerns:** Order execution requires risk gating, kill switches, and audit trails. Market data does not.
- **Lifecycle:** A market data subscription lives as long as the consumer wants data. An order has a multi-state lifecycle (pending → submitted → partial fill → filled/cancelled/rejected).

Your existing codebase already recognizes this separation: `TradingPort` and
`MarketDataPort` are separate Protocols. `RiskCheckedTradingPort` wraps only the
trading port. Merging them into Instrument would undo this separation.

**W3 — No Separation Between Instrument Identity and Instrument Runtime State (HIGH)**

You need two distinct concepts:

1. **Instrument Identity** — immutable, eternal. "RELIANCE on NSE" is the same
   entity today as it was 10 years ago. It has a symbol, exchange, ISIN, asset class,
   lot size, tick size. It does NOT have a "current quote" — the quote is a temporal
   fact about the instrument, not a property of its identity.

2. **Instrument Runtime State** — mutable, ephemeral. The current quote, the active
   subscription, the latest depth snapshot — these are runtime facts that change
   every tick. They belong to a session-scoped object, not to the instrument's
   identity.

Your existing `Instrument` dataclass is correctly the identity layer (frozen, no
behavior). Your `InstrumentRef` in `historical.py` is a further-reduced identity
for streaming/historical contexts. The proposed design would collapse these layers.

**W4 — "Provider" Is the Right Abstraction but the Granularity Is Unclear (MEDIUM)**

You list "Broker Provider, Replay Provider, CSV Provider, Yahoo Provider, Polygon
Provider, Paper Provider, FIX Provider, Simulation Provider" — but these conflate
two different roles:

- **Data Providers** — supply market data (quotes, depth, history, option chains). Yahoo, Polygon, CSV, Replay are data-only.
- **Execution Providers** — can place/cancel/modify orders. Broker, Paper, FIX are execution-capable.

A broker is BOTH a data provider and an execution provider. Yahoo is ONLY a data
provider. This distinction must be explicit in the type system, not implicit.

Your existing codebase already has this separation: `MarketDataPort` vs `TradingPort`
vs `StreamingPort`. The redesign should preserve and strengthen it.

**W5 — Extensions Mechanism Needs Stronger Type Safety (MEDIUM)**

`instrument.extensions.depth20` is ergonomic but loses type safety. If `depth20`
is not available for this broker, what happens? `AttributeError` at runtime? A
`None` return? A typed `Optional[Depth20Extension]`?

Your existing `CapabilitySurface` manifest + `BrokerCapabilities.supports()` pattern
is the right foundation. The extension access should be capability-gated and
type-safe.

**W6 — Missing Account/Portfolio Aggregate (HIGH)**

Your proposal focuses entirely on the instrument side and barely mentions Account,
Portfolio, Position, and Order. In a production trading SDK, these are first-class
aggregates with their own lifecycles:

- **Account** is an aggregate root (balance, margin, holdings, positions).
- **Order** is an entity within the Account/Execution aggregate (lifecycle: pending → submitted → partial → filled/cancelled/rejected).
- **Position** is an entity within the Account aggregate (mutable, tracks unrealized P&L).
- **Portfolio** is a read model / projection over Account + Positions + Holdings.

Your existing entities (`Balance`, `Position`, `Holding`, `Order`, `Trade`) are
correct as value objects/entities, but they're not organized into aggregates.

**W7 — No Mention of Concurrency Model (MEDIUM)**

A financial SDK will have hundreds of concurrent consumers reading quotes, placing
orders, and subscribing to streams. The design must specify:

- Is Instrument thread-safe? (If it holds runtime state, it must be.)
- Are subscriptions shared or per-consumer?
- How are concurrent order placements serialized?
- What is the memory model for cross-thread quote publication?

Your existing `BrokerRegistry` uses `threading.RLock()` and your streaming uses
asyncio. The redesign must be explicit about the concurrency model.

### 1.2 Answers to Your Specific Questions

**Q1: Is Instrument really the correct Aggregate Root?**

Partially. Instrument is a valid **Entity** and an excellent **identity root** for
market data. But it should NOT be the Aggregate Root for execution. Execution belongs
to the Account/Order aggregate. Instrument is referenced BY orders, positions, and
subscriptions — it does not own them.

**Q2: Should there be another root above Instrument?**

Yes: **Market** (or **Universe**). A Market represents a trading venue (NSE, BSE,
NFO, MCX) and owns the set of instruments available on it. This is where instrument
discovery, market hours, and market-level metadata live. StockSharp has this concept
implicitly via the `Board`/`ExchangeBoard` association.

**Q3: Should Provider replace Broker as the abstraction?**

Yes, but with the Data/Execution split made explicit. Rename:
- `MarketDataPort` → `MarketDataProvider` (or keep `MarketDataPort`)
- `TradingPort` → `ExecutionProvider` (or keep `TradingPort`)
- `StreamingPort` → `StreamingProvider` (or keep `StreamingPort`)

A Broker is a composite provider that implements all three. A CSV provider implements
only `MarketDataProvider`. This is already your current architecture — just needs
naming clarity.

**Q4: What responsibilities belong inside Instrument?**

- Identity: symbol, exchange, ISIN, asset class, lot size, tick size, expiry, strike
- Type classification: equity, future, option, index, commodity, currency, crypto
- Metadata: corporate actions, market hours reference, segment classification
- **Nothing that requires IO**

**Q5: What responsibilities should NOT belong inside Instrument?**

- Quote retrieval (IO-bound, provider-specific)
- Historical data retrieval (IO-bound, potentially multi-source)
- Subscription management (session-scoped, concurrency-heavy)
- Order placement (execution domain, risk-gated)
- Depth retrieval (IO-bound)
- Option chain construction (requires provider call)
- Statistics computation (CPU-bound, may require historical data fetch)

**Q6: Should Instrument own Quote, History, Depth and Subscription?**

No. These are **runtime state** owned by a **session-scoped handle** (e.g.,
`InstrumentHandle` or `LiveInstrument`), not by the Instrument identity. The
identity is immutable; the runtime state is mutable and session-scoped.

**Q7: How should Account, Portfolio, Position and Order relate to Instrument?**

```
Account (Aggregate Root)
  ├── Balance (Value Object)
  ├── Holdings[] (Entities — long-term delivery positions)
  ├── Positions[] (Entities — intraday/derivative positions, reference Instrument)
  └── Orders[] (Entities — lifecycle managed, reference Instrument)

Instrument (Aggregate Root for market data)
  └── (referenced by Orders, Positions, Holdings, Subscriptions)

OptionChain (Aggregate Root)
  └── Options[] (each is an Instrument identity)
```

**Q8: Is Option inheritance correct?**

No. An Option is NOT a subclass of Instrument. An Option IS an Instrument — it has
the same identity structure (symbol, exchange, lot size, tick size) plus additional
attributes (strike, expiry, option type, underlying). This should be modeled as:

```python
@dataclass(frozen=True)
class Instrument:
    symbol: str
    exchange: Exchange
    asset_class: AssetClass
    lot_size: int
    tick_size: Decimal
    # ... identity fields

@dataclass(frozen=True)
class OptionContract:
    instrument: Instrument          # composition, not inheritance
    underlying: InstrumentRef
    strike: Decimal
    expiry: date
    option_type: OptionType          # CE / PE
    exercise_style: ExerciseStyle    # EUROPEAN / AMERICAN
```

**Q9: Should OptionChain be an Aggregate?**

Yes. OptionChain is a proper aggregate root:
- It owns a collection of Option contracts.
- It enforces invariants (all options share the same underlying and expiry).
- It provides aggregate-level operations (ATM, ITM, OTM, PCR, IV surface).
- Each Option within the chain is an Instrument identity.

**Q10: How should extensions work?**

Extensions should be:
1. **Typed Protocols** — each extension is a `Protocol` with typed methods.
2. **Capability-gated** — availability is declared via `BrokerCapabilities`.
3. **Lazily resolved** — accessed via `handle.extensions.depth20` which returns
   `Depth20Extension | None` based on whether the provider supports it.
4. **Composable** — extensions are decorators over the provider, not over the
   instrument.

**Q11: How should broker capabilities be modeled?**

Your existing `BrokerCapabilities` frozen dataclass is the right pattern. Keep it.
The improvement is to:
1. Split into `DataCapabilities`, `ExecutionCapabilities`, `StreamingCapabilities`
   (ISP — not every consumer needs all three).
2. Make capability checks return typed `Capability[T]` monads instead of bare booleans,
   enabling ergonomic `caps.depth_20.map(lambda ext: ...)` patterns.

**Q12: How would StockSharp, Bloomberg or Interactive Brokers architect this?**

| System | Instrument Model | Execution Model | Data Model |
|--------|-----------------|-----------------|------------|
| **StockSharp** | `Security` = identity + metadata (POCO). Central but passive. | `IConnector` handles all order operations. Strategy calls `connector.RegisterOrder()`. | `IConnector` raises events (`NewTrades`, `NewCandles`). Security is referenced in events. |
| **QuantConnect LEAN** | `Symbol` (immutable ID) + `Security` (state holder with models). Security holds holdings, price, fees — but NOT behavior. | `IBrokerage` interface. Algorithm calls `BrokerageModel.Order()`. | `IDataQueueHandler` streams data. `SubscriptionDataConfig` maps Symbol → data stream. |
| **Interactive Brokers** | `Contract` = identity (symbol, secType, exchange, currency). Passive data container. | `EClient` sends orders. `EWrapper` receives events. Order references Contract. | `EClient.reqMktData()` → `EWrapper.tickPrice()`. Contract is passed as argument. |

**Common pattern across all three:** Instrument/Security/Contract is an **identity +
passive state holder**. A **separate connector/client/brokerage** handles all IO.
Events flow through an **observer/callback** mechanism. The instrument is referenced
by orders and events but does not own the IO.

**Q13: What architectural mistakes am I making?**

1. **Active Record for a complex domain** — `instrument.buy()` is Active Record. For
   a financial SDK, the Domain Model + Service pattern is more appropriate.
2. **Collapsing identity and runtime state** — Instrument should be immutable identity;
   runtime state belongs to a session-scoped handle.
3. **Coupling data and execution** — `buy()` and `history()` on the same object have
   different reliability, threading, and lifecycle requirements.
4. **No explicit concurrency model** — God Objects in concurrent systems are
   particularly dangerous.
5. **Missing Account/Order aggregate** — Trading is not just about instruments; it's
   about accounts, orders, positions, and risk.

**Q14: Where could this design become a God Object?**

Instrument with 11 state fields and 10 methods. Every new feature (Greeks, IV
surface, PCR, OI analysis, corporate actions scanner, fund flow) would add more
methods to Instrument. Within 2 years, Instrument would have 40+ methods.

**Q15: How can composition prevent that?**

Split Instrument into:
- `Instrument` — immutable identity (5-7 fields, zero methods).
- `InstrumentHandle` — session-scoped, holds a Provider reference, delegates all IO
  to the provider. This is the "intelligent domain object" you want, but it's
  composed FROM Instrument + ProviderContext, not inheriting FROM Instrument.
- `OptionChain` — separate aggregate for derivative structures.
- `Account` — separate aggregate for execution and portfolio.

**Q16: What should the public API look like?**

See Phase 4. The key insight: `instrument.history()` is achievable, but the
`instrument` in that expression is an `InstrumentHandle` (session-scoped, provider-
bound), not the immutable `Instrument` identity.

**Q17: What should remain completely hidden?**

- HTTP clients, WebSocket transports, token managers
- Broker-specific DTOs and response parsing
- Instrument resolution internals (symbol → security_id mapping)
- Rate limiting, circuit breakers, retry logic
- Streaming transport and message decoding
- Thread synchronization primitives

**Q18: How would you redesign this from first principles?**

See Phases 2–7.

### 1.3 Tradeoffs Summary

| Decision | Tradeoff | Recommendation |
|----------|----------|----------------|
| Instrument as God Object vs. thin identity | Ergonomics vs. maintainability | **Thin identity + handle.** Ergonomics achieved via handle, not via bloating identity. |
| Active Record vs. Domain Model + Service | Simplicity vs. scalability | **Domain Model + Service.** Financial domain is too complex for Active Record. |
| Single Provider vs. split Data/Execution | Simplicity vs. correctness | **Split.** Data and execution have fundamentally different contracts. |
| Inheritance for instrument types vs. composition | Intuition vs. flexibility | **Composition.** Avoid the diamond problem with multi-class instruments. |
| Mutable Instrument vs. immutable identity + mutable handle | Simplicity vs. thread safety | **Immutable + handle.** Critical for concurrent access. |
| Extensions on Instrument vs. extensions on Provider | Ergonomics vs. coupling | **Extensions on Provider, accessed via handle.** `handle.extensions.depth20` delegates to provider. |

---

## Phase 2 — Domain Model

### 2.1 Design Philosophy

We apply DDD with the following principles:

1. **Aggregates are consistency boundaries**, not convenience groupings.
2. **Value Objects are immutable and compared by value.**
3. **Entities have identity and lifecycle.**
4. **Aggregate Roots are the only entry points** to their internal entities.
5. **References between aggregates use IDs**, not direct object references.

### 2.2 Aggregate Roots

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AGGREGATE ROOT MAP                                │
│                                                                         │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐               │
│  │  Instrument  │    │ OptionChain   │    │   Account    │               │
│  │  (identity)  │    │ (derivative)  │    │ (execution)  │               │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘               │
│         │                   │                    │                       │
│         │ referenced by     │ contains           │ owns                  │
│         │                   │                    │                       │
│  ┌──────▼───────┐    ┌──────▼───────┐    ┌──────▼───────┐               │
│  │ Instrument   │    │  Option       │    │  Order       │               │
│  │  Handle      │    │  (Instrument  │    │  Position    │               │
│  │ (runtime)    │    │   + terms)    │    │  Holding     │               │
│  └──────────────┘    └──────────────┘    │  Balance     │               │
│                                          └──────────────┘               │
│                                                                         │
│  ┌─────────────┐    ┌──────────────┐                                   │
│  │   Market     │    │   Session     │                                   │
│  │ (venue)      │    │ (connection)  │                                   │
│  └─────────────┘    └──────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Entities and Value Objects

#### 2.3.1 Instrument (Value Object — Immutable Identity)

```python
@dataclass(frozen=True, slots=True)
class Instrument:
    """Immutable instrument identity — the canonical reference to a tradable asset.

    This object has NO behavior and NO IO. It is a pure identity record.
    It is compared by value (same symbol + exchange = same instrument).
    It is safe to share across threads, cache indefinitely, and use as a dict key.
    """
    symbol: str                          # Canonical ticker: "RELIANCE"
    exchange: Exchange                   # NSE, BSE, NFO, MCX, etc.
    asset_class: AssetClass              # EQUITY, FUTURE, OPTION, INDEX, etc.
    isin: str = ""                       # International Securities Identification Number
    lot_size: int = 1                    # Contract lot size (derivatives)
    tick_size: Decimal = Decimal("0.05") # Minimum price increment
    trading_symbol: str = ""             # Broker-specific trading symbol
    expiry: date | None = None           # Derivative expiry date
    strike: Decimal | None = None        # Option strike price
    option_type: OptionType | None = None  # CE / PE (options only)
    underlying_ref: InstrumentRef | None = None  # For derivatives
    exercise_style: ExerciseStyle | None = None  # EUROPEAN / AMERICAN
    currency: Currency = Currency.INR
```

**Why Value Object, not Entity?** An instrument's identity is fully determined by its
symbol + exchange + asset class + (expiry + strike for derivatives). Two Instrument
objects with the same fields ARE the same instrument. There is no mutable state that
needs a persistent identity separate from the value.

**Why not inheritance for Equity/Future/Option?** Consider a "currency future on USDINR"
— is it a Future or a Currency? With inheritance, you need multiple inheritance or a
diamond pattern. With composition, `asset_class: AssetClass` captures the type, and
optional fields (`expiry`, `strike`, `option_type`) capture derivative terms. This
is how QuantConnect's `Symbol` works — `SecurityType` is an enum field, not a subclass.

#### 2.3.2 InstrumentHandle (Entity — Session-Scoped Runtime State)

```python
class InstrumentHandle:
    """Session-scoped handle to an instrument — the 'live' domain object.

    Created by a Session bound to a Provider. Delegates all IO to the provider.
    Holds runtime state (latest quote, active subscriptions) in a thread-safe manner.

    This is the object users interact with:
        handle = session.instrument("RELIANCE", Exchange.NSE)
        quote = await handle.quote()
        bars = await handle.history(timeframe="5m", bars=100)
        await handle.subscribe(lambda tick: ...)
        order = await handle.buy(quantity=100, order_type=OrderType.MARKET)

    The handle IS the 'intelligent domain object' the user wants — but it is
    composed from Instrument (identity) + Session (provider context), not
    inherited from Instrument.
    """

    def __init__(
        self,
        instrument: Instrument,
        session: "Session",
    ) -> None:
        self._instrument = instrument
        self._session = session
        self._lock = threading.RLock()
        self._latest_quote: Quote | None = None
        self._latest_depth: MarketDepth | None = None
        self._subscriptions: list[Subscription] = []

    @property
    def instrument(self) -> Instrument:
        """Immutable identity of this handle."""
        return self._instrument

    @property
    def extensions(self) -> ExtensionRegistry:
        """Broker-specific extension facade."""
        return self._session.extensions

    # ── Market Data (delegates to session.provider) ──────────────────

    async def quote(self) -> Quote:
        """Fetch the latest quote snapshot."""
        return await self._session.provider.get_quote(self._instrument)

    async def ltp(self) -> Decimal:
        """Fetch the last traded price."""
        return await self._session.provider.get_ltp(self._instrument)

    async def depth(self) -> MarketDepth:
        """Fetch the current order book depth."""
        return await self._session.provider.get_depth(self._instrument)

    async def history(self, *, timeframe: str, bars: int | None = None,
                      from_date: date | None = None,
                      to_date: date | None = None) -> HistoricalSeries:
        """Fetch historical OHLCV bars."""
        return await self._session.provider.get_history(
            self._instrument, timeframe=timeframe, bars=bars,
            from_date=from_date, to_date=to_date,
        )

    # ── Streaming (delegates to session.provider) ────────────────────

    async def subscribe(self, on_tick: Callable[[Quote], None]) -> Subscription:
        """Subscribe to real-time quote updates."""
        sub = await self._session.provider.subscribe_quotes(
            [self._instrument], on_tick=on_tick,
        )
        with self._lock:
            self._subscriptions.append(sub)
        return sub

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Cancel a subscription."""
        await self._session.provider.unsubscribe(subscription)
        with self._lock:
            self._subscriptions.remove(subscription)

    # ── Execution (delegates to session.execution_provider) ──────────

    async def buy(self, quantity: int, *,
                  order_type: OrderType = OrderType.MARKET,
                  price: Decimal | None = None,
                  product_type: ProductType = ProductType.INTRADAY) -> OrderResponse:
        """Place a buy order for this instrument."""
        return await self._session.execution_provider.place_order(
            OrderRequest(
                instrument=self._instrument,
                side=Side.BUY,
                quantity=quantity,
                order_type=order_type,
                price=price or Decimal("0"),
                product_type=product_type,
            )
        )

    async def sell(self, quantity: int, *,
                   order_type: OrderType = OrderType.MARKET,
                   price: Decimal | None = None,
                   product_type: ProductType = ProductType.INTRADAY) -> OrderResponse:
        """Place a sell order for this instrument."""
        return await self._session.execution_provider.place_order(
            OrderRequest(
                instrument=self._instrument,
                side=Side.SELL,
                quantity=quantity,
                order_type=order_type,
                price=price or Decimal("0"),
                product_type=product_type,
            )
        )

    # ── Derivatives ──────────────────────────────────────────────────

    async def option_chain(self, expiry: date | None = None) -> OptionChain:
        """Fetch the option chain for this instrument (if it's an underlying)."""
        return await self._session.provider.get_option_chain(
            self._instrument, expiry=expiry,
        )

    async def future_chain(self) -> FutureChain:
        """Fetch the futures chain for this instrument."""
        return await self._session.provider.get_future_chain(self._instrument)
```

**Key design decisions:**

1. **InstrumentHandle holds a reference to Session, not to a specific Provider.**
   The Session resolves the appropriate provider based on routing policy. This allows
   the same handle to work across multiple brokers.

2. **buy()/sell() are convenience methods that delegate to execution_provider.**
   They do NOT bypass risk checks — the execution_provider is risk-wrapped at the
   Session level, just as `RiskCheckedTradingPort` wraps the trading port in your
   current bootstrap.

3. **quote(), history(), subscribe() delegate to the data provider.**
   The handle does not cache or compute — it delegates. Caching is a provider-level
   concern (your existing `@cached` decorator and `Cache` ABC).

4. **Runtime state (latest_quote, subscriptions) is protected by a lock.**
   The handle is thread-safe.

#### 2.3.3 OptionChain (Aggregate Root)

```python
@dataclass(frozen=True)
class OptionChain:
    """Aggregate root for an option chain — owns all option contracts for one
    underlying + one expiry.

    Invariants enforced:
    - All options share the same underlying.
    - All options share the same expiry.
    - Each option is a valid Instrument identity.
    """
    underlying: InstrumentRef
    exchange: Exchange
    expiry: date
    options: tuple[OptionContract, ...]  # frozen tuple — immutable

    # ── Aggregate-level queries (pure, no IO) ────────────────────────

    @property
    def strikes(self) -> list[Decimal]:
        """All strike prices, sorted ascending."""
        return sorted({o.strike for o in self.options})

    @property
    def calls(self) -> list[OptionContract]:
        return [o for o in self.options if o.option_type == OptionType.CE]

    @property
    def puts(self) -> list[OptionContract]:
        return [o for o in self.options if o.option_type == OptionType.PE]

    def atm(self, spot: Decimal) -> OptionContract | None:
        """At-the-money option — strike closest to spot."""
        ...

    def itm(self, spot: Decimal, option_type: OptionType) -> list[OptionContract]:
        """In-the-money options for the given type."""
        ...

    def otm(self, spot: Decimal, option_type: OptionType) -> list[OptionContract]:
        """Out-of-the-money options."""
        ...

    @property
    def pcr(self) -> Decimal | None:
        """Put-Call Ratio (OI-based). Requires OI data in OptionLegs."""
        ...

    def iv_surface(self) -> dict[Decimal, Decimal]:
        """Implied Volatility surface — strike → IV."""
        ...
```

```python
@dataclass(frozen=True)
class OptionContract:
    """A single option within a chain — composition of Instrument + option terms."""
    instrument: Instrument               # Full instrument identity
    underlying: InstrumentRef
    strike: Decimal
    expiry: date
    option_type: OptionType
    exercise_style: ExerciseStyle
    leg_data: OptionLeg | None = None    # Market data (LTP, OI, IV, Greeks)
```

#### 2.3.4 Account (Aggregate Root — Execution Domain)

```python
class Account:
    """Aggregate root for the execution domain.

    Owns orders, positions, holdings, and balance. Enforces invariants:
    - Cannot place order if risk check fails.
    - Position updates are atomic with order fills.
    - Balance updates are atomic with order placement/cancellation.

    Referenced by InstrumentHandle for buy()/sell() delegation.
    """

    def __init__(self, account_id: str, execution_provider: ExecutionProvider) -> None:
        self._account_id = account_id
        self._execution_provider = execution_provider  # risk-wrapped
        self._positions: dict[str, Position] = {}      # keyed by instrument key
        self._holdings: dict[str, Holding] = {}
        self._balance: Balance = Balance(available_balance=Decimal("0"))

    @property
    def account_id(self) -> str:
        return self._account_id

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order through the risk-gated execution provider."""
        return await self._execution_provider.place_order(request)

    async def get_positions(self) -> list[Position]:
        """All open positions."""
        return await self._execution_provider.get_positions()

    async def get_balance(self) -> Balance:
        """Account balance and margin."""
        return await self._execution_provider.get_balances()

    async def get_holdings(self) -> list[Holding]:
        """Long-term equity holdings."""
        return await self._execution_provider.get_holdings()

    async def get_orders(self) -> list[Order]:
        """Current order book."""
        return await self._execution_provider.get_orderbook()

    async def get_trades(self) -> list[Trade]:
        """Today's executed fills."""
        return await self._execution_provider.get_trades()
```

#### 2.3.5 Value Objects (Existing — Retained and Refined)

| Value Object | Status | Notes |
|--------------|--------|-------|
| `Quote` | ✅ Retained | Frozen dataclass, immutable. |
| `MarketDepth` / `DepthLevel` | ✅ Retained | Frozen, immutable snapshot. |
| `HistoricalBar` | ✅ Retained | Frozen, with `InstrumentRef`. |
| `HistoricalSeries` | ✅ Retained | Mutable (gaps list), but bars are frozen. |
| `OrderRequest` | ✅ Retained | Frozen, immutable input. |
| `OrderResponse` | ✅ Retained | Frozen, with `.ok()` / `.fail()` factories. |
| `Balance` | ✅ Retained | Frozen, immutable snapshot. |
| `Trade` | ✅ Retained | Frozen, immutable fill. |
| `InstrumentRef` | ✅ Retained | Minimal ref for historical/streaming contexts. |
| `GatewayResult[T]` | ✅ Retained | Monadic result with map/flat_map/recover. |
| `DomainEvent` | ✅ Retained | Frozen, immutable event. |
| `RiskDecision` | ✅ Retained | Frozen, allow/deny with structured reason. |

#### 2.3.6 New Value Objects

```python
@dataclass(frozen=True)
class OptionLeg:
    """Market data for one option leg (CE or PE at one strike)."""
    ltp: Decimal | None = None
    oi: int | None = None
    volume: int | None = None
    iv: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    greeks: Greeks | None = None       # Typed, not dict[str, Any]

@dataclass(frozen=True)
class Greeks:
    """Option Greeks — typed value object."""
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None

@dataclass(frozen=True)
class Subscription:
    """Handle to an active subscription — used for unsubscribe."""
    subscription_id: str
    instrument_ref: InstrumentRef
    channel: str                        # "quotes", "depth", "orders"
```

### 2.4 Relationship Map

```
Session (1) ──── (N) InstrumentHandle
  │                       │
  │                       │ references
  │                       ▼
  │                  Instrument (immutable identity)
  │                       ▲
  │                       │ referenced by
  │                       │
  ├── (1) Account ──── (N) Order ──→ Instrument
  │         │
  │         ├── (N) Position ──→ Instrument
  │         ├── (N) Holding  ──→ Instrument
  │         └── (1) Balance
  │
  ├── (1) MarketDataProvider
  ├── (1) ExecutionProvider
  ├── (1) StreamingProvider
  └── (1) ExtensionRegistry
```

### 2.5 Lifecycle

| Object | Born | Lives | Dies |
|--------|------|-------|------|
| `Instrument` | Instrument master load / search | Eternal (cached, immutable) | Never (GC when cache evicted) |
| `InstrumentHandle` | `session.instrument(sym, exch)` | Session-scoped | Session close / explicit release |
| `Account` | `session.account()` | Session-scoped | Session close |
| `Order` | `account.place_order()` | Until cancelled/expired/filled | Order lifecycle terminal state |
| `Position` | First fill opens position | Until squared off | Quantity reaches 0 |
| `Subscription` | `handle.subscribe()` | Until `handle.unsubscribe()` | Explicit unsubscribe or session close |
| `OptionChain` | `handle.option_chain()` | Snapshot — immutable | GC when consumer drops reference |

---

## Phase 3 — Package Structure

### 3.1 Proposed Package Layout

```
brokers/                           # Top-level SDK package
├── __init__.py                    # Public API re-exports
│
├── domain/                        # PURE DOMAIN — zero external deps
│   ├── __init__.py
│   ├── entities.py                # Instrument, Quote, Order, Trade, Position, etc.
│   ├── value_objects.py           # Greeks, Subscription, OptionLeg, OptionContract
│   ├── aggregates.py              # OptionChain, FutureChain (aggregate roots)
│   ├── enums.py                   # Exchange, AssetClass, OptionType, Side, etc.
│   ├── references.py              # InstrumentRef, AccountRef (cross-aggregate refs)
│   ├── events.py                  # DomainEvent, EventType, EventPayload contracts
│   ├── result.py                  # GatewayResult[T] monadic result
│   ├── requests.py                # OrderRequest, ModifyOrderRequest, SliceOrderRequest
│   ├── historical.py              # HistoricalBar, HistoricalSeries, DateRange, Gap
│   ├── stream_health.py           # StreamHealth, FreshnessState, TransportState
│   ├── capabilities.py            # Capability enum, CapabilitySurface manifest
│   ├── exchange_segments.py       # ExchangeSegment, segment classification helpers
│   ├── symbols.py                 # normalize_symbol, make_instrument_key
│   └── exceptions.py              # Domain exception hierarchy
│
├── api/                           # PUBLIC SDK API — the user-facing surface
│   ├── __init__.py
│   ├── session.py                 # Session — the root object users create
│   ├── instrument_handle.py       # InstrumentHandle — the "live" instrument
│   ├── account.py                 # Account — execution aggregate root
│   ├── option_chain.py            # OptionChainHandle — live option chain
│   ├── extensions.py              # ExtensionRegistry — typed extension access
│   └── builders.py                # SessionBuilder, fluent API for configuration
│
├── providers/                     # PROVIDER FRAMEWORK — protocols + base classes
│   ├── __init__.py
│   ├── ports.py                   # MarketDataPort, ExecutionPort, StreamingPort
│   ├── base.py                    # BaseProvider, BaseMarketDataProvider
│   ├── registry.py                # ProviderRegistry, provider discovery
│   ├── capabilities.py            # ProviderCapabilities (split: data/exec/stream)
│   ├── extensions/                # Extension protocols
│   │   ├── __init__.py
│   │   ├── depth.py               # Depth20Provider, Depth200Provider
│   │   ├── forever_orders.py      # ForeverOrderProvider
│   │   ├── super_orders.py        # SuperOrderProvider
│   │   ├── gtt.py                 # GttOrderProvider
│   │   ├── alerts.py              # AlertProvider
│   │   ├── news.py                # NewsProvider
│   │   ├── fundamentals.py        # FundamentalsProvider
│   │   └── market_intelligence.py # MarketIntelligenceProvider
│   └── routing/                   # Provider routing
│       ├── __init__.py
│       ├── router.py              # ProviderRouter (replaces BrokerRouter)
│       ├── policy.py              # RoutingPolicy, SourceSelectionPolicy
│       └── quota_scheduler.py     # QuotaScheduler for concurrency control
│
├── brokers/                       # BROKER IMPLEMENTATIONS
│   ├── __init__.py
│   ├── dhan/                      # Dhan broker adapter
│   │   ├── __init__.py
│   │   ├── adapter.py             # DhanAdapter (implements all three ports)
│   │   ├── client.py              # DhanHttpClient (raw HTTP)
│   │   ├── mapper.py              # DhanMapper (DTO → domain entities)
│   │   ├── resolver.py            # DhanInstrumentResolver
│   │   ├── streaming/             # WebSocket feeds
│   │   │   ├── market_feed.py
│   │   │   ├── order_feed.py
│   │   │   └── decoder.py
│   │   ├── auth/                  # Authentication
│   │   │   ├── token_manager.py
│   │   │   └── totp_client.py
│   │   └── extensions/            # Dhan-specific extensions
│   │       ├── super_orders.py
│   │       ├── forever_orders.py
│   │       └── depth200.py
│   │
│   ├── upstox/                    # Upstox broker adapter
│   │   ├── (same structure as dhan)
│   │
│   └── paper/                     # Paper trading provider
│       ├── adapter.py
│       └── simulator.py
│
├── infrastructure/                # CROSS-CUTTING INFRASTRUCTURE
│   ├── __init__.py
│   ├── http_client.py             # Async HTTP client abstraction
│   ├── cache.py                   # Cache ABC + in-memory implementation
│   ├── cache_redis.py             # Redis-backed cache
│   ├── event_bus.py               # In-process event bus (pub/sub)
│   ├── resilience.py              # @rate_limit, @circuit_breaker, @retry
│   ├── logging.py                 # Structured logging
│   ├── metrics.py                 # Metrics registry (counters, gauges, histograms)
│   ├── health.py                  # Health check system
│   ├── time_service.py            # Time abstraction (for testing/replay)
│   ├── streaming/                 # Streaming infrastructure
│   │   ├── transport.py           # AsyncTransport protocol
│   │   ├── orchestrator.py        # Stream orchestrator
│   │   ├── subscription.py        # SubscriptionPlan, InstrumentKey
│   │   ├── stream_health.py       # Stream health monitoring
│   │   └── queue_iterator.py      # Async queue → iterator bridge
│   └── rate_config.py             # Per-broker rate limit configs
│
├── bootstrap/                     # WIRING & DEPENDENCY INJECTION
│   ├── __init__.py
│   ├── bootstrap.py               # bootstrap_session() — replaces bootstrap_broker_stack
│   ├── factory.py                 # Factory functions for adapters
│   ├── instrument_registry.py     # SharedInstrumentRegistry
│   └── risk.py                    # PreTradeRiskChecker, RiskCheckedExecutionPort
│
└── tests/                         # TEST SUITES (see Phase 8)
    ├── architecture/              # Architecture tests
    ├── unit/                      # Unit tests
    ├── contract/                  # Contract tests
    ├── integration/               # Integration tests
    ├── e2e/                       # End-to-end tests
    ├── performance/               # Performance benchmarks
    ├── recovery/                  # Recovery scenarios
    └── soak/                      # Long-running soak tests
```

### 3.2 Dependency Rules

```
┌─────────────────────────────────────────────────────┐
│                     api/                             │  ← User-facing
│   (depends on: domain, providers)                    │
├─────────────────────────────────────────────────────┤
│                  providers/                          │  ← Abstraction layer
│   (depends on: domain)                               │
├─────────────────────────────────────────────────────┤
│                    domain/                           │  ← Pure, zero deps
│   (depends on: NOTHING — only stdlib)                │
├─────────────────────────────────────────────────────┤
│              brokers/ + infrastructure/              │  ← Implementation
│   (depend on: domain, providers, infrastructure)     │
├─────────────────────────────────────────────────────┤
│                   bootstrap/                         │  ← Wiring
│   (depends on: everything above)                     │
└─────────────────────────────────────────────────────┘
```

**Rules enforced:**

1. **`domain/` imports nothing from outside `domain/`.** Pure Python, stdlib only.
2. **`providers/` imports from `domain/` only.** Defines protocols and base classes.
3. **`api/` imports from `domain/` and `providers/`.** The user-facing surface.
4. **`brokers/` imports from `domain/`, `providers/`, `infrastructure/`.** Concrete implementations.
5. **`infrastructure/` imports from `domain/` only.** Cross-cutting concerns.
6. **`bootstrap/` imports from everything.** The composition root.
7. **No circular imports.** Enforced by architecture tests (see Phase 8).

### 3.3 Module Explanations

| Module | Responsibility | Key Types |
|--------|---------------|-----------|
| `domain/entities.py` | Immutable identity and snapshot types | `Instrument`, `Quote`, `Order`, `Trade`, `Position`, `Balance`, `Holding` |
| `domain/aggregates.py` | Aggregate roots for derivative structures | `OptionChain`, `FutureChain` |
| `domain/events.py` | Event type catalogue and payload contracts | `DomainEvent`, `EventType`, `EventPayload` |
| `api/session.py` | The root object users create; owns providers and routing | `Session` |
| `api/instrument_handle.py` | The "live" instrument with behavior | `InstrumentHandle` |
| `api/account.py` | Execution aggregate root | `Account` |
| `providers/ports.py` | Protocol interfaces for data, execution, streaming | `MarketDataPort`, `ExecutionPort`, `StreamingPort` |
| `providers/extensions/` | Typed Protocols for broker-specific features | `Depth20Provider`, `ForeverOrderProvider`, etc. |
| `providers/routing/` | Provider selection and routing | `ProviderRouter`, `RoutingPolicy` |
| `brokers/dhan/` | Dhan-specific implementation | `DhanAdapter`, `DhanHttpClient` |
| `infrastructure/event_bus.py` | In-process pub/sub | `EventBus` |
| `infrastructure/streaming/` | WebSocket transport and orchestration | `AsyncTransport`, `StreamOrchestrator` |
| `bootstrap/bootstrap.py` | Composition root — wires everything | `bootstrap_session()` |

---

## Phase 4 — Public SDK API

### 4.1 Design Principles for the Public API

1. **Progressive disclosure:** Simple things are simple; advanced things are possible.
2. **Fluent builders:** Configuration via method chaining, not giant constructors.
3. **Async-first:** All IO is async. Sync wrappers provided for convenience.
4. **Type-safe:** No `Any` in the public API. All returns are typed.
5. **No broker names in user code:** Users never write `if broker == "dhan"`.

### 4.2 Quick Start — The 5-Line Hello World

```python
from brokers import Session

# 1. Create a session (the root object)
session = await Session.create(
    brokers=["dhan"],
    dhan_client_id="123",
    dhan_access_token="tok",
)

# 2. Get an instrument handle
reliance = session.instrument("RELIANCE", Exchange.NSE)

# 3. Fetch market data
quote = await reliance.quote()
print(f"RELIANCE LTP: {quote.ltp}")

# 4. Place an order
response = await reliance.buy(quantity=10, order_type=OrderType.MARKET)
print(f"Order: {response.order_id}, status: {response.status}")

# 5. Subscribe to live ticks
async for tick in reliance.stream_quotes():
    print(f"Tick: {tick.ltp}")
```

### 4.3 Advanced Configuration

```python
from brokers import SessionBuilder, RiskLimits, Exchange

session = await (
    SessionBuilder()
        .with_broker("dhan", client_id="123", access_token="tok")
        .with_broker("upstox", access_token="tok2")
        .with_routing_policy(
            execution="dhan",              # All orders through Dhan
            market_data=["dhan", "upstox"], # Load-balanced
            historical=["upstox", "dhan"],  # Upstox primary for history
        )
        .with_risk_limits(
            RiskLimits(
                max_order_value=Decimal("100000"),
                max_position_quantity=10000,
                enabled=True,
            )
        )
        .with_max_concurrent_requests(10)
        .with_batch_concurrency(8)
        .build()
)
```

### 4.4 Multi-Broker Usage

```python
# The same instrument works across brokers — routing is automatic
reliance = session.instrument("RELIANCE", Exchange.NSE)

# Quote comes from the best available broker (based on routing policy)
quote = await reliance.quote()

# But you can also access a specific broker's view:
dhan_quote = await session
    .broker("dhan")
    .instrument("RELIANCE", Exchange.NSE)
    .quote()

# Extensions are broker-specific and type-safe
depth20 = reliance.extensions.depth20  # Returns Depth20Extension | None
if depth20 is not None:
    snapshot = await depth20.get()
```

### 4.5 Option Chain Usage

```python
nifty = session.instrument("NIFTY", Exchange.NFO)

# Fetch the option chain for nearest expiry
chain = await nifty.option_chain()

# Query the chain (pure, no IO — all data already fetched)
print(f"Strikes: {chain.strikes}")
print(f"ATM: {chain.atm(spot=quote.ltp)}")
print(f"PCR: {chain.pcr}")

# Get a handle to a specific option for trading
atm_call = chain.atm(spot=quote.ltp)
if atm_call and atm_call.option_type == OptionType.CE:
    option_handle = session.instrument_from(atm_call.instrument)
    response = await option_handle.buy(quantity=75)  # 75 = lot size
```

### 4.6 Account and Portfolio

```python
account = session.account()

# Balance and margin
balance = await account.get_balance()
print(f"Available: {balance.available_balance}")

# Positions
positions = await account.get_positions()
for pos in positions:
    print(f"{pos.symbol}: {pos.quantity} @ {pos.average_price}, P&L: {pos.pnl}")

# Order management
orders = await account.get_orders()
for order in orders:
    print(f"{order.order_id}: {order.status}")

# Cancel an order
await account.cancel_order("12345")
```

### 4.7 Streaming and Events

```python
# Subscribe to quotes
sub = await reliance.subscribe_quotes(
    on_tick=lambda tick: print(f"Tick: {tick.ltp}")
)

# Subscribe to order updates
order_sub = await account.subscribe_orders(
    on_update=lambda order: print(f"Order {order.order_id}: {order.status}")
)

# Event bus — system-wide events
session.event_bus.subscribe(
    EventType.BROKER_DISCONNECTED,
    handler=lambda event: print(f"Broker down: {event.payload}")
)

# Cleanup
await sub.cancel()
await order_sub.cancel()
await session.close()
```

### 4.8 Paper Trading (Zero Configuration)

```python
# No credentials needed — paper provider is always available
session = await Session.create(brokers=["paper"])

reliance = session.instrument("RELIANCE", Exchange.NSE)

# Simulated market data
quote = await reliance.quote()  # Returns deterministic simulated data

# Simulated order execution
response = await reliance.buy(quantity=100)
# Fills instantly at simulated price
```

### 4.9 Why This API Is Intuitive

| Principle | How It's Achieved |
|-----------|-------------------|
| **Instrument-centric** | `reliance.quote()`, `reliance.history()`, `reliance.buy()` — the instrument is the subject. |
| **Broker-agnostic** | No broker names in common operations. Routing is automatic. |
| **Progressive disclosure** | Quick start is 5 lines. Advanced config uses fluent builder. |
| **Type-safe** | Extensions return `T | None`. All methods have typed returns. |
| **Async-first** | All IO is `async`. No blocking calls in the hot path. |
| **Composable** | Session → Handle → Provider. Each layer is independently testable. |

---

## Phase 5 — Internal Architecture

### 5.1 Engine Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                           SESSION                                     │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Market   │  │ Execution│  │ Streaming│  │  Extension        │   │
│  │ Data     │  │ Engine   │  │ Engine   │  │  Registry         │   │
│  │ Engine   │  │          │  │          │  │                   │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────────────────┘   │
│       │              │              │                               │
│       ▼              ▼              ▼                               │
│  ┌──────────────────────────────────────────────────────┐          │
│  │              PROVIDER ROUTER                          │          │
│  │  (capability filtering → health check → policy order)│          │
│  └──────────────────────┬───────────────────────────────┘          │
│                         │                                            │
│       ┌─────────────────┼─────────────────┐                         │
│       ▼                 ▼                 ▼                         │
│  ┌─────────┐      ┌─────────┐      ┌─────────┐                     │
│  │  Dhan   │      │  Upstox │      │  Paper  │                     │
│  │ Adapter │      │ Adapter │      │ Adapter │                     │
│  └────┬────┘      └────┬────┘      └────┬────┘                     │
│       │                │                │                            │
│       ▼                ▼                ▼                            │
│  ┌──────────────────────────────────────────────┐                  │
│  │              INFRASTRUCTURE                   │                  │
│  │  HTTP │ WebSocket │ Cache │ EventBus │ Rate   │                  │
│  │  Client│ Transport │       │           │ Limit│                  │
│  └──────────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 Authentication & Session

**Current state:** `TokenManager` and `TokenStateStore` Protocol exist in
`brokers/common/auth/`. TOTP clients exist for Dhan and Upstox.

**Redesign:**

```python
class AuthManager:
    """Manages authentication lifecycle for all providers.

    Responsibilities:
    - Token acquisition (OAuth, TOTP, API key)
    - Token refresh (proactive refresh before expiry)
    - Token storage (in-memory, file, Redis via TokenStateStore)
    - Auth event publishing (TOKEN_REFRESHED, TOKEN_EXPIRED)
    """

    def __init__(
        self,
        token_store: TokenStateStore,
        event_bus: EventBus,
        time_service: TimeService,
    ) -> None:
        self._store = token_store
        self._event_bus = event_bus
        self._time = time_service
        self._refresh_task: asyncio.Task | None = None

    async def get_token(self, broker_id: str) -> AccessToken:
        """Get a valid token, refreshing if necessary."""
        ...

    async def start_proactive_refresh(self, broker_id: str) -> None:
        """Background task that refreshes tokens before expiry."""
        ...
```

**Token lifecycle:**
```
Acquire → Store → Use → [Expiry approaching] → Refresh → Store → Use → ...
                                                                    ↓
                                                              [Refresh fails]
                                                                    ↓
                                                              TOKEN_EXPIRED event
                                                                    ↓
                                                              Re-authenticate or fail
```

### 5.3 Streaming Engine

**Current state:** `BaseMarketFeed` (ABC), `BaseOrderStream` (ABC),
`StreamOrchestrator`, `SubscriptionPlan`, `StreamHealth` monitoring.

**Redesign preserves this architecture** — it is well-designed. Key changes:

1. **StreamOrchestrator becomes provider-agnostic.** Currently it's somewhat
   broker-specific. Make it work with any `StreamingPort` implementation.

2. **Subscription deduplication across handles.** If two InstrumentHandles subscribe
   to the same instrument, the orchestrator should maintain ONE broker subscription
   and fan-out to both consumers. This is the **Flyweight pattern** for subscriptions.

3. **Backpressure handling.** If a consumer's callback is slow, the orchestrator
   should buffer (bounded) and drop oldest (configurable) rather than blocking the
   WebSocket read loop.

```
┌─────────────────────────────────────────────┐
│            STREAM ORCHESTRATOR               │
│                                             │
│  ┌─────────────┐    ┌──────────────────┐   │
│  │ Subscription │    │  Transport       │   │
│  │ Manager      │───→│  (WebSocket)     │   │
│  │ (Flyweight)  │    │                  │   │
│  └──────┬───────┘    └────────┬─────────┘   │
│         │                     │              │
│         │ fan-out             │ decode       │
│         ▼                     ▼              │
│  ┌─────────────┐    ┌──────────────────┐   │
│  │ Consumer     │    │  Decoder         │   │
│  │ Queue (per   │    │  (broker-specific)│   │
│  │  consumer)   │    │                  │   │
│  └─────────────┘    └──────────────────┘   │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  Stream Health Monitor               │   │
│  │  (freshness, transport, subscription)│   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### 5.4 Historical Data Engine

**Current state:** `HistoricalBar`, `HistoricalSeries`, `DateRange`, `Gap`,
`MergeManifest`, `HistoricalDataCoordinator` (referenced but in archive).

**Redesign:**

```python
class HistoricalDataEngine:
    """Coordinates historical data retrieval with:

    1. Multi-source merging (fetch from multiple brokers, merge, detect conflicts)
    2. Gap detection and filling (retry from alternate source)
    3. Caching (avoid re-fetching recently requested data)
    4. Rate limit awareness (quota scheduler integration)
    5. Pagination handling (broker-specific page sizes)
    """

    def __init__(
        self,
        router: ProviderRouter,
        cache: Cache,
        scheduler: QuotaScheduler,
    ) -> None:
        ...

    async def get_history(
        self,
        instrument: Instrument,
        *,
        timeframe: str,
        from_date: date,
        to_date: date,
    ) -> HistoricalSeries:
        """Fetch historical bars with multi-source merge and gap filling."""
        ...
```

### 5.5 Order Engine (OMS)

**Current state:** `TradingPort` Protocol, `OrderRequest`, `OrderResponse`,
`RiskCheckedTradingPort` decorator.

**Redesign adds:**

1. **Order lifecycle state machine:**
   ```
   PENDING → SUBMITTED → PARTIALLY_FILLED → FILLED
                 ↓              ↓
            CANCELLED       CANCELLED
                 ↓              ↓
              REJECTED      REJECTED
   ```

2. **Idempotency:** Your existing `IdempotencyCacheProtocol` and `MemoryIdempotencyCache`
   are retained. Every `place_order` generates a correlation_id; retries with the same
   correlation_id return the original response.

3. **Order event publishing:** Every state transition publishes a `DomainEvent`
   (`ORDER_PLACED`, `ORDER_UPDATED`, `ORDER_CANCELLED`, `ORDER_REJECTED`, `TRADE`).

4. **Reconciliation:** Your existing `BaseReconciliation` ABC is retained. A background
   task periodically compares internal order state with broker state and publishes
   `RECONCILIATION_DRIFT` events on mismatch.

### 5.6 Portfolio Engine

**Current state:** `Position`, `Balance`, `Holding` entities exist but are passive.

**Redesign adds:**

```python
class PortfolioEngine:
    """Real-time portfolio state aggregator.

    Maintains a live view of:
    - All positions (updated on every fill)
    - Account balance (updated on every order/fill)
    - Holdings (updated on delivery/cNC trades)
    - Unrealized P&L (updated on every tick)

    Subscribes to TRADE and POSITION_CHANGED events to update state.
    Publishes PORTFOLIO_UPDATED events when state changes.
    """

    def __init__(self, event_bus: EventBus, account: Account) -> None:
        self._event_bus = event_bus
        self._account = account
        self._positions: dict[str, Position] = {}
        self._lock = threading.RLock()

    async def start(self) -> None:
        """Subscribe to events and begin real-time updates."""
        self._event_bus.subscribe(EventType.TRADE, self._on_trade)
        self._event_bus.subscribe(EventType.POSITION_CHANGED, self._on_position_change)

    def snapshot(self) -> PortfolioSnapshot:
        """Current portfolio state (thread-safe read)."""
        with self._lock:
            return PortfolioSnapshot(
                positions=list(self._positions.values()),
                balance=self._balance,
                timestamp=datetime.now(timezone.utc),
            )
```

### 5.7 Recovery Engine

```python
class RecoveryEngine:
    """Handles connection recovery and state resynchronization.

    Triggers on:
    - BROKER_DISCONNECTED events
    - Stream health degradation (freshness timeout)
    - Circuit breaker state changes

    Recovery sequence:
    1. Disconnect all streams for the affected broker
    2. Reconnect transport (with backoff)
    3. Re-authenticate if token expired
    4. Resubscribe to all active subscriptions
    5. Reconcile order state (fetch orderbook, compare with local)
    6. Reconcile positions (fetch positions, compare with local)
    7. Publish BROKER_CONNECTED event
    """

    async def recover_broker(self, broker_id: str) -> None:
        """Execute full recovery sequence for a broker."""
        ...
```

### 5.8 Caching

**Current state:** `Cache` ABC, in-memory implementation, `@cached` decorator,
Redis implementation in archive.

**Redesign:** Retained as-is. The cache is injected into providers and the historical
data engine. Cache keys are `InstrumentRef`-based for market data and
`InstrumentRef + timeframe + date_range` for historical data.

### 5.9 Events

**Current state:** `EventBus` in `infrastructure/event_bus.py`, `DomainEvent` and
`EventType` in `domain/events.py` with payload contracts.

**Redesign:** Retained. The event bus is the nervous system of the SDK. All
engines communicate via events. Key event flows documented in Phase 6.

### 5.10 Health & Metrics

**Current state:** `HealthCheck` ABC, `HealthRegistry`, `MetricsRegistry` with
counters, gauges, histograms, timers.

**Redesign:** Retained. Each provider reports health via the `HealthRegistry`.
The `Session` exposes a `health()` method that aggregates all component health
checks into a single `SessionHealth` snapshot.

### 5.11 Capability Registry

**Current state:** `BrokerCapabilities` frozen dataclass with `supports()` and
`limit_for()` methods. Pre-built profiles for Dhan, Upstox, Paper.

**Redesign splits capabilities:**

```python
@dataclass(frozen=True, slots=True)
class DataCapabilities:
    """Market data capabilities."""
    supports_ltp: bool = True
    supports_quote: bool = True
    supports_depth: bool = True
    supports_depth_levels: int = 5
    supports_history: bool = True
    supports_option_chain: bool = True
    supports_future_chain: bool = True
    historical_window: HistoricalWindowConstraint = field(default_factory=HistoricalWindowConstraint)

@dataclass(frozen=True, slots=True)
class ExecutionCapabilities:
    """Order execution capabilities."""
    supports_place_order: bool = True
    supports_cancel_order: bool = True
    supports_modify_order: bool = True
    supports_order_types: tuple[OrderType, ...] = (OrderType.MARKET, OrderType.LIMIT)
    supports_product_types: tuple[ProductType, ...] = (ProductType.INTRADAY, ProductType.CNC)
    supports_amo: bool = False  # After-Market Orders
    rate_limits: RateLimitProfile = field(default_factory=RateLimitProfile)

@dataclass(frozen=True, slots=True)
class StreamingCapabilities:
    """Streaming capabilities."""
    supports_quote_stream: bool = True
    supports_depth_stream: bool = True
    supports_order_stream: bool = True
    max_instruments_per_connection: int = 1000
    max_connections: int = 5
    stream_limits: StreamLimitProfile = field(default_factory=StreamLimitProfile)

@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Composite capabilities for a provider."""
    broker_id: str
    data: DataCapabilities = field(default_factory=DataCapabilities)
    execution: ExecutionCapabilities = field(default_factory=ExecutionCapabilities)
    streaming: StreamingCapabilities = field(default_factory=StreamingCapabilities)
    extensions: frozenset[str] = frozenset()  # Extension protocol names supported
```

### 5.12 Extension Registry

```python
class ExtensionRegistry:
    """Typed access to broker-specific extensions.

    Extensions are registered per-provider and gated by capabilities.
    Access returns the extension or None (if not supported by this provider).
    """

    def __init__(
        self,
        extensions: dict[str, Any],  # extension_name → implementation
        capabilities: ProviderCapabilities,
    ) -> None:
        self._extensions = extensions
        self._caps = capabilities

    @property
    def depth20(self) -> Depth20Extension | None:
        """Dhan-specific 20-level depth."""
        if "depth20" not in self._caps.extensions:
            return None
        return self._extensions.get("depth20")

    @property
    def forever_orders(self) -> ForeverOrderExtension | None:
        """GTT/forever order support."""
        if "forever_orders" not in self._caps.extensions:
            return None
        return self._extensions.get("forever_orders")

    # ... typed properties for each extension
```

---

## Phase 6 — Event Flow

### 6.1 Event Ownership

| Event | Published By | Payload | Consumers |
|-------|-------------|---------|-----------|
| `TICK` | Streaming Engine | Quote snapshot | InstrumentHandle callbacks, PortfolioEngine |
| `DEPTH` | Streaming Engine | MarketDepth | InstrumentHandle callbacks |
| `ORDER_PLACED` | Order Engine | Order | PortfolioEngine, audit log |
| `ORDER_UPDATED` | Order Engine (from stream) | Order | PortfolioEngine, user callbacks |
| `ORDER_CANCELLED` | Order Engine | order_id | PortfolioEngine, user callbacks |
| `ORDER_REJECTED` | Order Engine | order_id, reason | PortfolioEngine, risk engine |
| `TRADE` | Order Engine (from stream) | Trade | PortfolioEngine, PositionTracker |
| `POSITION_CHANGED` | PortfolioEngine | symbol, quantity | User callbacks, risk engine |
| `RISK_BREACH` | Risk Checker | rule, value, limit | Kill switch, alerting |
| `RISK_REJECTED` | Risk Checker | order_id, rule | Order Engine (returns fail) |
| `BROKER_CONNECTED` | Recovery Engine | broker_name | Router (marks healthy) |
| `BROKER_DISCONNECTED` | Transport Monitor | broker_name, reason | Recovery Engine, Router |
| `TOKEN_REFRESHED` | Auth Manager | broker_name, expires_at | Proactive refresh scheduler |
| `TOKEN_EXPIRED` | Auth Manager | broker_name | Recovery Engine |
| `CIRCUIT_BREAKER_OPENED` | Resilience Layer | reason | Router (marks unhealthy) |
| `CIRCUIT_BREAKER_CLOSED` | Resilience Layer | down_time | Router (marks healthy) |
| `RECONCILIATION_DRIFT` | Reconciliation | symbol, internal, broker | Alerting, manual review |
| `STREAM_HEALTH_DEGRADED` | Stream Health Monitor | component, metric | Recovery Engine |

### 6.2 Streaming Event Flow

```
WebSocket Frame
    │
    ▼
Decoder (broker-specific)
    │
    ▼
Normalized Quote / Depth
    │
    ▼
Stream Orchestrator
    │
    ├──→ Update InstrumentHandle._latest_quote (thread-safe)
    │
    ├──→ Publish TICK event on EventBus
    │       │
    │       ├──→ PortfolioEngine (updates unrealized P&L)
    │       ├──→ User callback (lambda tick: ...)
    │       └──→ Metrics (latency histogram)
    │
    └──→ Stream Health Monitor (updates freshness)
```

### 6.3 Order Event Flow

```
User calls handle.buy(quantity=100)
    │
    ▼
InstrumentHandle.buy()
    │
    ▼
Account.place_order(OrderRequest)
    │
    ▼
RiskCheckedExecutionPort.place_order()
    │
    ├──→ PreTradeRiskChecker.check()
    │       │
    │       ├──→ ALLOW → continue
    │       └──→ DENY → return OrderResponse.fail(error_code="RISK_DENIED")
    │                   │
    │                   └──→ Publish RISK_REJECTED event
    │
    ▼
ExecutionPort.place_order() (broker adapter)
    │
    ▼
Broker HTTP API
    │
    ▼
OrderResponse
    │
    ├──→ Publish ORDER_PLACED event
    │       │
    │       ├──→ PortfolioEngine (updates pending orders)
    │       └──→ User callback (if subscribed)
    │
    └──→ Return to caller

─── Later, via WebSocket ───

Order update frame
    │
    ▼
Decoder → Order (updated status)
    │
    ▼
Order Engine processes update
    │
    ├──→ Publish ORDER_UPDATED event
    │       │
    │       ├──→ PortfolioEngine (updates order state)
    │       └──→ User callback
    │
    └──→ If fill: Publish TRADE event
            │
            ├──→ PortfolioEngine (updates position, balance)
            ├──→ Publish POSITION_CHANGED event
            └──→ User callback
```

### 6.4 Connection Recovery Event Flow

```
WebSocket disconnect detected
    │
    ▼
Transport Monitor publishes BROKER_DISCONNECTED
    │
    ├──→ Router marks broker unhealthy
    │       │
    │       └──→ Future routing requests skip this broker
    │
    └──→ Recovery Engine initiates recovery
            │
            ├──→ Backoff wait (exponential: 1s, 2s, 4s, 8s, max 60s)
            │
            ├──→ Reconnect transport
            │       │
            │       ├──→ Success → Re-authenticate
            │       │              │
            │       │              ├──→ Success → Resubscribe to all active subscriptions
            │       │              │              │
            │       │              │              ├──→ Reconcile orders (fetch orderbook)
            │       │              │              │
            │       │              │              ├──→ Reconcile positions
            │       │              │              │
            │       │              │              └──→ Publish BROKER_CONNECTED
            │       │              │                      │
            │       │              │                      └──→ Router marks healthy
            │       │              │
            │       │              └──→ Fail → Publish TOKEN_EXPIRED → re-auth
            │       │
            │       └──→ Fail → Retry with backoff
            │
            └──→ Max retries exhausted → publish SERVICE_FAILED
```

---

## Phase 7 — Broker Provider Framework

### 7.1 Design Goal

Adding a new broker should require:
1. **One adapter file** implementing the three ports.
2. **One mapper file** translating broker DTOs ↔ domain entities.
3. **One resolver file** for instrument resolution.
4. **One capabilities file** declaring what the broker supports.
5. **Zero changes** to existing code (Open/Closed Principle).

### 7.2 Provider Protocol Hierarchy

```python
# providers/ports.py

@runtime_checkable
class MarketDataPort(Protocol):
    """Read-only market data operations."""

    async def get_quote(self, instrument: Instrument) -> Quote: ...
    async def get_ltp(self, instrument: Instrument) -> Decimal: ...
    async def get_depth(self, instrument: Instrument) -> MarketDepth: ...
    async def get_history(self, instrument: Instrument, *, timeframe: str,
                          from_date: date | None, to_date: date | None) -> HistoricalSeries: ...
    async def get_option_chain(self, underlying: Instrument, *, expiry: date | None) -> OptionChain: ...
    async def get_future_chain(self, underlying: Instrument) -> FutureChain: ...
    async def search_instruments(self, query: str) -> list[Instrument]: ...

@runtime_checkable
class ExecutionPort(Protocol):
    """Order execution operations (risk-gated at the Session level)."""

    async def place_order(self, request: OrderRequest) -> OrderResponse: ...
    async def cancel_order(self, order_id: str) -> OrderResponse: ...
    async def modify_order(self, request: ModifyOrderRequest) -> OrderResponse: ...
    async def get_positions(self) -> list[Position]: ...
    async def get_balance(self) -> Balance: ...
    async def get_orders(self) -> list[Order]: ...
    async def get_trades(self) -> list[Trade]: ...
    async def get_holdings(self) -> list[Holding]: ...

@runtime_checkable
class StreamingPort(Protocol):
    """Real-time streaming operations."""

    async def subscribe_quotes(self, instruments: list[Instrument],
                               on_tick: Callable[[Quote], None]) -> Subscription: ...
    async def subscribe_depth(self, instruments: list[Instrument],
                              on_depth: Callable[[MarketDepth], None]) -> Subscription: ...
    async def subscribe_orders(self, on_update: Callable[[Order], None]) -> Subscription: ...
    async def unsubscribe(self, subscription: Subscription) -> None: ...
```

### 7.3 Provider Registration & Discovery

```python
# providers/registry.py

class ProviderRegistry:
    """Registry of available providers with their capabilities and ports.

    Providers are registered at startup via the bootstrap process.
    Discovery is via entry_points (for plugin providers) or explicit registration.
    """

    def register(
        self,
        broker_id: str,
        capabilities: ProviderCapabilities,
        market_data_port: MarketDataPort | None = None,
        execution_port: ExecutionPort | None = None,
        streaming_port: StreamingPort | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> None: ...
```

**Plugin discovery via entry_points:**

```toml
# pyproject.toml for a third-party broker package
[project.entry-points."brokers.providers"]
my_broker = "my_broker_pkg.adapter:MyBrokerProvider"
```

```python
# The bootstrap process discovers providers:
def discover_providers() -> dict[str, type]:
    """Discover broker providers via entry_points."""
    providers = {}
    for ep in importlib.metadata.entry_points(group="brokers.providers"):
        providers[ep.name] = ep.load()
    return providers
```

### 7.4 Extension Registration

```python
# Each broker registers its extensions during adapter construction

class DhanAdapter:
    """Dhan broker adapter — implements MarketDataPort, ExecutionPort, StreamingPort."""

    def __init__(self, client: DhanHttpClient, ...):
        self._client = client
        # ... other init

        # Register Dhan-specific extensions
        self._extensions = {
            "depth20": DhanDepth20Extension(client),
            "depth200": DhanDepth200Extension(client),
            "forever_orders": DhanForeverOrderExtension(client),
            "super_orders": DhanSuperOrderExtension(client),
        }

    @property
    def extensions(self) -> dict[str, Any]:
        return self._extensions
```

### 7.5 Dependency Injection

```python
# bootstrap/bootstrap.py — the composition root

async def bootstrap_session(
    *,
    broker_ids: list[str],
    dhan_client_id: str = "",
    dhan_access_token: str = "",
    upstox_access_token: str = "",
    routing_policy: SourceSelectionPolicy | None = None,
    risk_limits: RiskLimits | None = None,
    cache: Cache | None = None,
    event_bus: EventBus | None = None,
) -> Session:
    """Bootstrap a fully wired Session with dependency injection.

    This is the ONLY place where concrete classes are wired together.
    All other modules depend on abstractions (Protocols, ABCs).
    """
    # 1. Infrastructure
    event_bus = event_bus or EventBus()
    cache = cache or MemoryCache()
    time_service = SystemTimeService()
    health_registry = HealthRegistry()
    metrics = MetricsRegistry()

    # 2. Providers
    registry = ProviderRegistry()
    for broker_id in broker_ids:
        adapter = _create_adapter(broker_id, ...)
        caps = _capabilities_for(broker_id)
        registry.register(
            broker_id=broker_id,
            capabilities=caps,
            market_data_port=adapter,
            execution_port=_wrap_with_risk(adapter, ...),
            streaming_port=adapter,
            extensions=adapter.extensions,
        )

    # 3. Routing
    policy = routing_policy or _auto_select_policy(broker_ids)
    router = ProviderRouter(registry=registry, policy=policy)

    # 4. Session
    session = Session(
        registry=registry,
        router=router,
        event_bus=event_bus,
        cache=cache,
        health=health_registry,
        metrics=metrics,
    )

    return session
```

### 7.6 Adding a New Broker — Checklist

```
1. Create brokers/mybroker/ directory
2. Implement MyBrokerAdapter (MarketDataPort + ExecutionPort + StreamingPort)
3. Implement MyBrokerMapper (DTO → domain entities)
4. Implement MyBrokerResolver (InstrumentResolver)
5. Declare MyBrokerCapabilities (ProviderCapabilities)
6. Implement streaming/ (market_feed, order_feed, decoder)
7. Implement auth/ (token_manager)
8. Implement extensions/ (broker-specific features)
9. Add factory function in bootstrap/factory.py
10. Add entry_point in pyproject.toml (for plugin discovery)
11. Write contract tests (must pass the contract suite)
12. Write integration tests (against sandbox/test environment)
13. Run certification pipeline (see Phase 8)
```

---

## Phase 8 — Testing Architecture

### 8.1 Testing Pyramid

```
                    ┌─────────┐
                    │   Soak   │  ← 2-5 tests: 24h+ continuous run
                    │  Tests   │
                    └─────────┘
                   ┌───────────┐
                   │ Recovery  │  ← 5-10 tests: disconnect/reconnect scenarios
                   │  Tests    │
                   └───────────┘
                  ┌─────────────┐
                  │    E2E      │  ← 10-20 tests: full workflow through paper broker
                  │   Tests     │
                  └─────────────┘
                 ┌───────────────┐
                 │ Integration   │  ← 50-100 tests: adapter + real HTTP (sandbox)
                 │    Tests      │
                 └───────────────┘
                ┌─────────────────┐
                │  Performance    │  ← 10-20 tests: throughput, latency, memory
                │    Tests        │
                └─────────────────┘
               ┌───────────────────┐
               │  Contract Tests   │  ← 100+ tests: every port method, every broker
               │    (per broker)   │
               └───────────────────┘
              ┌─────────────────────┐
              │   Architecture      │  ← 20-30 tests: dependency rules, no God Objects
              │     Tests           │
              └─────────────────────┘
             ┌───────────────────────┐
             │     Unit Tests        │  ← 500+ tests: pure domain logic, mappers
             │   (fastest, most)     │
             └───────────────────────┘
```

### 8.2 Architecture Tests

Architecture tests enforce structural rules at the package level. They use static
analysis (import graph, AST inspection) to verify that dependencies flow in the
correct direction.

```python
# tests/architecture/test_dependency_rules.py

class TestDependencyRules:
    """Enforce that dependency directions follow the clean architecture rules."""

    def test_domain_imports_nothing_external(self):
        """domain/ must not import from any other brokers/ package."""
        domain_imports = get_imports("brokers/domain")
        forbidden = {"brokers.api", "brokers.providers", "brokers.brokers",
                     "brokers.infrastructure", "brokers.bootstrap"}
        assert not (set(domain_imports) & forbidden)

    def test_providers_only_import_domain(self):
        """providers/ must only import from domain/."""
        provider_imports = get_imports("brokers/providers")
        allowed = {"brokers.domain"}
        forbidden = {"brokers.api", "brokers.brokers", "brokers.infrastructure",
                     "brokers.bootstrap"}
        assert not (set(provider_imports) & forbidden)

    def test_no_circular_imports(self):
        """No circular imports anywhere in the package."""
        graph = build_import_graph("brokers")
        cycles = detect_cycles(graph)
        assert cycles == [], f"Circular imports detected: {cycles}"

    def test_no_broker_names_in_domain(self):
        """domain/ must not reference any specific broker by name."""
        domain_files = get_python_files("brokers/domain")
        for f in domain_files:
            content = f.read_text()
            assert "dhan" not in content.lower()
            assert "upstox" not in content.lower()

    def test_no_any_type_hints_in_public_api(self):
        """api/ must not use Any type hints in public methods."""
        api_files = get_python_files("brokers/api")
        for f in api_files:
            tree = ast.parse(f.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.AnnAssign) and isinstance(node.annotation, ast.Name):
                    assert node.annotation.id != "Any", f"Any type in {f.name}"
```

### 8.3 Unit Tests

Unit tests cover pure domain logic with no IO.

```python
# tests/unit/test_option_chain.py

class TestOptionChain:
    def test_strikes_sorted_ascending(self):
        chain = make_test_chain(strikes=[100, 50, 200, 150])
        assert chain.strikes == [50, 100, 150, 200]

    def test_atm_returns_closest_strike(self):
        chain = make_test_chain(strikes=[100, 110, 120])
        atm = chain.atm(spot=Decimal("115"))
        assert atm.strike == 120  # 120 is closer to 115 than 110

    def test_itm_calls_when_spot_above_strike(self):
        chain = make_test_chain(strikes=[100, 110, 120])
        itm_calls = chain.itm(spot=Decimal("115"), option_type=OptionType.CE)
        assert all(o.strike < 115 for o in itm_calls)

    def test_pcr_computes_put_call_ratio(self):
        chain = make_test_chain_with_oi(
            calls_oi=[100, 200, 300],
            puts_oi=[150, 250, 350],
        )
        assert chain.pcr == Decimal("750") / Decimal("600")  # total puts / total calls
```

### 8.4 Contract Tests

Contract tests verify that every broker adapter conforms to the port protocols.
A **shared abstract test suite** is run against every adapter.

```python
# tests/contract/test_market_data_port_contract.py

class MarketDataPortContractSuite(ABC):
    """Abstract contract suite that every MarketDataPort implementation must pass.

    Subclass this for each broker and implement the abstract fixtures.
    """

    @abstractmethod
    def make_port(self) -> MarketDataPort:
        """Create a configured MarketDataPort instance."""
        ...

    @abstractmethod
    def test_instrument(self) -> Instrument:
        """An instrument that exists on this broker."""
        ...

    @pytest.mark.asyncio
    async def test_get_quote_returns_typed_quote(self):
        port = self.make_port()
        quote = await port.get_quote(self.test_instrument())
        assert isinstance(quote, Quote)
        assert quote.ltp > 0
        assert isinstance(quote.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_get_ltp_returns_decimal(self):
        port = self.make_port()
        ltp = await port.get_ltp(self.test_instrument())
        assert isinstance(ltp, Decimal)
        assert ltp > 0

    @pytest.mark.asyncio
    async def test_get_history_returns_historical_series(self):
        port = self.make_port()
        series = await port.get_history(
            self.test_instrument(),
            timeframe="1D",
            from_date=date.today() - timedelta(days=30),
            to_date=date.today(),
        )
        assert isinstance(series, HistoricalSeries)
        assert len(series.bars) > 0
        assert all(isinstance(b, HistoricalBar) for b in series.bars)

    @pytest.mark.asyncio
    async def test_unknown_instrument_raises_not_found(self):
        port = self.make_port()
        fake = Instrument(symbol="FAKE999", exchange=Exchange.NSE, asset_class=AssetClass.EQUITY)
        with pytest.raises(InstrumentNotFoundError):
            await port.get_quote(fake)


class TestDhanMarketDataContract(MarketDataPortContractSuite):
    def make_port(self):
        return create_dhan_adapter(client_id="test", access_token="test")

    def test_instrument(self):
        return Instrument(symbol="RELIANCE", exchange=Exchange.NSE, asset_class=AssetClass.EQUITY)


class TestUpstoxMarketDataContract(MarketDataPortContractSuite):
    def make_port(self):
        return create_upstox_adapter(access_token="test")

    def test_instrument(self):
        return Instrument(symbol="RELIANCE", exchange=Exchange.NSE, asset_class=AssetClass.EQUITY)


class TestPaperMarketDataContract(MarketDataPortContractSuite):
    def make_port(self):
        return create_paper_adapter()

    def test_instrument(self):
        return Instrument(symbol="RELIANCE", exchange=Exchange.NSE, asset_class=AssetClass.EQUITY)
```

### 8.5 Integration Tests

Integration tests run against broker sandbox/test environments with real HTTP calls.
They are tagged and can be skipped in CI when credentials are not available.

```python
# tests/integration/test_dhan_integration.py

@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("DHAN_ACCESS_TOKEN"), reason="No Dhan credentials")
class TestDhanIntegration:

    @pytest.fixture
    async def session(self):
        return await Session.create(
            brokers=["dhan"],
            dhan_client_id=os.getenv("DHAN_CLIENT_ID"),
            dhan_access_token=os.getenv("DHAN_ACCESS_TOKEN"),
        )

    @pytest.mark.asyncio
    async def test_full_quote_workflow(self, session):
        reliance = session.instrument("RELIANCE", Exchange.NSE)
        quote = await reliance.quote()
        assert quote.ltp > 0
        assert quote.symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_option_chain_workflow(self, session):
        nifty = session.instrument("NIFTY", Exchange.NFO)
        chain = await nifty.option_chain()
        assert len(chain.strikes) > 0
        assert chain.expiry is not None
```

### 8.6 Performance Tests

```python
# tests/performance/test_streaming_throughput.py

@pytest.mark.performance
class TestStreamingThroughput:

    @pytest.mark.asyncio
    async def test_quote_stream_handles_10000_ticks_per_second(self, paper_session):
        """Stream must handle at least 10,000 ticks/sec without backpressure."""
        handle = paper_session.instrument("RELIANCE", Exchange.NSE)
        count = 0

        async def consumer():
            async for tick in handle.stream_quotes():
                nonlocal count
                count += 1

        # Inject 10,000 ticks
        await paper_session.inject_ticks("RELIANCE", count=10000, rate=10000)

        await asyncio.wait_for(consumer(), timeout=5.0)
        assert count >= 10000

    @pytest.mark.asyncio
    async def test_batch_ltp_completes_under_1_second(self, session):
        """Batch LTP for 100 symbols must complete in under 1 second."""
        symbols = [f"SYM{i}" for i in range(100)]
        start = time.monotonic()
        results = await session.ltp_batch(symbols, Exchange.NSE)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0
```

### 8.7 Recovery Tests

```python
# tests/recovery/test_connection_recovery.py

@pytest.mark.recovery
class TestConnectionRecovery:

    @pytest.mark.asyncio
    async def test_stream_recovers_after_disconnect(self, session):
        """Stream must auto-recover after transport disconnect."""
        handle = session.instrument("RELIANCE", Exchange.NSE)
        ticks_before = []
        ticks_after = []

        sub1 = await handle.subscribe_quotes(on_tick=ticks_before.append)

        # Simulate disconnect
        await session.simulate_disconnect("dhan")

        # Wait for recovery
        await asyncio.sleep(2.0)  # backoff + reconnect

        # Verify new ticks arrive after recovery
        await asyncio.sleep(1.0)
        assert len(ticks_after) > 0

        await sub1.cancel()

    @pytest.mark.asyncio
    async def test_orders_preserved_after_reconnect(self, session):
        """Orders placed before disconnect must still be visible after recovery."""
        account = session.account()
        response = await account.place_order(
            OrderRequest(symbol="RELIANCE", exchange=Exchange.NSE, ...)
        )
        order_id = response.order_id

        await session.simulate_disconnect("dhan")
        await asyncio.sleep(2.0)

        orders = await account.get_orders()
        assert any(o.order_id == order_id for o in orders)
```

### 8.8 Soak Tests

```python
# tests/soak/test_24h_streaming.py

@pytest.mark.soak
@pytest.mark.skipif(not os.getenv("RUN_SOAK_TESTS"), reason="Soak tests not enabled")
class Test24HourStreaming:

    @pytest.mark.asyncio
    async def test_stream_stable_for_24_hours(self, session):
        """Stream must remain stable for 24 hours without manual intervention.

        Monitors:
        - No memory leak (RSS growth < 100MB over 24h)
        - No missed ticks (sequence gap detection)
        - Auto-recovery from any disconnects
        - Stream health remains 'healthy' or 'degraded' (never 'failed')
        """
        handle = session.instrument("RELIANCE", Exchange.NSE)
        stats = SoakStats()

        sub = await handle.subscribe_quotes(
            on_tick=lambda t: stats.record_tick(t)
        )

        await asyncio.sleep(24 * 3600)  # 24 hours

        await sub.cancel()

        # Assertions
        assert stats.memory_growth_mb < 100
        assert stats.sequence_gaps == 0
        assert stats.max_disconnect_time_s < 60
```

### 8.9 Broker Certification Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                  BROKER CERTIFICATION PIPELINE                       │
│                                                                     │
│  Stage 1: Contract Tests                                            │
│  ├── All MarketDataPort methods return typed entities              │
│  ├── All ExecutionPort methods return OrderResponse                │
│  ├── All StreamingPort methods return Subscription                 │
│  ├── No raw broker DTOs leak through                               │
│  └── Error handling: broker errors → domain exceptions             │
│  Pass rate: 100% required                                           │
│                                                                     │
│  Stage 2: Integration Tests (Sandbox)                               │
│  ├── Quote, LTP, Depth, History return valid data                  │
│  ├── Option chain, Future chain return valid structures             │
│  ├── Order placement, cancellation, modification succeed            │
│  ├── Positions, holdings, balance return valid data                 │
│  └── Streaming: quotes and order updates received                   │
│  Pass rate: 100% required                                           │
│                                                                     │
│  Stage 3: Recovery Tests                                            │
│  ├── Stream recovers after disconnect (under 30s)                   │
│  ├── Orders preserved after reconnect                               │
│  ├── Token refresh works without manual intervention                │
│  └── Circuit breaker opens on repeated failures                     │
│  Pass rate: 100% required                                           │
│                                                                     │
│  Stage 4: Performance Tests                                         │
│  ├── Quote latency < 100ms (p99)                                    │
│  ├── Order placement latency < 500ms (p99)                          │
│  ├── Stream throughput > 1000 ticks/sec                             │
│  └── Batch LTP for 100 symbols < 2s                                 │
│  Pass rate: 90% required (latency can vary by network)              │
│                                                                     │
│  Stage 5: Soak Test (4 hours minimum)                               │
│  ├── No memory leak (< 50MB growth in 4h)                           │
│  ├── No stream drops without recovery                               │
│  ├── No unrecoverable error states                                  │
│  └── All metrics within expected ranges                             │
│  Pass rate: 100% required                                           │
│                                                                     │
│  ─────────────────────────────────────────────                      │
│  CERTIFICATION: All stages pass → broker is certified               │
│  for production use.                                                │
│                                                                     │
│  Certification is valid for one release cycle. Re-certify on         │
│  any breaking change in the broker API or SDK interface.            │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.10 Thread Safety Tests

```python
# tests/architecture/test_thread_safety.py

class TestThreadSafety:

    @pytest.mark.asyncio
    async def test_concurrent_quote_reads(self, session):
        """100 concurrent quote reads must not corrupt state."""
        handle = session.instrument("RELIANCE", Exchange.NSE)

        async def read_quote():
            return await handle.quote()

        results = await asyncio.gather(*[read_quote() for _ in range(100)])
        assert all(isinstance(r, Quote) for r in results)
        assert all(r.symbol == "RELIANCE" for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_order_placement(self, paper_session):
        """10 concurrent orders must all be processed (no lost orders)."""
        account = paper_session.account()
        handle = paper_session.instrument("RELIANCE", Exchange.NSE)

        async def place_one():
            return await handle.buy(quantity=1)

        responses = await asyncio.gather(*[place_one() for _ in range(10)])
        assert all(r.success for r in responses)
        assert len({r.order_id for r in responses}) == 10  # all unique
```

---

## Phase 9 — Implementation Roadmap

### Milestone 0: Domain Model Refactoring (Weeks 1-2)

**Purpose:** Refactor the domain layer to separate identity from runtime state and
introduce the aggregate roots.

**Deliverables:**
- `Instrument` as pure immutable identity (no behavior)
- `InstrumentHandle` as session-scoped entity with behavior
- `OptionChain` and `OptionContract` as proper aggregates
- `Account` as execution aggregate root
- `Greeks` typed value object (replacing `dict[str, Any]`)
- New enums: `AssetClass`, `OptionType`, `ExerciseStyle`, `Currency`

**Dependencies:** None (this is the foundation)

**Acceptance Criteria:**
- All existing domain entities preserved with backward-compatible aliases
- New types compile cleanly with mypy --strict
- Unit tests pass for all domain types
- Architecture test: `domain/` imports nothing external

**Testing Requirements:**
- Unit tests for all new types
- Architecture test for dependency rules
- mypy --strict passes on `domain/`

**Architecture Validation:**
- No God Objects (cyclomatic complexity < 15 per class)
- No `Any` types in domain layer
- All entities frozen where stateless

**Code Review Checklist:**
- [ ] No behavior (IO methods) on Instrument
- [ ] All value objects frozen
- [ ] No broker names in domain/
- [ ] No imports from outside domain/ in domain/
- [ ] Greeks typed (not dict[str, Any])

**Exit Criteria:**
- 100% unit test pass
- mypy --strict clean
- Architecture tests pass

---

### Milestone 1: Provider Framework (Weeks 3-4)

**Purpose:** Extract the provider abstraction from the existing gateway/router/registry
into a clean, extensible framework.

**Deliverables:**
- `providers/ports.py` with `MarketDataPort`, `ExecutionPort`, `StreamingPort`
  Protocols
- `providers/registry.py` with `ProviderRegistry`
- `providers/routing/` with `ProviderRouter` (refactored from `BrokerRouter`)
- `providers/capabilities.py` with split `DataCapabilities`, `ExecutionCapabilities`,
  `StreamingCapabilities`, `ProviderCapabilities`
- `providers/extensions/` with typed extension Protocols
- Entry point discovery mechanism

**Dependencies:** Milestone 0

**Acceptance Criteria:**
- Existing adapters (Dhan, Upstox, Paper) work unchanged through new framework
- `ProviderRegistry` replaces `BrokerRegistry` with backward-compatible alias
- Extension protocols defined for all existing extensions (depth20, forever_orders, etc.)

**Testing Requirements:**
- Contract test suite abstract base for each port
- Unit tests for router and registry
- Integration test: existing adapters pass through new framework

**Architecture Validation:**
- `providers/` imports only from `domain/`
- No circular dependencies
- All ports are `runtime_checkable` Protocols

**Code Review Checklist:**
- [ ] All ports are Protocols (not ABCs — enables structural typing)
- [ ] No `Any` in port method signatures
- [ ] Extension protocols are typed
- [ ] Router is provider-agnostic (no broker names)

**Exit Criteria:**
- All existing tests pass
- Contract suite runs against all three brokers
- mypy --strict clean on `providers/`

---

### Milestone 2: Session & Public API (Weeks 5-6)

**Purpose:** Build the user-facing API layer that wraps the provider framework with
the InstrumentHandle/Account/Session abstraction.

**Deliverables:**
- `api/session.py` — `Session` root object
- `api/instrument_handle.py` — `InstrumentHandle` with behavior
- `api/account.py` — `Account` aggregate
- `api/option_chain.py` — `OptionChainHandle`
- `api/extensions.py` — `ExtensionRegistry`
- `api/builders.py` — `SessionBuilder` fluent API
- `bootstrap/bootstrap.py` — `bootstrap_session()` (replaces `bootstrap_broker_stack`)

**Dependencies:** Milestones 0, 1

**Acceptance Criteria:**
- Quick start example (5 lines) works
- All existing `bootstrap_broker_stack` use cases work through `bootstrap_session`
- `InstrumentHandle` provides quote(), ltp(), depth(), history(), subscribe(),
  buy(), sell(), option_chain(), future_chain()
- Extensions accessed via `handle.extensions.depth20` (typed, None-safe)

**Testing Requirements:**
- E2E tests through paper broker
- Unit tests for SessionBuilder
- Integration test: full workflow (quote → order → position → close)

**Architecture Validation:**
- `api/` imports only from `domain/` and `providers/`
- No direct broker references in `api/`
- All public methods typed (no `Any`)

**Code Review Checklist:**
- [ ] No broker names in api/
- [ ] All methods have docstrings
- [ ] Async-first (no sync-only methods)
- [ ] Extensions are None-safe
- [ ] Session is the single entry point

**Exit Criteria:**
- E2E test suite passes
- Public API documented with examples
- `bootstrap_broker_stack` deprecated with alias to `bootstrap_session`

---

### Milestone 3: Event-Driven Architecture (Weeks 7-8)

**Purpose:** Wire all engines through the event bus and implement the recovery engine.

**Deliverables:**
- All engines publish/consume events via `EventBus`
- `RecoveryEngine` for connection recovery
- `PortfolioEngine` for real-time portfolio state
- Event payload validation (strict mode for tests)
- Event flow documentation

**Dependencies:** Milestones 0, 1, 2

**Acceptance Criteria:**
- Order lifecycle events published at each state transition
- Stream disconnection triggers automatic recovery
- Portfolio state updates in real-time from trade events
- All events validated against `EventPayload` contracts

**Testing Requirements:**
- Recovery tests (disconnect/reconnect scenarios)
- Event ordering tests (ORDER_PLACED before ORDER_UPDATED)
- Event payload validation tests

**Code Review Checklist:**
- [ ] All state transitions publish events
- [ ] No engine directly calls another engine (use events)
- [ ] Recovery backoff is exponential
- [ ] Event payloads match contracts

**Exit Criteria:**
- Recovery tests pass
- No event payload contract violations in test runs

---

### Milestone 4: Streaming Improvements (Weeks 9-10)

**Purpose:** Enhance the streaming engine with subscription deduplication,
backpressure handling, and improved health monitoring.

**Deliverables:**
- Subscription deduplication (Flyweight pattern) — one broker subscription per
  instrument, fanned out to multiple consumers
- Bounded per-consumer queues with configurable drop policy
- Enhanced `StreamHealth` monitoring with freshness, transport, and subscription states
- Backpressure metrics (queue depth, drop count)

**Dependencies:** Milestones 0-3

**Acceptance Criteria:**
- 10 InstrumentHandles subscribing to the same instrument result in 1 broker subscription
- Slow consumer does not block the WebSocket read loop
- Stream health transitions are published as events

**Testing Requirements:**
- Performance test: 10,000 ticks/sec throughput
- Recovery test: stream recovers after disconnect
- Soak test: 4-hour continuous streaming

**Exit Criteria:**
- Performance tests pass
- Soak test passes (4h, < 50MB memory growth)

---

### Milestone 5: Certification Pipeline (Weeks 11-12)

**Purpose:** Build the automated certification pipeline for broker onboarding.

**Deliverables:**
- `tests/contract/` with abstract contract suites for all three ports
- `tests/integration/` with sandbox integration tests
- `tests/recovery/` with disconnect/reconnect scenarios
- `tests/performance/` with latency and throughput benchmarks
- `tests/soak/` with long-running stability tests
- `scripts/certify_broker.py` — runs all stages and produces certification report

**Dependencies:** Milestones 0-4

**Acceptance Criteria:**
- `python scripts/certify_broker.py --broker dhan` runs all 5 stages
- Certification report generated with pass/fail per stage
- Paper broker certified (serves as reference implementation)

**Exit Criteria:**
- Paper broker fully certified
- Dhan and Upstox certified against sandbox (when credentials available)

---

### Milestone 6: Provider Plugin System (Weeks 13-14)

**Purpose:** Enable third-party broker providers via plugin discovery.

**Deliverables:**
- Entry point discovery (`importlib.metadata.entry_points`)
- Provider package template/scaffold
- Documentation for third-party provider development
- Example: CSV provider (data-only) as a plugin

**Dependencies:** Milestones 0-5

**Acceptance Criteria:**
- Third-party package discovered automatically when installed
- CSV provider works as a data-only provider (no execution)
- Provider development guide published

**Exit Criteria:**
- CSV provider certified through the pipeline
- Plugin discovery works in fresh environment

---

### Milestone 7: Hardening & Documentation (Weeks 15-16)

**Purpose:** Production hardening, comprehensive documentation, and final review.

**Deliverables:**
- Full API documentation (docstrings → Sphinx)
- Architecture decision records (ADRs) for key decisions
- Migration guide from current `bootstrap_broker_stack` to `bootstrap_session`
- Performance benchmarking report
- Security review (token handling, credential storage)
- Thread safety audit

**Dependencies:** Milestones 0-6

**Exit Criteria:**
- Documentation complete and reviewed
- All milestones' exit criteria met
- No open P0/P1 bugs
- Security review passed

---

## Phase 10 — Future Trading Operating System

### 10.1 How the Broker SDK Becomes the Foundation

The Broker SDK is designed to be the **single source of truth** for all market data
and order execution in the Trading OS. Every higher-level module depends on the SDK's
public API (`Session`, `InstrumentHandle`, `Account`) and never touches broker-specific
code.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TRADING OPERATING SYSTEM                           │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Scanner  │  │ Strategy │  │ Portfolio │  │   Risk   │           │
│  │ Engine   │  │  Engine  │  │ Analytics │  │  Engine  │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │              │                  │
│  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐           │
│  │  Replay  │  │  Back-   │  │  Auto-   │  │  Order   │           │
│  │  Engine  │  │  tester  │  │  mation  │  │  Flow    │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │              │                  │
│       └──────────────┴──────────────┴──────────────┘                 │
│                              │                                       │
│                    ┌─────────▼──────────┐                           │
│                    │   BROKER SDK API   │                           │
│                    │                    │                           │
│                    │  Session           │                           │
│                    │  InstrumentHandle  │                           │
│                    │  Account           │                           │
│                    │  EventBus          │                           │
│                    └─────────┬──────────┘                           │
│                              │                                       │
│                    ┌─────────▼──────────┐                           │
│                    │   PROVIDERS        │                           │
│                    │  Dhan / Upstox /   │                           │
│                    │  Paper / CSV /     │                           │
│                    │  Replay / FIX      │                           │
│                    └────────────────────┘                           │
└─────────────────────────────────────────────────────────────────────┘
```

### 10.2 Module Integration Patterns

#### Scanner
```python
# Scanner uses batch market data from the SDK
session = await Session.create(brokers=["dhan", "upstox"])

# Batch LTP for entire universe
prices = await session.ltp_batch(universe, Exchange.NSE)

# Filter based on price action
candidates = [s for s in universe if prices[s] > threshold]

# Subscribe to real-time updates for candidates
for sym in candidates:
    handle = session.instrument(sym, Exchange.NSE)
    await handle.subscribe_quotes(on_tick=scanner.on_tick)
```

#### Strategy Engine
```python
# Strategy receives events from the SDK's EventBus
class MyStrategy:
    def __init__(self, session: Session):
        self.session = session
        self.session.event_bus.subscribe(EventType.TICK, self.on_tick)
        self.session.event_bus.subscribe(EventType.TRADE, self.on_fill)

    async def on_tick(self, event: DomainEvent):
        # Strategy logic using event.payload
        if self.should_buy(event.payload):
            handle = self.session.instrument(event.symbol, ...)
            await handle.buy(quantity=100)

    async def on_fill(self, event: DomainEvent):
        # Update strategy state on fill
        self.position_manager.on_fill(event.payload)
```

#### Replay / Backtesting
```python
# Replay provider implements MarketDataPort + StreamingPort
# but NOT ExecutionPort — orders are simulated
replay_session = await Session.create(
    brokers=["replay"],
    replay_data_source="historical_data.parquet",
    replay_start_date=date(2024, 1, 1),
    replay_end_date=date(2024, 12, 31),
    replay_speed=10.0,  # 10x speed
)

# Same API as live trading — strategy code is identical
handle = replay_session.instrument("RELIANCE", Exchange.NSE)
async for tick in handle.stream_quotes():
    # Strategy runs on replayed data
    ...
```

#### Risk Engine
```python
# Risk engine wraps the SDK's execution provider
# (already implemented as RiskCheckedTradingPort)

# The Trading OS can add additional risk layers:
class MaxDrawdownRiskGate:
    """Wraps ExecutionPort with drawdown-based risk gating."""

    def __init__(self, inner: ExecutionPort, max_drawdown: Decimal):
        self._inner = inner
        self._max_drawdown = max_drawdown

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        if self._current_drawdown > self._max_drawdown:
            return OrderResponse.fail("Max drawdown exceeded", error_code="DRAWDOWN_LIMIT")
        return await self._inner.place_order(request)
```

#### Portfolio Analytics
```python
# Portfolio analytics subscribes to the SDK's EventBus
class PortfolioAnalytics:
    def __init__(self, session: Session):
        self.session = session
        self.session.event_bus.subscribe(EventType.POSITION_CHANGED, self.on_position)
        self.session.event_bus.subscribe(EventType.TICK, self.on_tick)

    async def on_tick(self, event: DomainEvent):
        # Recalculate Sharpe, drawdown, exposure
        self._update_analytics(event.payload)

    def sharpe_ratio(self) -> Decimal:
        ...
```

#### Market Profile / Order Flow
```python
# These consume depth and tick data from the SDK
handle = session.instrument("NIFTY", Exchange.NFO)

# Depth data for order flow analysis
depth = await handle.depth()

# Subscribe to depth stream for real-time order flow
await handle.subscribe_depth(on_depth=order_flow_analyzer.on_depth)
```

### 10.3 No Architectural Changes Required

The key design property is that **the SDK's public API is stable** and sufficient
for all Trading OS modules:

| Trading OS Module | SDK API Used | Extensions Needed? |
|-------------------|-------------|-------------------|
| Scanner | `ltp_batch`, `subscribe_quotes`, `InstrumentHandle` | No |
| Strategy Engine | `EventBus`, `InstrumentHandle.buy/sell`, `Account` | No |
| Portfolio Analytics | `EventBus`, `Account.get_positions` | No |
| Risk Engine | `ExecutionPort` (wrapped), `RiskCheckedTradingPort` | No |
| Replay Engine | `Session.create(brokers=["replay"])` — ReplayProvider | New provider (plugin) |
| Backtesting | Same as Replay + PaperProvider for execution | New provider (plugin) |
| Automation | `EventBus`, `InstrumentHandle`, `Account` | No |
| AMT | `EventBus`, `Account` | No |
| Order Flow | `subscribe_depth`, `depth()` | No |
| Market Profile | `subscribe_quotes`, `history()` | No |

**No SDK changes are needed to support any Trading OS module.** New data sources
(Replay, CSV, Yahoo) are added as new providers via the plugin system — no changes
to the SDK core.

---

## Appendix A: Design Patterns Used

| Pattern | Where Applied | Why |
|---------|--------------|-----|
| **Aggregate Root** | `OptionChain`, `Account` | Consistency boundary for derivative structures and execution state |
| **Value Object** | `Instrument`, `Quote`, `Order`, `Greeks` | Immutable, compared by value, thread-safe |
| **Entity** | `InstrumentHandle`, `Position`, `Order` | Has lifecycle and mutable state |
| **Factory** | `SessionBuilder`, `create_dhan_adapter()` | Encapsulates complex object construction |
| **Abstract Factory** | `bootstrap_session()` | Creates families of related objects (providers, router, engines) |
| **Adapter** | `DhanAdapter`, `UpstoxAdapter` | Translates broker-specific APIs to domain ports |
| **Strategy** | `RoutingPolicy`, `RoutingMode` | Interchangeable routing algorithms |
| **Repository** | `ProviderRegistry`, `SharedInstrumentRegistry` | Central lookup for providers and instruments |
| **Observer** | `EventBus`, `subscribe_quotes()` | Decoupled event notification |
| **Decorator** | `RiskCheckedTradingPort`, `MaxDrawdownRiskGate` | Wraps execution with cross-cutting concerns |
| **Composite** | `OptionChain` containing `OptionContract[]` | Tree structure for derivatives |
| **Builder** | `SessionBuilder` | Fluent construction of complex Session config |
| **Specification** | `BrokerCapabilities.supports()`, capability filtering | Composable business rules for provider selection |
| **State** | Order lifecycle (PENDING → SUBMITTED → FILLED) | State-dependent behavior for orders |
| **Proxy** | `InstrumentHandle` (delegates to provider) | Lazy access to provider IO |
| **Flyweight** | Subscription deduplication in StreamOrchestrator | Shared subscription for multiple consumers |
| **Dependency Injection** | `bootstrap_session()` composition root | All dependencies injected via constructors |
| **Capability Pattern** | `ProviderCapabilities`, `ExtensionRegistry` | Runtime feature discovery and gating |
| **Plugin Architecture** | Entry point discovery for providers | Third-party extensibility without core changes |
| **Monad** | `GatewayResult[T]` with map/flat_map/recover | Functional error handling without exceptions |

---

## Appendix B: Reference Architecture Comparison

| Aspect | StockSharp | QuantConnect LEAN | Interactive Brokers | This SDK |
|--------|-----------|-------------------|--------------------|---------| 
| Instrument | `Security` (POCO) | `Symbol` + `Security` | `Contract` | `Instrument` (VO) + `InstrumentHandle` (Entity) |
| Gateway | `IConnector` | `IBrokerage` | `EClient`/`EWrapper` | `MarketDataPort` + `ExecutionPort` + `StreamingPort` |
| Communication | Message-based | Events + interfaces | Callbacks | `EventBus` + async Protocols |
| Multi-broker | Multiple Connectors | Multiple Brokerages | Single API | `ProviderRouter` with `ProviderRegistry` |
| Extensions | N/A (monolithic) | Reality Models on Security | N/A | Typed `ExtensionRegistry` with capability gating |
| Risk | Strategy-level | `BrokerageModel` | N/A | `RiskCheckedTradingPort` decorator |
| Testing | Manual | Lean CLI | TWS / IGateway | 7-layer test pyramid + certification pipeline |

---

## Appendix C: Migration Path from Current Codebase

The existing codebase is **70% compatible** with this design. The refactoring is
evolutionary, not revolutionary:

| Current | Target | Migration Effort |
|---------|--------|-----------------|
| `domain/entities.py` `Instrument` (frozen dataclass) | `Instrument` VO (add `asset_class`, `isin`, `currency`) | Small — add fields, keep frozen |
| `domain/ports.py` `TradingPort` | `ExecutionPort` (rename + refine signatures) | Small — rename + type refinement |
| `domain/ports.py` `MarketDataPort` | `MarketDataPort` (change `Instrument` param) | Small — change symbol+exchange → Instrument |
| `common/gateway.py` `UnifiedBrokerGateway` | `Session` + `InstrumentHandle` | Medium — new classes, delegate to existing router |
| `common/registry.py` `BrokerRegistry` | `ProviderRegistry` | Small — rename + add extension registry |
| `common/router.py` `BrokerRouter` | `ProviderRouter` | Small — rename |
| `common/capabilities.py` `BrokerCapabilities` | `ProviderCapabilities` (split into 3) | Medium — split dataclass |
| `common/bootstrap.py` `bootstrap_broker_stack` | `bootstrap_session` | Medium — new composition root |
| `common/pre_trade_risk.py` | Retained as-is | None |
| `infrastructure/event_bus.py` | Retained as-is | None |
| `infrastructure/streaming/` | Retained + enhanced | Small — add fan-out |
| `brokers/dhan/adapter.py` | Implement new port interfaces | Medium — change method signatures |
| `brokers/dhan/streaming/` | Retained as-is | None |

**Backward compatibility:** `bootstrap_broker_stack` will be preserved as a
deprecated alias to `bootstrap_session` for one release cycle. Existing adapter
code will work through compatibility shims.

---

*End of Architecture Design Document*

---

**Document Status:** This is a living document. It should be reviewed and updated
at each milestone completion. Architecture Decision Records (ADRs) should be created
for any deviations from this blueprint.
