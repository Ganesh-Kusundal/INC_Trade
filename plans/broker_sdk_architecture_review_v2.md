# Broker SDK — Architecture Review & Redesign Blueprint (v2)

**Prepared by:** Architecture Review Board
**Date:** July 2026
**Status:** Revised — incorporates refactoring philosophy
**Supersedes:** v1 (`broker_sdk_architecture_review.md`)

> **What changed from v1:** The v1 document proposed `InstrumentHandle` as a
> wrapper around `Instrument` + `Session`, and preserved the existing
> `UnifiedBrokerGateway → IntelligentMarketDataGateway → BrokerRouter →
> BrokerRegistry → Port` wrapper chain with backward-compatible aliases.
> The refactoring philosophy rejects both: wrapper-only classes are code
> smells, anemic domain models are code smells, and backward compatibility
> is not a goal. This v2 redesigns from first principles.

---

## Phase 1 — Architecture Review (Revised)

### 1.1 Confession: v1 Was Wrong

The v1 document made three fundamental errors:

| v1 Decision | Code Smell | Why It's Wrong |
|-------------|-----------|----------------|
| `Instrument` = passive identity VO (no behavior) | **Anemic Domain Model** | Instrument has rich domain behavior. Stripping it to a data bag moves behavior to service classes that become God Objects. |
| `InstrumentHandle` = session-scoped wrapper forwarding to providers | **Wrapper-only class** | Its sole purpose is forwarding calls. The provider does all the work. |
| Preserve `UnifiedBrokerGateway → IntelligentMarketDataGateway → Router → Registry → Port` | **Wrapper chain** (5 layers) | Four of five layers just forward. Routing could be a strategy inside the provider. |
| "Evolutionary migration with backward-compatible aliases" | **Parallel implementations** | Creates old and new coexisting. Violates "one source of truth." |

### 1.2 The Existing Codebase's Code Smells

#### Smell 1: The Gateway Wrapper Chain (CRITICAL)

```
User → UnifiedBrokerGateway → IntelligentMarketDataGateway → BrokerRouter
     → BrokerRegistry → DhanAdapter → DhanHttpClient
```

**Six layers.** Four exist solely to forward `get_ltp` to `DhanAdapter`.

**Elimination:** Delete all four wrapper classes. Replace with a single
`Provider` abstraction that internally selects the best broker using a
`RoutingStrategy` — a function, not a class hierarchy.

#### Smell 2: RiskCheckedTradingPort Is a Wrapper (MEDIUM)

Wraps `TradingPort` and forwards 7 of 8 methods unchanged. Only `place_order`
is gated.

**Elimination:** Risk gating moves inside `Account.place_order()` as a
Strategy call. No wrapper needed.

#### Smell 3: BatchFetchMixin Uses `type: ignore` (MEDIUM)

Calls `self.get_ltp()` with `# type: ignore[attr-defined]` — hidden
dependency the type system can't express.

**Elimination:** Batch ops are explicit methods on Instrument that call
`self._provider`. No mixin.

#### Smell 4: String-Based Dispatch (MEDIUM)

`_route_market()` uses `getattr(port, method)` with `Any` args and return.

**Elimination:** Each operation is a typed method. No generic dispatcher.

#### Smell 5: `extended()` Returns `Any` + `hasattr` (MEDIUM)

No type safety. String-based introspection.

**Elimination:** Extensions are typed Protocols. Provider declares them via
capabilities. Typed, capability-gated access.

#### Smell 6: Instrument Is Anemic (HIGH)

Frozen dataclass with 9 fields and zero methods. Textbook Anemic Domain Model.

**Elimination:** Instrument becomes a rich domain object owning its market
data, subscriptions, and trading operations. Delegates IO to injected
Provider but owns domain logic.

#### Smell 7: Duplicate Instrument Identity (MEDIUM)

`Instrument`, `InstrumentRef`, `ResolvedInstrument` — three overlapping types.

**Elimination:** One `Instrument` class. `InstrumentRef` deleted.
`ResolvedInstrument` is internal to the provider.

#### Smell 8: `GatewayResult` Monad Unused (LOW)

Defined with map/flat_map/recover but no method returns it.

**Elimination:** Delete. Use native exceptions + `OrderResponse`.

#### Smell 9: `HistoricalDataCoordinator` Duplicates Routing (MEDIUM)

Calls `self._router.route()` — same routing as the gateway. Two paths to
the same broker selection.

**Elimination:** Multi-source merge is a strategy inside CompositeProvider.
No separate coordinator.

#### Smell 10: Bootstrap Is a God Function (LOW)

100+ lines knowing every broker's credentials, capabilities, and policies.

**Elimination:** `Broker` factory — each broker registers itself. ~20 lines.

### 1.3 Revised Answers to Key Questions

**Q1: Is Instrument the correct Aggregate Root?**
Yes — and it must be RICH, not anemic. Instrument owns quote, history, depth,
subscriptions, and trading. It delegates IO to an injected Provider but owns
the domain logic.

**Q2: Should there be another root above Instrument?**
No. Instrument is the top-level aggregate root for market data. Account is
the top-level for execution. They are peers.

**Q3: Should Provider replace Broker?**
Yes. Provider is the single abstraction. Routing lives INSIDE the provider
as a Strategy, not in a separate Router class.

**Q4: What belongs inside Instrument?**
Identity, market data retrieval, subscription management, trading operations
(delegated to Account), option chain construction, validation, event
publication.

**Q5: What should NOT belong inside Instrument?**
Account balance, order lifecycle, portfolio P&L, HTTP/WebSocket transport,
token management, rate limiting.

**Q6: Should Instrument own Quote, History, Depth, Subscription?**
Yes. These are Instrument's state and behavior. The Provider is the IO
mechanism, not the owner.

**Q7: How should Account/Portfolio/Position/Order relate to Instrument?**
Account owns orders, positions, holdings, balance. Orders reference
Instruments. `instrument.buy()` delegates to `account.place_order()` — a
convenience, not an ownership transfer.

**Q8: Is Option inheritance correct?**
No. Option is composition: Instrument + option terms. Not a subclass.

**Q9: Should OptionChain be an Aggregate?**
Yes. Owns option contracts, enforces invariants, each option is an Instrument.

**Q10: How should extensions work?**
Typed Protocols. Provider declares support via capabilities. Access via
`instrument.extensions.depth20` returning typed extension or None.

**Q12: How would StockSharp/IB architect this?**
All three use rich instrument objects as the primary interaction point. The
connector/client is the IO mechanism injected into the instrument. No wrapper
chain. v2 follows this pattern.

### 1.4 The Core Redesign Principle

> **Instrument is a rich domain object. It owns its state and behavior. It
> delegates IO to an injected Provider. There is no wrapper, no handle, no
> session, no gateway between the user and the Instrument.**

```
User → Instrument.quote()  →  Provider.get_quote()  →  Broker HTTP
User → Instrument.buy()    →  Account.place_order() →  Provider.place_order()  →  Broker HTTP
User → Instrument.subscribe()  →  Provider.subscribe()  →  Broker WebSocket
```

**Three layers, not six.** Every layer has real responsibility.

---

## Phase 2 — Domain Model (Revised)

### 2.1 Design Principle: Rich Domain Objects

Every domain object owns its state and behavior. IO is delegated to an
injected Provider. No anemic data bags. No wrapper classes. No service
classes that operate on passive data.

### 2.2 Instrument — Rich Aggregate Root

```python
class Instrument:
    """Rich domain object — the primary aggregate root for market data.

    Owns its identity, cached market data state, active subscriptions,
    and trading operations. Delegates IO to an injected Provider.

    Created by a Broker (factory) which injects the Provider. The user
    interacts directly with Instrument — no handle, no session, no gateway.

    Thread safety: internal state protected by a lock. Identity is immutable.
    """

    def __init__(
        self,
        symbol: str,
        exchange: Exchange,
        asset_class: AssetClass,
        *,
        provider: Provider,
        lot_size: int = 1,
        tick_size: Decimal = Decimal("0.05"),
        isin: str = "",
        expiry: date | None = None,
        strike: Decimal | None = None,
        option_type: OptionType | None = None,
        underlying: Instrument | None = None,
        trading_symbol: str = "",
    ) -> None:
        # Immutable identity
        self._symbol = symbol
        self._exchange = exchange
        self._asset_class = asset_class
        self._lot_size = lot_size
        self._tick_size = tick_size
        self._isin = isin
        self._expiry = expiry
        self._strike = strike
        self._option_type = option_type
        self._underlying = underlying
        self._trading_symbol = trading_symbol

        # Injected IO delegate
        self._provider = provider

        # Mutable runtime state (thread-safe)
        self._lock = threading.RLock()
        self._cached_quote: Quote | None = None
        self._cached_depth: MarketDepth | None = None
        self._subscriptions: list[Subscription] = []

    # ── Identity (immutable) ───────────────────────────────────────

    @property
    def symbol(self) -> str: return self._symbol

    @property
    def exchange(self) -> Exchange: return self._exchange

    @property
    def asset_class(self) -> AssetClass: return self._asset_class

    @property
    def lot_size(self) -> int: return self._lot_size

    @property
    def is_derivative(self) -> bool:
        return self._asset_class in (AssetClass.FUTURE, AssetClass.OPTION)

    @property
    def is_option(self) -> bool:
        return self._asset_class == AssetClass.OPTION

    @property
    def is_expired(self) -> bool:
        return self._expiry is not None and self._expiry < date.today()

    # ── Market Data (delegates to provider, caches result) ─────────

    async def quote(self) -> Quote:
        """Fetch and cache the latest quote."""
        q = await self._provider.get_quote(self)
        with self._lock:
            self._cached_quote = q
        return q

    async def ltp(self) -> Decimal:
        """Fetch the last traded price."""
        return await self._provider.get_ltp(self)

    async def depth(self) -> MarketDepth:
        """Fetch and cache order book depth."""
        d = await self._provider.get_depth(self)
        with self._lock:
            self._cached_depth = d
        return d

    @property
    def cached_quote(self) -> Quote | None:
        """Last cached quote. No IO."""
        with self._lock:
            return self._cached_quote

    async def history(
        self, *, timeframe: str = "1D", bars: int | None = None,
        from_date: date | None = None, to_date: date | None = None,
    ) -> HistoricalSeries:
        """Fetch historical OHLCV bars."""
        return await self._provider.get_history(
            self, timeframe=timeframe, bars=bars,
            from_date=from_date, to_date=to_date,
        )

    # ── Streaming (delegates to provider, tracks subscriptions) ────

    async def subscribe_quotes(self, on_tick: Callable[[Quote], None]) -> Subscription:
        """Subscribe to real-time quote updates."""
        sub = await self._provider.subscribe_quotes([self], on_tick=on_tick)
        with self._lock:
            self._subscriptions.append(sub)
        return sub

    async def subscribe_depth(self, on_depth: Callable[[MarketDepth], None]) -> Subscription:
        """Subscribe to real-time depth updates."""
        sub = await self._provider.subscribe_depth([self], on_depth=on_depth)
        with self._lock:
            self._subscriptions.append(sub)
        return sub

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Cancel an active subscription."""
        await self._provider.unsubscribe(subscription)
        with self._lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)

    async def unsubscribe_all(self) -> None:
        """Cancel all subscriptions for this instrument."""
        with self._lock:
            subs = list(self._subscriptions)
            self._subscriptions.clear()
        for sub in subs:
            await self._provider.unsubscribe(sub)

    # ── Trading (creates orders via Account) ───────────────────────

    async def buy(
        self, quantity: int, *,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
        account: Account | None = None,
    ) -> OrderResponse:
        """Place a buy order. Delegates to Account for risk gating."""
        if account is None:
            account = self._provider.default_account
        return await account.place_order(OrderRequest(
            instrument=self, side=Side.BUY, quantity=quantity,
            order_type=order_type, price=price or Decimal("0"),
            product_type=product_type,
        ))

    async def sell(
        self, quantity: int, *,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
        account: Account | None = None,
    ) -> OrderResponse:
        """Place a sell order. Delegates to Account for risk gating."""
        if account is None:
            account = self._provider.default_account
        return await account.place_order(OrderRequest(
            instrument=self, side=Side.SELL, quantity=quantity,
            order_type=order_type, price=price or Decimal("0"),
            product_type=product_type,
        ))

    # ── Derivatives ────────────────────────────────────────────────

    async def option_chain(self, expiry: date | None = None) -> OptionChain:
        """Fetch the option chain (if this instrument is an underlying)."""
        return await self._provider.get_option_chain(self, expiry=expiry)

    async def future_chain(self) -> FutureChain:
        """Fetch the futures chain."""
        return await self._provider.get_future_chain(self)

    # ── Extensions (typed, capability-gated) ───────────────────────

    @property
    def extensions(self) -> ExtensionAccess:
        """Typed access to broker-specific extensions."""
        return self._provider.extensions.for_instrument(self)

    # ── Lifecycle ──────────────────────────────────────────────────

    async def close(self) -> None:
        """Clean up: unsubscribe all streams."""
        await self.unsubscribe_all()
```

**Why this is NOT a God Object:**

| Responsibility | How It's Handled |
|----------------|-----------------|
| Market data retrieval | Delegates to `provider.get_quote()` — 1-line methods |
| Subscription tracking | List append/remove — trivial state management |
| Trading | Delegates to `account.place_order()` — doesn't own order lifecycle |
| Caching | Stores last quote/depth — simple memoization |
| Validation | `is_derivative`, `is_expired` — pure computed properties |

Instrument is the **orchestration point**, not the implementor. Complexity
lives in the Provider (IO) and Account (order lifecycle). This is the
difference between a God Object (owns all complexity) and a rich domain
object (owns the domain contract, delegates implementation).

### 2.3 Account — Execution Aggregate Root

```python
class Account:
    """Aggregate root for the execution domain.

    Owns order placement, positions, holdings, and balance.
    Risk gating happens HERE, inside place_order — not in a wrapper.
    """

    def __init__(
        self, account_id: str, provider: Provider,
        risk_policy: RiskPolicy | None = None,
    ) -> None:
        self._account_id = account_id
        self._provider = provider
        self._risk_policy = risk_policy or RiskPolicy.no_limits()
        self._lock = threading.RLock()
        self._open_orders: dict[str, Order] = {}

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order with risk gating.

        Risk check happens HERE — not in a wrapper. If denied, returns
        OrderResponse.fail() with the reason.
        """
        # Risk gate — real responsibility, not a forwarding wrapper
        decision = await self._risk_policy.check(request, self._provider)
        if not decision.allowed:
            return OrderResponse.fail(
                message=f"Risk denied: {decision.reason}",
                error_code=decision.error_code,
            )

        # Execute — delegate to provider
        response = await self._provider.place_order(request)

        # Track order — real state management
        if response.success:
            with self._lock:
                self._open_orders[response.order_id] = Order(
                    request=request, response=response,
                )
        return response

    async def cancel_order(self, order_id: str) -> OrderResponse:
        return await self._provider.cancel_order(order_id)

    async def get_positions(self) -> list[Position]:
        return await self._provider.get_positions()

    async def get_balance(self) -> Balance:
        return await self._provider.get_balance()

    async def get_holdings(self) -> list[Holding]:
        return await self._provider.get_holdings()

    async def get_orders(self) -> list[Order]:
        return await self._provider.get_orders()

    async def get_trades(self) -> list[Trade]:
        return await self._provider.get_trades()

    async def subscribe_orders(self, on_update: Callable[[Order], None]) -> Subscription:
        return await self._provider.subscribe_orders(on_update=on_update)
```

**Why risk gating is inside Account, not in a wrapper:**

`RiskCheckedTradingPort` wraps `TradingPort` and forwards 7 of 8 methods
unchanged. That's a wrapper-only class. In v2, risk gating is a single `if`
inside `Account.place_order()` — the method that actually needs it. The risk
policy is a **Strategy** injected into Account, not a wrapper around it.

### 2.4 Order — Entity with Lifecycle

```python
class Order:
    """Order entity — owns its lifecycle.

    PENDING → SUBMITTED → PARTIALLY_FILLED → FILLED
                   ↓              ↓
              CANCELLED       CANCELLED
                   ↓              ↓
                REJECTED       REJECTED

    Publishes events on every state transition.
    """

    def __init__(self, request: OrderRequest, response: OrderResponse) -> None:
        self._request = request
        self._response = response
        self._status = response.status

    @property
    def order_id(self) -> str: return self._response.order_id

    @property
    def status(self) -> OrderStatus: return self._status

    @property
    def instrument(self) -> Instrument: return self._request.instrument

    def update_status(
        self, new_status: OrderStatus, *,
        filled_quantity: int = 0,
        average_price: Decimal = Decimal("0"),
        event_bus: EventBus | None = None,
    ) -> None:
        """Transition to a new status and publish an event."""
        old_status = self._status
        self._status = new_status
        if event_bus is not None:
            event_type = self._event_type_for_transition(new_status)
            if event_type is not None:
                event_bus.publish(DomainEvent.now(
                    event_type=event_type.value,
                    payload={"order_id": self.order_id, "status": new_status.value},
                    symbol=self.instrument.symbol,
                ))

    @staticmethod
    def _event_type_for_transition(new: OrderStatus) -> EventType | None:
        return {
            OrderStatus.OPEN: EventType.ORDER_PLACED,
            OrderStatus.PARTIALLY_FILLED: EventType.ORDER_UPDATED,
            OrderStatus.FILLED: EventType.ORDER_UPDATED,
            OrderStatus.CANCELLED: EventType.ORDER_CANCELLED,
            OrderStatus.REJECTED: EventType.ORDER_REJECTED,
        }.get(new)
```

### 2.5 OptionChain — Aggregate Root

Each option in the chain is a full `Instrument` (with provider injected).
The chain provides `atm()`, `itm()`, `otm()`, `calls`, `puts`, `strikes`.

### 2.6 Deleted Types

| Deleted Type | Reason |
|-------------|--------|
| `InstrumentHandle` (v1 proposal) | Wrapper-only class — never created |
| `InstrumentRef` | Replaced by `Instrument` itself |
| `ResolvedInstrument` | Internal to provider, not a domain type |
| `UnifiedBrokerGateway` | Wrapper chain — deleted |
| `IntelligentMarketDataGateway` | Wrapper chain — deleted |
| `BrokerRouter` | Routing → Strategy inside Provider |
| `BrokerRegistry` | Discovery → Broker factory |
| `BatchFetchMixin` | Batch ops on Instrument, no mixin |
| `RiskCheckedTradingPort` | Risk → Strategy inside Account |
| `GatewayResult[T]` | Unused monad — deleted |
| `HistoricalDataCoordinator` | Merge → Strategy inside CompositeProvider |
| `_PortAsRiskContext` | Adapter hack — deleted with risk wrapper |

---

## Phase 3 — Package Structure (Revised)

### 3.1 Package Layout — No Manager/Helper/Util/Wrapper Classes

```
brokers/
├── __init__.py                    # Public API: Broker, Instrument, Account
├── domain/                        # PURE DOMAIN — zero deps, rich objects
│   ├── instrument.py              # Instrument — rich aggregate root
│   ├── option_chain.py            # OptionChain — aggregate root
│   ├── account.py                 # Account — execution aggregate root
│   ├── order.py                   # Order — entity with lifecycle
│   ├── values.py                  # Quote, Depth, Trade, Position, Balance
│   ├── historical.py              # HistoricalBar, HistoricalSeries
│   ├── requests.py                # OrderRequest, ModifyOrderRequest
│   ├── events.py                  # DomainEvent, EventType
│   ├── enums.py                   # Exchange, AssetClass, Side, OrderType
│   ├── capabilities.py            # ProviderCapabilities
│   ├── extensions.py              # Extension Protocols
│   └── exceptions.py              # Domain exceptions
├── provider/                      # PROVIDER ABSTRACTION — single interface
│   ├── protocol.py                # Provider Protocol — the ONE interface
│   ├── routing.py                 # RoutingStrategy (function, not class)
│   ├── capabilities.py            # Capability profiles per broker
│   └── extensions.py              # ExtensionAccess — typed facade
├── brokers/                       # CONCRETE IMPLEMENTATIONS
│   ├── dhan/
│   │   ├── dhan_provider.py       # Implements Provider
│   │   ├── http_client.py         # Raw HTTP
│   │   ├── mapper.py              # DTO → domain objects
│   │   ├── resolver.py            # Symbol → security_id
│   │   ├── streaming.py           # WebSocket feeds
│   │   ├── auth.py                # Token management
│   │   └── extensions.py          # Dhan-specific extensions
│   ├── upstox/                    # Same structure
│   └── paper/
│       ├── paper_provider.py      # In-memory simulation
│       └── simulator.py
├── infrastructure/                # CROSS-CUTTING (no business logic)
│   ├── http.py                    # Async HTTP client
│   ├── cache.py                   # Cache abstraction
│   ├── event_bus.py               # In-process event bus
│   ├── resilience.py              # @rate_limit, @circuit_breaker
│   ├── logging.py                 # Structured logging
│   ├── metrics.py                 # Metrics
│   ├── health.py                  # Health checks
│   └── streaming.py               # WebSocket transport, orchestrator
├── broker.py                      # Broker — factory + DI entry point
└── risk.py                        # RiskPolicy — strategy, not wrapper
```

### 3.2 What Was Eliminated

The entire `brokers/common/` directory is deleted. Every module in it was a
wrapper or a class that existed solely to forward calls:

| Eliminated | Reason |
|-----------|--------|
| `common/gateway.py` | Wrapper chain |
| `common/intelligent_gateway.py` | Wrapper chain |
| `common/router.py` | Routing → Strategy inside Provider |
| `common/registry.py` | Discovery → Broker factory |
| `common/batch.py` | Mixin with hidden deps → batch on Instrument |
| `common/bootstrap.py` | God function → Broker factory |
| `common/pre_trade_risk.py` | Wrapper decorator → risk in Account |
| `common/historical_coordinator.py` | Duplicates routing → merge in Provider |
| `common/instrument_registry.py` | Instrument lookup is Provider method |
| `common/quota_scheduler.py` | Concurrency → Provider infrastructure |
| `common/policy.py` | Replaced by RoutingStrategy |
| `common/factory.py` | Replaced by Broker factory methods |
| `common/auth/` | Auth moves into each provider |
| `common/idempotency.py` | Internal to provider |
| `common/reconciliation.py` | Provider method |

### 3.3 Dependency Rules (Architecture Test Enforced)

1. `domain/` imports nothing from outside `domain/` except stdlib.
2. `provider/` imports from `domain/` only.
3. `brokers/` imports from `domain/`, `provider/`, `infrastructure/`.
4. `infrastructure/` imports from `domain/` only.
5. `broker.py` imports from everything — composition root.
6. **No circular imports.**
7. **No class named `*Manager`, `*Helper`, `*Util`, `*Wrapper`, `*Facade`.**
8. **No class with >70% forwarding methods.**

---

## Phase 4 — Public SDK API (Revised)

### 4.1 Quick Start — Direct Instrument Access, No Wrappers

```python
from brokers import Broker, Exchange

# 1. Create a Broker (factory + DI entry point)
broker = Broker.dhan(client_id="123", access_token="tok")

# 2. Get an Instrument — it's a rich domain object, not a handle
reliance = broker.instrument("RELIANCE", Exchange.NSE)

# 3. Market data — directly on the instrument
quote = await reliance.quote()
print(f"RELIANCE: {quote.ltp}")

# 4. History — directly on the instrument
bars = await reliance.history(timeframe="5m", bars=100)

# 5. Subscribe — directly on the instrument
sub = await reliance.subscribe_quotes(on_tick=lambda q: print(q.ltp))

# 6. Trade — instrument.buy() delegates to Account (with risk gating)
response = await reliance.buy(quantity=10)

# 7. Cleanup
await sub.cancel()
await reliance.close()
```

**Three layers: User → Instrument → Provider → Broker. No gateway, no
router, no registry, no handle.**

### 4.2 Multi-Broker — Routing Is a Strategy Inside the Provider

```python
broker = Broker.compose(
    primary=Broker.dhan(client_id="123", access_token="tok"),
    secondary=Broker.upstox(access_token="tok2"),
    routing=RoutingStrategy(
        execution="primary",
        market_data=["primary", "secondary"],
        historical=["secondary", "primary"],
    ),
)

reliance = broker.instrument("RELIANCE", Exchange.NSE)
quote = await reliance.quote()  # Routed by strategy inside the provider
```

No `BrokerRouter` class. `RoutingStrategy` is a frozen dataclass with
function references. The composite provider checks it internally.

### 4.3 Option Chain — Each Option Is a Full Instrument

```python
nifty = broker.instrument("NIFTY", Exchange.NFO)
chain = await nifty.option_chain()

atm_call = chain.atm(spot=(await nifty.ltp()))
if atm_call:
    response = await atm_call.buy(quantity=75)  # 75 = NIFTY lot size
```

### 4.4 Account — Direct Access, No Gateway

```python
account = broker.account()
balance = await account.get_balance()
positions = await account.get_positions()
sub = await account.subscribe_orders(on_update=lambda o: print(o.status))
```

### 4.5 Extensions — Typed, Capability-Gated

```python
depth20 = reliance.extensions.depth20  # Returns Depth20Extension | None
if depth20:
    snapshot = await depth20.get()
```

### 4.6 Paper Trading — Same API, Zero Config

```python
broker = Broker.paper()
reliance = broker.instrument("RELIANCE", Exchange.NSE)
quote = await reliance.quote()  # Simulated
```

### 4.7 v1 vs v2 Comparison

| v1 (Wrapper Chain) | v2 (Direct Domain Objects) |
|---------------------|---------------------------|
| `Session.create()` → `session.instrument()` → `handle.quote()` | `Broker.dhan()` → `broker.instrument()` → `reliance.quote()` |
| 3 objects, 2 indirections | 2 objects, 1 indirection |
| `InstrumentHandle` is a wrapper | `Instrument` IS the domain object |
| Risk in `RiskCheckedTradingPort` wrapper | Risk in `Account.place_order()` |
| Routing in `BrokerRouter` class | Routing in `RoutingStrategy` function |

---

## Phase 5 — Internal Architecture (Revised)

### 5.1 Provider — The Single Abstraction

Replaces `MarketDataPort` + `TradingPort` + `StreamingPort` with ONE Protocol.
Every broker implements all three — the split created three protocols always
implemented together, requiring a registry to look up three separate ports.
One Protocol is simpler and correct.

Data-only providers (CSV, Yahoo) raise `NotSupportedError` for execution
methods — a single `raise` is cleaner than a separate protocol.

### 5.2 Routing — Strategy Inside the Provider

`RoutingStrategy` is a frozen dataclass with function fields:
`select_for_quote`, `select_for_history`, `select_for_execution`,
`select_for_streaming`. The `CompositeProvider` calls these functions to
select which sub-provider to delegate to. No separate Router class.

`CompositeProvider` is NOT a wrapper — it adds failover, capability
checking, and multi-source routing. Real responsibility.

### 5.3 Risk — Strategy Inside Account

`RiskPolicy` is injected into `Account`. `place_order()` calls
`risk_policy.check()` before executing. If denied, returns
`OrderResponse.fail()`. No wrapper class.

### 5.4 Authentication — Inside the Provider

Each provider owns its own auth. No `AuthManager` class wrapping providers.

### 5.5 Streaming — Orchestrator Inside the Provider

`StreamOrchestrator` is retained — it has real responsibility (connection
lifecycle, reconnection, health monitoring, fan-out). It's infrastructure,
not a forwarding layer. Owned by the provider.

### 5.6 EventBus — Retained As-Is

Real responsibility: pub/sub dispatch, handler isolation, sequence
numbering. Not a wrapper.

### 5.7 Historical Data — No Separate Coordinator

Multi-source merge is ~20 lines inside `CompositeProvider.get_history()`,
not a 250-line class duplicating routing logic.

---

## Phase 6 — Event Flow (Revised)

### 6.1 Event Ownership — Domain Objects Publish, Not Gateways

| Event | Published By | Why |
|-------|-------------|-----|
| `TICK` / `DEPTH` | Provider | Owns the WebSocket, decodes ticks |
| `ORDER_PLACED` | Account | Owns order placement |
| `ORDER_UPDATED` / `CANCELLED` | Order | Owns its lifecycle |
| `ORDER_REJECTED` | Account | Owns risk gating |
| `TRADE` | Provider | Decodes the fill from order stream |
| `RISK_REJECTED` | Account | Owns risk gating |
| `BROKER_CONNECTED` / `DISCONNECTED` | Provider | Owns connection |

**Key change:** Events published by domain objects that own the
responsibility, not by a separate "engine" layer. No `PortfolioEngine`,
no `RecoveryEngine` — those responsibilities live inside the objects
that own the state.

### 6.2 Order Flow — No Wrapper Layers

```
User: instrument.buy(quantity=100)
    → Instrument.buy() delegates to account.place_order()
    → Account.place_order():
        ├── risk_policy.check() → ALLOW or DENY (Strategy, not wrapper)
        ├── provider.place_order() → DhanProvider → HTTP (direct call)
        ├── Track order in _open_orders (real state management)
        └── Publish ORDER_PLACED event (real responsibility)
```

**Four layers, not seven.** Each has real responsibility.

### 6.3 Recovery — Inside the Provider

`StreamOrchestrator` already handles disconnect → backoff → reconnect →
resubscribe. No `RecoveryEngine` class. The provider owns the orchestrator.

---

## Phase 7 — Broker Provider Framework (Revised)

### 7.1 Adding a New Broker — One File + One Line

1. Create `brokers/mybroker/mybroker_provider.py` — implements Provider
2. Create supporting files (http_client, mapper, resolver, streaming, auth)
3. Add one line to `Broker` factory: `Broker.mybroker = staticmethod(...)`
4. Run contract test suite + certification pipeline

**No changes to any existing file** (except one line in Broker factory).
Open/Closed Principle satisfied.

### 7.2 Broker Factory

```python
class Broker:
    """Factory + DI entry point."""
    @staticmethod
    def dhan(*, client_id: str, access_token: str) -> Broker: ...
    @staticmethod
    def upstox(*, access_token: str) -> Broker: ...
    @staticmethod
    def paper() -> Broker: ...
    @staticmethod
    def compose(*, primary: Broker, secondary: Broker,
                routing: RoutingStrategy) -> Broker: ...

    def instrument(self, symbol: str, exchange: Exchange, **kwargs) -> Instrument: ...
    def account(self) -> Account: ...
```

---

## Phase 8 — Testing Architecture (Revised)

### 8.1 Architecture Tests — Ban Code Smells

```python
class TestNoCodeSmells:
    def test_no_wrapper_only_classes(self):
        """No class with >70% forwarding methods."""

    def test_no_manager_helper_util_classes(self):
        """No class named *Manager, *Helper, *Util, *Wrapper, *Facade."""

    def test_no_anemic_domain_objects(self):
        """Domain classes must have methods, not just data."""

    def test_no_type_ignore_in_domain(self):
        """Domain layer must have zero type: ignore."""

    def test_no_getattr_dispatch(self):
        """No string-based method dispatch via getattr."""

    def test_no_broker_names_in_domain(self):
        """Domain must not reference any specific broker."""

    def test_no_circular_imports(self):
        """No circular imports anywhere."""

    def test_domain_imports_nothing_external(self):
        """domain/ imports only from domain/ and stdlib."""

    def test_max_call_depth(self):
        """No call chain deeper than 3 layers."""
```

### 8.2 Other Test Layers

Contract, integration, performance, recovery, soak, and certification
pipeline are retained from v1 — the testing architecture was correct.

---

## Phase 9 — Implementation Roadmap (Revised)

### Milestone 0: Clean-Slate Domain Model (Weeks 1-3)
- Rich Instrument, OptionChain, Account, Order
- Delete anemic `Instrument`, `InstrumentRef`, `GatewayResult`
- mypy --strict clean, architecture tests pass

### Milestone 1: Provider Abstraction (Weeks 4-5)
- Single `Provider` Protocol, `RoutingStrategy` function
- Delete `common/gateway.py`, `common/intelligent_gateway.py`,
  `common/router.py`, `common/registry.py`, `common/batch.py`
- No classes named *Manager/*Wrapper/*Facade

### Milestone 2: Concrete Providers (Weeks 6-8)
- `DhanProvider`, `UpstoxProvider`, `PaperProvider`, `CompositeProvider`
- Delete `common/adapter.py`, `common/factory.py`, `common/bootstrap.py`,
  `common/pre_trade_risk.py`, `common/historical_coordinator.py`,
  `common/instrument_registry.py`, `common/policy.py`, `common/auth/`
- All providers pass contract suite

### Milestone 3: Broker Factory + Public API (Weeks 9-10)
- `Broker` factory, `RiskPolicy` strategy
- Quick start (5 lines) works
- No backward-compatible aliases (clean break)

### Milestone 4: Event-Driven Integration (Weeks 11-12)
- Account, Order, Provider publish events
- Recovery inside StreamOrchestrator (already exists)
- No separate "engine" classes

### Milestone 5: Testing & Certification (Weeks 13-15)
### Milestone 6: Hardening & Documentation (Weeks 16-17)

---

## Phase 10 — Future Trading Operating System (Revised)

The Trading OS consumes `Instrument`, `Account`, and `Provider` — the same
three abstractions. No architectural changes needed for Scanner, Strategy,
Backtesting, Risk, Portfolio, Automation. New data sources are new Provider
implementations via the plugin system.

---

## Appendix A: Code Smell Elimination Catalog

| # | Smell | Elimination |
|---|-------|-------------|
| 1 | Wrapper chain (6 layers) | Delete all 4 wrapper classes. Routing = Strategy inside Provider. |
| 2 | Anemic Domain Model | Instrument becomes rich with quote(), history(), subscribe(), buy(), sell() |
| 3 | Wrapper-only class (RiskCheckedTradingPort) | Risk gating moves into Account.place_order() as Strategy |
| 4 | Wrapper-only class (v1's InstrumentHandle) | Never created. Instrument IS the domain object. |
| 5 | Wrapper-only class (v1's Session) | Replaced by Broker factory |
| 6 | Hidden dependency + `type: ignore` | Delete BatchFetchMixin. Batch ops on Instrument. |
| 7 | String-based dispatch (`getattr`) | Each operation is a typed method. |
| 8 | `Any` return type | Extensions are typed Protocols. |
| 9 | `hasattr` introspection | Provider declares extensions via capabilities. |
| 10 | Duplicate identity types | One Instrument class. |
| 11 | Unused monad (GatewayResult) | Delete. Use native exceptions + OrderResponse. |
| 12 | Duplicated routing logic | Merge is Strategy inside CompositeProvider. |
| 13 | God function (bootstrap) | Broker factory — ~20 lines. |
| 14 | Primitive obsession (greeks: dict) | Typed Greeks value object. |
| 15 | Feature envy | Risk logic moves to Account which owns the operation. |
| 16 | Temporal coupling | Broker factory creates everything in one call. |
| 17 | Static state (broker names in functions) | Capabilities declared by provider itself. |
| 18 | Leaky abstraction (_PortAsRiskContext) | Risk policy accepts Provider directly. |
| 19 | Long parameter list (12 params) | Broker.dhan(client_id=, access_token=) — 2 params. |
| 20 | Divergent change (5 files for new broker) | One new file + one line in Broker. |

---

## Appendix B: Before/After Comparison

| Metric | Current | v1 (Evolutionary) | v2 (Clean Redesign) |
|--------|---------|-------------------|---------------------|
| Layers user → HTTP | 6 | 4 | 3 |
| Wrapper-only classes | 4 | 2 | 0 |
| Anemic domain objects | 1 | 1 | 0 |
| *Manager/*Helper classes | 3 | 3 | 0 |
| `type: ignore` in logic | 3 | 3 | 0 |
| `getattr` string dispatch | 1 | 1 | 0 |
| `Any` in public API | 2 | 2 | 0 |
| Duplicate identity types | 3 | 3 | 1 |
| Files to change for new broker | 5+ | 5+ | 1 + 1 line |
| Risk gating | Wrapper | Wrapper | Strategy in Account |
| Routing | Router class | Router class | Strategy function in Provider |
| Backward compatibility | N/A | Preserved | Clean break |

---

*End of Architecture Design Document v2*

**Next step:** Begin Milestone 0 — build the rich domain model from scratch.
