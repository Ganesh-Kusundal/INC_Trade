# TradeXV2 Object-Centric Architecture Design

## 1. Executive Summary

This document defines the complete architecture for TradeXV2's **Object-Centric Trading Platform**. The core principle: **Instruments are first-class objects with state and behavior**, not data Transfer Objects passed through gateways.

### Design Philosophy

```
OLD: Gateway → DTO → Service → Adapter → API
NEW: Instrument Object → Self-contained → Delegates to Provider
```

### Key Principles

1. **Instrument-Centric**: Everything revolves around Instrument objects
2. **No Gateway Pattern**: Objects own their behavior, not monolithic facades
3. **Provider Injection**: Instruments receive capabilities via providers
4. **Composition Over Inheritance**: Decorators, not class hierarchies
5. **One Identity**: Single Instrument instance per symbol per runtime
6. **Infrastructure Reuse**: All brokers share common infrastructure

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER CODE / STRATEGIES                            │
│                                                                             │
│   equity = broker.get_equity("RELIANCE")                                    │
│   equity.quote()                                                            │
│   equity.buy(10)                                                            │
│                                                                             │
│   chain = equity.option_chain("2025-01-30")                                 │
│   chain.atm_strike().call.instrument.buy(25)                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BROKER SESSION LAYER                                │
│                                                                             │
│   BrokerSession                                                             │
│   ├── InstrumentRepository (identity, caching, lookup)                      │
│   ├── OrderManager (placement, tracking, lifecycle)                         │
│   ├── MarketDataProvider (quotes, depth, historical)                        │
│   └── StreamingManager (subscriptions, callbacks)                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INSTRUMENT OBJECT LAYER                             │
│                                                                             │
│   Instrument (Base)                                                         │
│   ├── Equity                                                                │
│   ├── Future                                                                │
│   ├── Option                                                                │
│   └── Index                                                                 │
│                                                                             │
│   InstrumentOptionChain (Composition of Instruments)                        │
│   SyntheticFuture (Derived from Options)                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DECORATOR LAYER                                     │
│                                                                             │
│   Depth20Decorator (Dhan)    Depth30Decorator (Upstox)                      │
│   Depth200Decorator (Dhan)   CachedDecorator                               │
│   LoggedDecorator            MetricsDecorator                               │
│                                                                             │
│   inst = with_depth(with_cache(equity), levels=200)                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PORTS LAYER (Interfaces)                            │
│                                                                             │
│   MarketDataPort     OrderExecutionPort     StreamingPort                   │
│   HistoricalPort     InstrumentPort         PortfolioPort                   │
│   OptionsPort        AuthPort               CachePort                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BROKER ADAPTERS                                     │
│                                                                             │
│   DhanAdapter          UpstoxAdapter          PaperAdapter                   │
│   ├── DhanMarketData   ├── UpstoxMarketData   └── PaperMarketData           │
│   ├── DhanOrders       ├── UpstoxOrders                               │
│   ├── DhanStreaming    ├── UpstoxStreaming                               │
│   └── DhanExtensions   └── UpstoxExtensions                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INFRASTRUCTURE LAYER                                │
│                                                                             │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│   │   Auth      │ │   Token     │ │   Session   │ │   REST      │          │
│   │   Manager   │ │   Manager   │ │   Manager   │ │   Client    │          │
│   └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘          │
│                                                                             │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│   │   WebSocket │ │ Connection  │ │ Subscription│ │  Scheduler  │          │
│   │   Client    │ │   Manager   │ │   Manager   │ │             │          │
│   └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘          │
│                                                                             │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│   │   Retry     │ │  Circuit    │ │   Rate      │ │  Heartbeat  │          │
│   │   Engine    │ │  Breaker    │ │   Limiter   │ │  Manager    │          │
│   └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘          │
│                                                                             │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│   │  Reconnect  │ │   Config    │ │  Secrets    │ │  Metrics    │          │
│   │  Manager    │ │             │ │             │ │             │          │
│   └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘          │
│                                                                             │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│   │  Tracing    │ │  Logging    │ │   Health    │ │   Caching   │          │
│   │             │ │             │ │  Monitoring │ │             │          │
│   └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘          │
│                                                                             │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                          │
│   │     DI      │ │  Thread     │ │  Event      │                          │
│   │  Container  │ │   Pools     │ │   Bus       │                          │
│   └─────────────┘ └─────────────┘ └─────────────┘                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Class Diagrams

### 3.1 Instrument Hierarchy

```
                            ┌─────────────────────┐
                            │      Instrument      │
                            │  (Frozen Dataclass)  │
                            ├─────────────────────┤
                            │ - symbol: str        │
                            │ - exchange: str      │
                            │ - segment: str       │
                            │ - name: str          │
                            │ - lot_size: int      │
                            │ - tick_size: Decimal │
                            │ - isin: str          │
                            │ - expiry: datetime?  │
                            │ - strike: Decimal?   │
                            │ - option_type: str?  │
                            ├─────────────────────┤
                            │ + quote() → Quote    │
                            │ + depth(n) → Depth   │
                            │ + subscribe(cb)      │
                            │ + buy(qty) → Order   │
                            │ + sell(qty) → Order  │
                            │ + is_equity()        │
                            │ + is_future()        │
                            │ + is_option()        │
                            └──────────┬──────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            │                          │                          │
            ▼                          ▼                          ▼
┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│      Equity       │    │      Future       │    │      Option       │
├───────────────────┤    ├───────────────────┤    ├───────────────────┤
│ + dividend_yield  │    │ + expiry: datetime│    │ + strike: Decimal │
│ + pe_ratio        │    │ + lot_multiplier  │    │ + option_type: str│
│ + sector          │    │ + underlying      │    │ + greeks()        │
│ + market_cap      │    │ + basis()         │    │ + intrinsic_value │
└───────────────────┘    └───────────────────┘    └───────────────────┘
                                       │                          │
                                       │                          │
                                       ▼                          ▼
                            ┌───────────────────┐    ┌───────────────────┐
                            │      Index        │    │ InstrumentOption  │
                            ├───────────────────┤    │     Chain         │
                            │ + constituents    │    ├───────────────────┤
                            │ + weight()        │    │ + strikes: tuple  │
                            │ + sector_breakdown│    │ + max_pain        │
                            └───────────────────┘    │ + pcr             │
                                                     │ + atm_strike()   │
                                                     │ + subscribe_all()│
                                                     └───────────────────┘
```

### 3.2 Instrument Option Chain Composition

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     InstrumentOptionChain                               │
├─────────────────────────────────────────────────────────────────────────┤
│ - underlying: Instrument                                               │
│ - expiry: str                                                          │
│ - spot: Decimal                                                        │
│ - strikes: tuple[InstrumentOptionStrike, ...]                          │
│ - _context: MarketDataContext                                          │
├─────────────────────────────────────────────────────────────────────────┤
│ + max_pain_strike: Decimal                                             │
│ + pcr: Decimal                                                         │
│ + atm_strike() → InstrumentOptionStrike                                │
│ + subscribe_all(callback) → int                                        │
│ + synthetic_future(qty) → SyntheticFuture                              │
│ + refresh() → InstrumentOptionChain                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                │ contains
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     InstrumentOptionStrike                              │
├─────────────────────────────────────────────────────────────────────────┤
│ - strike: Decimal                                                      │
│ - call: InstrumentOptionLeg                                            │
│ - put: InstrumentOptionLeg                                             │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
┌─────────────────────────────┐ ┌─────────────────────────────┐
│   InstrumentOptionLeg (Call)│ │   InstrumentOptionLeg (Put) │
├─────────────────────────────┤ ├─────────────────────────────┤
│ - instrument: Instrument    │ │ - instrument: Instrument    │
│ - ltp: Decimal              │ │ - ltp: Decimal              │
│ - oi: int                   │ │ - oi: int                   │
│ - volume: int               │ │ - volume: int               │
│ - iv: Decimal               │ │ - iv: Decimal               │
│ - delta: Decimal            │ │ - delta: Decimal            │
├─────────────────────────────┤ ├─────────────────────────────┤
│ + greeks() → dict           │ │ + greeks() → dict           │
│ + buy(qty) → Order          │ │ + buy(qty) → Order          │
│ + sell(qty) → Order         │ │ + sell(qty) → Order         │
└─────────────────────────────┘ └─────────────────────────────┘
```

### 3.3 Decorator Pattern

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     InstrumentDecorator (Base)                          │
├─────────────────────────────────────────────────────────────────────────┤
│ - _wrapped: Instrument                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│ + __getattr__(name) → Any  (delegates to wrapped)                      │
└─────────────────────────────────────────────────────────────────────────┘
                                ▲
            ┌───────────────────┼───────────────────┐
            │                   │                   │
            ▼                   ▼                   ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  DepthDecorator   │ │ CachedDecorator   │ │  LoggedDecorator  │
├───────────────────┤ ├───────────────────┤ ├───────────────────┤
│ - _depth_provider │ │ - _cache: Cache   │ │ - _logger: Logger │
├───────────────────┤ ├───────────────────┤ ├───────────────────┤
│ + depth(levels)   │ │ + quote() [cached]│ │ + quote() [logged]│
└────────┬──────────┘ └───────────────────┘ └───────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│Depth20 │ │Depth30 │
│Decorator│ │Decorator│
├────────┤ ├────────┤
│+depth_20│ │+depth_30│
└────────┘ └────────┘
    │
    ▼
┌────────┐
│Depth200│
│Decorator│
├────────┤
│+depth_200│
└────────┘
```

### 3.4 Instrument Repository (Singleton Pattern)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     InstrumentRepository                                │
├─────────────────────────────────────────────────────────────────────────┤
│ - _lock: RLock                                                         │
│ - _instruments: dict[str, Instrument]                                   │
│ - _market_data_cache: dict[str, QuoteState]                            │
│ - _depth_cache: dict[str, DepthState]                                  │
│ - _subscriptions: dict[str, SubscriptionHandle]                        │
│ - _lazy_loaders: dict[str, Callable]                                   │
├─────────────────────────────────────────────────────────────────────────┤
│ + get(key: str) → Instrument?                                          │
│ + get_equity(symbol: str) → Equity                                     │
│ + get_future(symbol: str, expiry: datetime) → Future                   │
│ + get_option(symbol: str, expiry: datetime, strike: Decimal, type) → Option │
│ + get_or_create(key: str, factory: Callable) → Instrument              │
│ + search(query: str) → list[Instrument]                                │
│ + register(instrument: Instrument) → None                              │
│ + get_quote_state(key: str) → QuoteState                               │
│ + get_depth_state(key: str) → DepthState                               │
│ + get_subscription(key: str) → SubscriptionHandle?                     │
│ + set_subscription(key: str, handle: SubscriptionHandle) → None        │
│ + clear() → None                                                       │
│ + count() → int                                                        │
│ + keys() → list[str]                                                   │
└─────────────────────────────────────────────────────────────────────────┘

Guarantees:
- One Instrument per composite key (identity)
- Thread-safe operations (concurrency)
- Lazy loading with cache (performance)
- Single QuoteState per instrument (state)
- Single Subscription per instrument (streaming)
```

---

## 4. Infrastructure Layer Design

### 4.1 Infrastructure Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     INFRASTRUCTURE LAYER                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    SECURITY & AUTH                              │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  AuthenticationManager  │  TokenManager    │  SecretsManager   │   │
│  │  - login()              │  - get_token()   │  - get_secret()   │   │
│  │  - logout()             │  - refresh()     │  - store_secret() │   │
│  │  - validate()           │  - revoke()      │  - rotate()       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    CONNECTION & SESSION                         │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  SessionManager        │  ConnectionManager │  HeartbeatManager│   │
│  │  - create()            │  - connect()       │  - start()       │   │
│  │  - destroy()           │  - disconnect()    │  - stop()        │   │
│  │  - get_session()       │  - is_connected()  │  - on_heartbeat()│   │
│  │  - renew()             │  - reconnect()     │  - on_timeout()  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    NETWORKING                                   │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  RestClient            │  WebSocketClient   │  ReconnectManager│   │
│  │  - get()               │  - connect()       │  - on_disconnect │   │
│  │  - post()              │  - send()          │  - should_reconnect│  │
│  │  - put()               │  - receive()       │  - get_delay()   │   │
│  │  - delete()            │  - close()         │  - reset()       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    RESILIENCE                                   │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  RetryEngine           │  CircuitBreaker    │  RateLimiter     │   │
│  │  - execute(fn)         │  - call(fn)        │  - acquire()     │   │
│  │  - with_retry()        │  - record_success  │  - wait()        │   │
│  │  - get_backoff()       │  - record_failure  │  - throttle()    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    STREAMING                                    │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  SubscriptionManager   │  EventBus          │  Scheduler       │   │
│  │  - subscribe()         │  - publish()       │  - schedule()    │   │
│  │  - unsubscribe()       │  - subscribe()     │  - cancel()      │   │
│  │  - ref_count()         │  - unsubscribe()   │  - run_interval()│   │
│  │  - deduplicate()       │  - emit()          │  - run_once()    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    OBSERVABILITY                                │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  MetricsCollector      │  TracingManager    │  HealthMonitor   │   │
│  │  - counter()           │  - start_span()    │  - register()    │   │
│  │  - gauge()             │  - end_span()      │  - check()       │   │
│  │  - histogram()         │  - trace()         │  - status()      │   │
│  │  - timer()             │  - inject()        │  - subscribe()   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    SUPPORT                                      │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  ConfigurationManager  │  MemoryCache       │  DIContainer     │   │
│  │  - get()               │  - get()           │  - register()    │   │
│  │  - set()               │  - set()           │  - resolve()     │   │
│  │  - validate()          │  - invalidate()    │  - inject()      │   │
│  │  - reload()            │  - stats()         │  - singleton()   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    CONCURRENCY                                  │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  ThreadPoolManager     │  LoggingManager                         │   │
│  │  - submit()            │  - get_logger()                         │   │
│  │  - map()               │  - configure()                          │   │
│  │  - shutdown()          │  - set_level()                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Infrastructure Interface Definitions

```python
# ── Authentication ───────────────────────────────────────────────────────

class AuthenticationManager(Protocol):
    """Manages broker authentication lifecycle."""

    async def login(self, credentials: dict[str, Any]) -> AuthResult: ...
    async def logout(self) -> None: ...
    async def validate_token(self, token: str) -> bool: ...
    def get_auth_mode(self) -> AuthMode: ...
    def is_authenticated(self) -> bool: ...


# ── Token Management ─────────────────────────────────────────────────────

class TokenManager(Protocol):
    """Manages token lifecycle with automatic refresh."""

    def get_token(self) -> str: ...
    async def refresh_token(self) -> str: ...
    def revoke_token(self) -> None: ...
    def get_expiry(self) -> datetime | None: ...
    def is_expired(self) -> bool: ...
    def time_until_expiry(self) -> timedelta: ...
    def on_token_refresh(self, callback: Callable[[str], None]) -> None: ...


# ── Session Management ───────────────────────────────────────────────────

class SessionManager(Protocol):
    """Manages broker sessions with lifecycle."""

    def create_session(self, broker_id: str, config: SessionConfig) -> Session: ...
    def get_session(self, broker_id: str) -> Session | None: ...
    def destroy_session(self, broker_id: str) -> None: ...
    def renew_session(self, broker_id: str) -> Session: ...
    def is_active(self, broker_id: str) -> bool: ...
    def get_all_sessions(self) -> dict[str, Session]: ...


# ── REST Client ──────────────────────────────────────────────────────────

class RestClient(Protocol):
    """HTTP client with resilience features."""

    async def get(self, url: str, headers: dict = None) -> Response: ...
    async def post(self, url: str, data: Any = None, headers: dict = None) -> Response: ...
    async def put(self, url: str, data: Any = None, headers: dict = None) -> Response: ...
    async def delete(self, url: str, headers: dict = None) -> Response: ...
    def set_timeout(self, timeout: float) -> None: ...
    def set_headers(self, headers: dict[str, str]) -> None: ...


# ── WebSocket Client ─────────────────────────────────────────────────────

class WebSocketClient(Protocol):
    """WebSocket client with auto-reconnection."""

    async def connect(self, url: str, headers: dict = None) -> None: ...
    async def send(self, data: str | bytes) -> None: ...
    async def receive(self) -> str | bytes: ...
    async def close(self) -> None: ...
    def is_connected(self) -> bool: ...
    def on_message(self, callback: Callable[[str], None]) -> None: ...
    def on_error(self, callback: Callable[[Exception], None]) -> None: ...
    def on_close(self, callback: Callable[[], None]) -> None: ...


# ── Connection Manager ───────────────────────────────────────────────────

class ConnectionManager(Protocol):
    """Manages multiple connections with health monitoring."""

    def connect(self, name: str, client: RestClient | WebSocketClient) -> Connection: ...
    def disconnect(self, name: str) -> None: ...
    def get_connection(self, name: str) -> Connection | None: ...
    def is_connected(self, name: str) -> bool: ...
    def reconnect(self, name: str) -> Connection: ...
    def get_all_connections(self) -> dict[str, Connection]: ...


# ── Subscription Manager ─────────────────────────────────────────────────

class SubscriptionManager(Protocol):
    """Manages streaming subscriptions with reference counting."""

    def subscribe(self, key: str, callback: Callable) -> SubscriptionHandle: ...
    def unsubscribe(self, key: str) -> None: ...
    def ref_count(self, key: str) -> int: ...
    def is_subscribed(self, key: str) -> bool: ...
    def get_all_subscriptions(self) -> dict[str, SubscriptionHandle]: ...
    def clear(self) -> None: ...


# ── Scheduler ────────────────────────────────────────────────────────────

class Scheduler(Protocol):
    """Task scheduler for background operations."""

    def schedule(self, task: Callable, interval: timedelta) -> ScheduledTask: ...
    def schedule_once(self, task: Callable, delay: timedelta) -> ScheduledTask: ...
    def cancel(self, task_id: str) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def is_running(self) -> bool: ...


# ── Retry Engine ─────────────────────────────────────────────────────────

class RetryEngine(Protocol):
    """Retry logic with exponential backoff."""

    def execute(
        self,
        fn: Callable,
        max_retries: int = 3,
        backoff: float = 1.0,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> Any: ...
    def get_backoff(self, attempt: int) -> float: ...
    def reset(self) -> None: ...


# ── Circuit Breaker ──────────────────────────────────────────────────────

class CircuitBreaker(Protocol):
    """Circuit breaker for fault tolerance."""

    def call(self, fn: Callable) -> Any: ...
    def record_success(self) -> None: ...
    def record_failure(self) -> None: ...
    def is_open(self) -> bool: ...
    def is_half_open(self) -> bool: ...
    def reset(self) -> None: ...
    def get_state(self) -> CircuitState: ...
    def get_metrics(self) -> CircuitMetrics: ...


# ── Rate Limiter ─────────────────────────────────────────────────────────

class RateLimiter(Protocol):
    """Token bucket rate limiter."""

    def acquire(self) -> bool: ...
    def wait(self) -> Awaitable[None]: ...
    def throttle(self, fn: Callable) -> Callable: ...
    def get_remaining(self) -> int: ...
    def get_reset_time(self) -> float: ...


# ── Heartbeat Manager ────────────────────────────────────────────────────

class HeartbeatManager(Protocol):
    """Connection health monitoring via heartbeats."""

    def start(self, name: str, interval: timedelta) -> None: ...
    def stop(self, name: str) -> None: ...
    def on_heartbeat(self, callback: Callable[[str], None]) -> None: ...
    def on_timeout(self, callback: Callable[[str], None]) -> None: ...
    def is_alive(self, name: str) -> bool: ...
    def get_latency(self, name: str) -> float: ...


# ── Reconnect Manager ────────────────────────────────────────────────────

class ReconnectManager(Protocol):
    """Automatic reconnection with backoff."""

    def on_disconnect(self, name: str) -> None: ...
    def should_reconnect(self, name: str) -> bool: ...
    def get_delay(self, name: str) -> float: ...
    def reset(self, name: str) -> None: ...
    def get_attempt(self, name: str) -> int: ...
    def set_max_attempts(self, name: str, max_attempts: int) -> None: ...


# ── Configuration ────────────────────────────────────────────────────────

class ConfigurationManager(Protocol):
    """Configuration management with hot-reload."""

    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def validate(self) -> bool: ...
    def reload(self) -> None: ...
    def get_section(self, section: str) -> dict[str, Any]: ...
    def watch(self, key: str, callback: Callable[[Any], None]) -> None: ...


# ── Secrets Manager ──────────────────────────────────────────────────────

class SecretsManager(Protocol):
    """Secure secrets storage."""

    def get_secret(self, name: str) -> str: ...
    def store_secret(self, name: str, value: str) -> None: ...
    def rotate_secret(self, name: str) -> str: ...
    def delete_secret(self, name: str) -> None: ...
    def list_secrets(self) -> list[str]: ...


# ── Metrics Collector ────────────────────────────────────────────────────

class MetricsCollector(Protocol):
    """Metrics collection for monitoring."""

    def counter(self, name: str, value: float = 1.0, tags: dict = None) -> None: ...
    def gauge(self, name: str, value: float, tags: dict = None) -> None: ...
    def histogram(self, name: str, value: float, tags: dict = None) -> None: ...
    def timer(self, name: str) -> TimerContext: ...
    def get_counter(self, name: str) -> float: ...
    def get_gauge(self, name: str) -> float: ...


# ── Tracing Manager ──────────────────────────────────────────────────────

class TracingManager(Protocol):
    """Distributed tracing for debugging."""

    def start_span(self, name: str) -> Span: ...
    def end_span(self, span: Span) -> None: ...
    def trace(self, name: str) -> ContextManager[Span]: ...
    def inject(self, headers: dict) -> dict: ...
    def extract(self, headers: dict) -> SpanContext | None: ...
    def get_trace_id(self) -> str: ...


# ── Logging Manager ──────────────────────────────────────────────────────

class LoggingManager(Protocol):
    """Centralized logging configuration."""

    def get_logger(self, name: str) -> Logger: ...
    def configure(self, config: LoggingConfig) -> None: ...
    def set_level(self, level: str) -> None: ...
    def add_handler(self, handler: Handler) -> None: ...
    def remove_handler(self, handler: Handler) -> None: ...


# ── Health Monitor ───────────────────────────────────────────────────────

class HealthMonitor(Protocol):
    """System health monitoring."""

    def register(self, name: str, check: Callable[[], HealthStatus]) -> None: ...
    def check(self, name: str) -> HealthStatus: ...
    def status(self) -> dict[str, HealthStatus]: ...
    def subscribe(self, callback: Callable[[str, HealthStatus], None]) -> None: ...
    def is_healthy(self) -> bool: ...


# ── Cache ────────────────────────────────────────────────────────────────

class Cache(Protocol):
    """Generic cache with TTL and LRU eviction."""

    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: float = None) -> None: ...
    def invalidate(self, key: str) -> None: ...
    def clear(self) -> None: ...
    def stats(self) -> CacheStats: ...
    def has(self, key: str) -> bool: ...
    def size(self) -> int: ...


# ── Dependency Injection ─────────────────────────────────────────────────

class DIContainer(Protocol):
    """Lightweight dependency injection container."""

    def register(self, interface: type, implementation: Any, singleton: bool = False) -> None: ...
    def resolve(self, interface: type) -> Any: ...
    def inject(self, target: Any) -> Any: ...
    def singleton(self, interface: type, factory: Callable) -> None: ...
    def has(self, interface: type) -> bool: ...


# ── Thread Pool ──────────────────────────────────────────────────────────

class ThreadPoolManager(Protocol):
    """Thread pool management for async operations."""

    def submit(self, fn: Callable, *args, **kwargs) -> Future: ...
    def map(self, fn: Callable, items: list) -> list: ...
    def shutdown(self, wait: bool = True) -> None: ...
    def get_stats(self) -> ThreadPoolStats: ...
```

---

## 5. Flow Diagrams

### 5.1 Instrument Lookup Flow

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  User Code  │────▶│ BrokerSession   │────▶│InstrumentRepository│
│             │     │                 │     │                  │
│ get_equity  │     │ 1. Check cache  │     │ 2. Get or create │
│ ("RELIANCE")│     │ 3. Return inst  │     │                  │
└─────────────┘     └─────────────────┘     └──────────────────┘
                                               │
                                               ▼
                                        ┌──────────────────┐
                                        │   Instrument     │
                                        │   (Equity)       │
                                        │                  │
                                        │ - _provider: set │
                                        │ - _context: set  │
                                        └──────────────────┘
```

### 5.2 Order Placement Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  User Code  │────▶│ Instrument  │────▶│ OrderManager│────▶│  Adapter    │
│             │     │             │     │             │     │             │
│ inst.buy(10)│     │ 1. Validate │     │ 2. Execute  │     │ 3. Place    │
│             │     │    quantity │     │    order    │     │    via API  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │   Order     │
                                        │  Response   │
                                        │             │
                                        │ - order_id  │
                                        │ - status    │
                                        └─────────────┘
```

### 5.3 Streaming Subscription Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  User Code  │────▶│ Instrument  │────▶│Subscription │────▶│  Streaming  │
│             │     │             │     │  Manager    │     │    Port     │
│ inst.       │     │ 1. Resolve  │     │ 2. Dedupe   │     │ 3. Connect  │
│ subscribe() │     │    provider │     │    & RefCount│    │    WS       │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │  QuoteState │
                                        │  (updated)  │
                                        │             │
                                        │ - ltp       │
                                        │ - bid/ask   │
                                        │ - volume    │
                                        └─────────────┘
```

### 5.4 Option Chain Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  User Code  │────▶│ Instrument  │────▶│MarketDataContext────▶│  Options   │
│             │     │             │     │             │     │    Port     │
│ inst.       │     │ 1. Delegate │     │ 2. Resolve  │     │ 3. Fetch    │
│ option_chain│     │    to ctx   │     │    chain    │     │    chain    │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────────┐
                                        │InstrumentOption │
                                        │     Chain       │
                                        │                 │
                                        │ - strikes[]     │
                                        │ - call.instrument│
                                        │ - put.instrument │
                                        └─────────────────┘
```

### 5.5 Decorator Application Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  User Code  │────▶│   with_     │────▶│  Depth200   │────▶│   Base      │
│             │     │   depth()   │     │ Decorator   │     │ Instrument  │
│ inst =      │     │             │     │             │     │             │
│ with_depth()│     │ 1. Select   │     │ 2. Wrap     │     │ 3. Delegate │
│             │     │    level    │     │    instrument│    │    methods  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │ depth(200)  │
                                        │ → provider  │
                                        │   .depth()  │
                                        └─────────────┘
```

---

## 6. Instrument Repository Design

### 6.1 Repository Interface

```python
class InstrumentRepository:
    """Thread-safe repository guaranteeing one Instrument per symbol.

    Guarantees:
    - One Instrument per composite key (identity)
    - Thread-safe operations (concurrency)
    - Lazy loading with cache (performance)
    - Single QuoteState per instrument (state)
    - Single Subscription per instrument (streaming)
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._instruments: dict[str, Instrument] = {}
        self._quote_states: dict[str, QuoteState] = {}
        self._depth_states: dict[str, DepthState] = {}
        self._subscriptions: dict[str, SubscriptionHandle] = {}
        self._lazy_loaders: dict[str, Callable[[], Instrument]] = {}

    # ── Identity & Lookup ────────────────────────────────────────────

    def get(self, key: str) -> Instrument | None:
        """Look up instrument by composite key (e.g., 'NSE:RELIANCE').

        Lock-free read: dict reference read is atomic in CPython.
        """
        return self._instruments.get(key)

    def get_equity(self, symbol: str, exchange: str = "NSE") -> Equity:
        """Get or create an Equity instrument.

        Guarantees:
        - Same object returned for same symbol+exchange
        - Thread-safe creation
        - Lazy provider injection
        """
        key = f"{exchange}:{symbol}"
        with self._lock:
            if key in self._instruments:
                inst = self._instruments[key]
                if not isinstance(inst, Equity):
                    raise TypeError(f"Expected Equity, got {type(inst).__name__}")
                return inst

            # Create new equity
            equity = Equity(
                symbol=symbol,
                exchange=exchange,
                lot_size=1,
                tick_size=Decimal("0.05"),
            )
            self._instruments[key] = equity
            self._quote_states[key] = QuoteState(symbol=symbol, exchange=exchange)
            return equity

    def get_future(
        self, symbol: str, expiry: datetime, exchange: str = "NFO"
    ) -> Future:
        """Get or create a Future instrument."""
        key = f"{exchange}:{symbol}:{expiry.date()}"
        with self._lock:
            if key in self._instruments:
                return self._instruments[key]

            future = Future(
                symbol=symbol,
                exchange=exchange,
                expiry=expiry,
                lot_size=1,
                tick_size=Decimal("0.05"),
            )
            self._instruments[key] = future
            self._quote_states[key] = QuoteState(symbol=symbol, exchange=exchange)
            return future

    def get_option(
        self,
        symbol: str,
        expiry: datetime,
        strike: Decimal,
        option_type: str,
        exchange: str = "NFO",
    ) -> Option:
        """Get or create an Option instrument."""
        key = f"{exchange}:{symbol}:{expiry.date()}:{strike}:{option_type}"
        with self._lock:
            if key in self._instruments:
                return self._instruments[key]

            option = Option(
                symbol=symbol,
                exchange=exchange,
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                lot_size=1,
                tick_size=Decimal("0.05"),
            )
            self._instruments[key] = option
            self._quote_states[key] = QuoteState(symbol=symbol, exchange=exchange)
            return option

    # ── Caching & State ──────────────────────────────────────────────

    def get_quote_state(self, key: str) -> QuoteState | None:
        """Get mutable quote state for an instrument."""
        return self._quote_states.get(key)

    def get_depth_state(self, key: str) -> DepthState | None:
        """Get mutable depth state for an instrument."""
        return self._depth_states.get(key)

    def set_quote_state(self, key: str, state: QuoteState) -> None:
        """Set/update quote state for an instrument."""
        with self._lock:
            self._quote_states[key] = state

    def set_depth_state(self, key: str, state: DepthState) -> None:
        """Set/update depth state for an instrument."""
        with self._lock:
            self._depth_states[key] = state

    # ── Subscription Management ──────────────────────────────────────

    def get_subscription(self, key: str) -> SubscriptionHandle | None:
        """Get active subscription for an instrument."""
        return self._subscriptions.get(key)

    def set_subscription(self, key: str, handle: SubscriptionHandle) -> None:
        """Register a subscription for an instrument."""
        with self._lock:
            # Unsubscribe old if exists
            old = self._subscriptions.get(key)
            if old is not None:
                try:
                    old.unsubscribe()
                except Exception:
                    pass
            self._subscriptions[key] = handle

    def remove_subscription(self, key: str) -> None:
        """Remove and unsubscribe an instrument."""
        with self._lock:
            handle = self._subscriptions.pop(key, None)
            if handle is not None:
                try:
                    handle.unsubscribe()
                except Exception:
                    pass

    # ── Search ───────────────────────────────────────────────────────

    def search(self, query: str) -> list[Instrument]:
        """Search instruments by symbol or name."""
        query_upper = query.upper()
        results = []
        for inst in self._instruments.values():
            if (
                query_upper in inst.symbol.upper()
                or query_upper in inst.name.upper()
            ):
                results.append(inst)
        return results

    def get_all(self) -> dict[str, Instrument]:
        """Return snapshot of all instruments."""
        with self._lock:
            return dict(self._instruments)

    def keys(self) -> list[str]:
        """Return all composite keys."""
        with self._lock:
            return list(self._instruments.keys())

    def count(self) -> int:
        """Return number of registered instruments."""
        return len(self._instruments)

    def clear(self) -> None:
        """Clear all instruments (for testing)."""
        with self._lock:
            # Unsubscribe all
            for handle in self._subscriptions.values():
                try:
                    handle.unsubscribe()
                except Exception:
                    pass
            self._instruments.clear()
            self._quote_states.clear()
            self._depth_states.clear()
            self._subscriptions.clear()
            self._lazy_loaders.clear()
```

### 6.2 Repository Guarantees

| Guarantee | Implementation | Benefit |
|-----------|----------------|---------|
| **One Instrument** | `get_or_create` with lock | Identity preservation |
| **One Runtime State** | `_quote_states` dict | Shared mutable state |
| **One Subscription** | `_subscriptions` dict | Deduplication |
| **One Object Instance** | Key-based lookup | Memory efficiency |
| **Thread Safety** | `RLock` on mutations | Concurrency safety |
| **Lazy Loading** | Factory functions | Performance |
| **Search** | Linear scan | Discovery |

### 6.3 Usage Examples

```python
# Initialize repository
repo = InstrumentRepository()

# Get equity - returns same object every time
equity1 = repo.get_equity("RELIANCE")
equity2 = repo.get_equity("RELIANCE")
assert equity1 is equity2  # Same object identity

# Get future
from datetime import datetime
future = repo.get_future("NIFTY", datetime(2025, 1, 30))

# Get option
option = repo.get_option(
    symbol="NIFTY",
    expiry=datetime(2025, 1, 30),
    strike=Decimal("25000"),
    option_type="CE",
)

# Search
results = repo.search("NIFTY")

# Get all
all_instruments = repo.get_all()

# Clear (for testing)
repo.clear()
```

---

## 7. Infrastructure Implementation

### 7.1 Core Infrastructure Classes

```python
# ── Authentication Manager ───────────────────────────────────────────────

class AuthenticationManagerImpl:
    """Manages broker authentication lifecycle."""

    def __init__(
        self,
        token_manager: TokenManager,
        config: ConfigurationManager,
    ):
        self._token_manager = token_manager
        self._config = config
        self._authenticated = False
        self._auth_mode: AuthMode = AuthMode.STATIC

    async def login(self, credentials: dict[str, Any]) -> AuthResult:
        """Authenticate with broker."""
        self._auth_mode = self._config.get("auth_mode", AuthMode.STATIC)

        if self._auth_mode == AuthMode.TOTP:
            return await self._totp_login(credentials)
        elif self._auth_mode == AuthMode.OAUTH:
            return await self._oauth_login(credentials)
        else:
            return await self._static_login(credentials)

    async def logout(self) -> None:
        """Logout and revoke token."""
        self._token_manager.revoke_token()
        self._authenticated = False

    async def validate_token(self, token: str) -> bool:
        """Validate if token is still valid."""
        return not self._token_manager.is_expired()

    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return self._authenticated and not self._token_manager.is_expired()


# ── Token Manager ────────────────────────────────────────────────────────

class TokenManagerImpl:
    """Manages token lifecycle with automatic refresh."""

    def __init__(
        self,
        config: ConfigurationManager,
        scheduler: Scheduler,
        cache: Cache,
    ):
        self._config = config
        self._scheduler = scheduler
        self._cache = cache
        self._token: str = ""
        self._expiry: datetime | None = None
        self._refresh_callbacks: list[Callable[[str], None]] = []

    def get_token(self) -> str:
        """Get current token, refreshing if needed."""
        if self.is_expired():
            self.refresh_token()
        return self._token

    def refresh_token(self) -> str:
        """Refresh the token."""
        # Implementation depends on broker
        raise NotImplementedError

    def is_expired(self) -> bool:
        """Check if token is expired."""
        if self._expiry is None:
            return True
        return datetime.now(UTC) >= self._expiry

    def on_token_refresh(self, callback: Callable[[str], None]) -> None:
        """Register callback for token refresh events."""
        self._refresh_callbacks.append(callback)


# ── Session Manager ──────────────────────────────────────────────────────

class SessionManagerImpl:
    """Manages broker sessions with lifecycle."""

    def __init__(self, di_container: DIContainer):
        self._container = di_container
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def create_session(self, broker_id: str, config: SessionConfig) -> Session:
        """Create a new broker session."""
        with self._lock:
            if broker_id in self._sessions:
                return self._sessions[broker_id]

            session = Session(
                broker_id=broker_id,
                config=config,
                rest_client=self._container.resolve(RestClient),
                ws_client=self._container.resolve(WebSocketClient),
                auth_manager=self._container.resolve(AuthenticationManager),
                token_manager=self._container.resolve(TokenManager),
            )
            self._sessions[broker_id] = session
            return session

    def get_session(self, broker_id: str) -> Session | None:
        """Get existing session."""
        return self._sessions.get(broker_id)

    def destroy_session(self, broker_id: str) -> None:
        """Destroy a session."""
        with self._lock:
            session = self._sessions.pop(broker_id, None)
            if session:
                session.close()


# ── REST Client ──────────────────────────────────────────────────────────

class RestClientImpl:
    """HTTP client with resilience features."""

    def __init__(
        self,
        config: ConfigurationManager,
        circuit_breaker: CircuitBreaker,
        retry_engine: RetryEngine,
        rate_limiter: RateLimiter,
        metrics: MetricsCollector,
    ):
        self._config = config
        self._circuit_breaker = circuit_breaker
        self._retry_engine = retry_engine
        self._rate_limiter = rate_limiter
        self._metrics = metrics
        self._session: aiohttp.ClientSession | None = None

    async def get(self, url: str, headers: dict = None) -> Response:
        """Execute GET request with resilience."""
        return await self._execute("GET", url, headers=headers)

    async def post(self, url: str, data: Any = None, headers: dict = None) -> Response:
        """Execute POST request with resilience."""
        return await self._execute("POST", url, data=data, headers=headers)

    async def _execute(self, method: str, url: str, **kwargs) -> Response:
        """Execute request with circuit breaker, retry, and rate limiting."""
        await self._rate_limiter.wait()

        def _request():
            return self._circuit_breaker.call(
                lambda: self._raw_request(method, url, **kwargs)
            )

        return await self._retry_engine.execute(_request)


# ── WebSocket Client ─────────────────────────────────────────────────────

class WebSocketClientImpl:
    """WebSocket client with auto-reconnection."""

    def __init__(
        self,
        reconnect_manager: ReconnectManager,
        heartbeat_manager: HeartbeatManager,
        metrics: MetricsCollector,
    ):
        self._reconnect_manager = reconnect_manager
        self._heartbeat_manager = heartbeat_manager
        self._metrics = metrics
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._message_callbacks: list[Callable[[str], None]] = []
        self._error_callbacks: list[Callable[[Exception], None]] = []
        self._close_callbacks: list[Callable[[], None]] = []

    async def connect(self, url: str, headers: dict = None) -> None:
        """Connect to WebSocket with auto-reconnect."""
        self._ws = await websockets.connect(url, extra_headers=headers or {})
        self._heartbeat_manager.start(url, timedelta(seconds=30))

    async def send(self, data: str | bytes) -> None:
        """Send data through WebSocket."""
        if self._ws:
            await self._ws.send(data)

    async def receive(self) -> str | bytes:
        """Receive data from WebSocket."""
        if self._ws:
            return await self._ws.recv()
        raise ConnectionError("Not connected")

    async def close(self) -> None:
        """Close WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None


# ── Connection Manager ───────────────────────────────────────────────────

class ConnectionManagerImpl:
    """Manages multiple connections with health monitoring."""

    def __init__(self, health_monitor: HealthMonitor):
        self._health_monitor = health_monitor
        self._connections: dict[str, Connection] = {}
        self._lock = threading.RLock()

    def connect(self, name: str, client: RestClient | WebSocketClient) -> Connection:
        """Establish a named connection."""
        with self._lock:
            connection = Connection(name=name, client=client)
            self._connections[name] = connection

            # Register health check
            self._health_monitor.register(
                name=lambda: self._check_health(name)
            )
            return connection

    def disconnect(self, name: str) -> None:
        """Disconnect a named connection."""
        with self._lock:
            connection = self._connections.pop(name, None)
            if connection:
                connection.close()

    def is_connected(self, name: str) -> bool:
        """Check if a connection is active."""
        conn = self._connections.get(name)
        return conn is not None and conn.is_active


# ── Subscription Manager ─────────────────────────────────────────────────

class SubscriptionManagerImpl:
    """Manages streaming subscriptions with reference counting."""

    def __init__(self, streaming_port: StreamingPort):
        self._streaming_port = streaming_port
        self._subscriptions: dict[str, SubscriptionHandle] = {}
        self._ref_counts: dict[str, int] = {}
        self._lock = threading.RLock()

    def subscribe(self, key: str, callback: Callable) -> SubscriptionHandle:
        """Subscribe with reference counting."""
        with self._lock:
            if key in self._subscriptions:
                self._ref_counts[key] += 1
                return self._subscriptions[key]

            handle = self._streaming_port.subscribe(key, callback)
            self._subscriptions[key] = handle
            self._ref_counts[key] = 1
            return handle

    def unsubscribe(self, key: str) -> None:
        """Unsubscribe with reference counting."""
        with self._lock:
            if key not in self._subscriptions:
                return

            self._ref_counts[key] -= 1
            if self._ref_counts[key] <= 0:
                handle = self._subscriptions.pop(key)
                handle.unsubscribe()
                del self._ref_counts[key]

    def ref_count(self, key: str) -> int:
        """Get reference count for a subscription."""
        return self._ref_counts.get(key, 0)


# ── Scheduler ────────────────────────────────────────────────────────────

class SchedulerImpl:
    """Task scheduler for background operations."""

    def __init__(self, thread_pool: ThreadPoolManager):
        self._thread_pool = thread_pool
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False

    def schedule(self, task: Callable, interval: timedelta) -> ScheduledTask:
        """Schedule recurring task."""
        task_id = str(uuid.uuid4())
        scheduled = ScheduledTask(
            id=task_id,
            task=task,
            interval=interval,
        )
        self._tasks[task_id] = scheduled
        if self._running:
            self._start_task(scheduled)
        return scheduled

    def schedule_once(self, task: Callable, delay: timedelta) -> ScheduledTask:
        """Schedule one-time task."""
        task_id = str(uuid.uuid4())
        scheduled = ScheduledTask(
            id=task_id,
            task=task,
            interval=delay,
            once=True,
        )
        self._tasks[task_id] = scheduled
        if self._running:
            self._start_task(scheduled)
        return scheduled

    def cancel(self, task_id: str) -> None:
        """Cancel a scheduled task."""
        task = self._tasks.pop(task_id, None)
        if task:
            task.cancel()

    def start(self) -> None:
        """Start the scheduler."""
        self._running = True
        for task in self._tasks.values():
            self._start_task(task)

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        for task in self._tasks.values():
            task.cancel()


# ── Retry Engine ─────────────────────────────────────────────────────────

class RetryEngineImpl:
    """Retry logic with exponential backoff."""

    def __init__(self, metrics: MetricsCollector):
        self._metrics = metrics
        self._attempt = 0

    def execute(
        self,
        fn: Callable,
        max_retries: int = 3,
        backoff: float = 1.0,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> Any:
        """Execute with retry logic."""
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                result = fn()
                self._metrics.counter("retry.success", tags={"attempt": attempt})
                return result
            except exceptions as e:
                last_exception = e
                self._metrics.counter("retry.failure", tags={"attempt": attempt})

                if attempt < max_retries:
                    delay = self.get_backoff(attempt) * backoff
                    time.sleep(delay)

        raise last_exception

    def get_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        return min(2 ** attempt, 60)  # Max 60 seconds


# ── Circuit Breaker ──────────────────────────────────────────────────────

class CircuitBreakerImpl:
    """Circuit breaker for fault tolerance."""

    def __init__(self, config: CircuitBreakerConfig):
        self._config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._lock = threading.Lock()

    def call(self, fn: Callable) -> Any:
        """Execute if circuit is closed."""
        with self._lock:
            self._check_recovery()
            if self._state == CircuitState.OPEN:
                raise CircuitOpenError("Circuit breaker is open")

        try:
            result = fn()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise

    def record_success(self) -> None:
        """Record successful call."""
        with self._lock:
            self._success_count += 1
            if self._state == CircuitState.HALF_OPEN:
                if self._success_count >= self._config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0

    def record_failure(self) -> None:
        """Record failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._failure_count >= self._config.failure_threshold:
                self._state = CircuitState.OPEN

    def _check_recovery(self) -> None:
        """Check if circuit should transition to half-open."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._config.open_duration_ms / 1000:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0


# ── Rate Limiter ─────────────────────────────────────────────────────────

class RateLimiterImpl:
    """Token bucket rate limiter."""

    def __init__(self, rate: int, per: float):
        self._rate = rate  # tokens per period
        self._per = per    # period in seconds
        self._tokens = rate
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        """Try to acquire a token."""
        with self._lock:
            self._refill()
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False

    async def wait(self) -> None:
        """Wait until a token is available."""
        while not self.acquire():
            await asyncio.sleep(0.01)

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        new_tokens = elapsed * (self._rate / self._per)
        self._tokens = min(self._rate, self._tokens + new_tokens)
        self._last_refill = now


# ── Heartbeat Manager ────────────────────────────────────────────────────

class HeartbeatManagerImpl:
    """Connection health monitoring via heartbeats."""

    def __init__(self, scheduler: Scheduler):
        self._scheduler = scheduler
        self._heartbeats: dict[str, HeartbeatState] = {}
        self._heartbeat_callbacks: list[Callable[[str], None]] = []
        self._timeout_callbacks: list[Callable[[str], None]] = []

    def start(self, name: str, interval: timedelta) -> None:
        """Start heartbeat monitoring."""
        state = HeartbeatState(
            name=name,
            interval=interval,
            last_heartbeat=datetime.now(UTC),
        )
        self._heartbeats[name] = state

        # Schedule heartbeat check
        self._scheduler.schedule(
            task=lambda: self._check_heartbeat(name),
            interval=interval,
        )

    def stop(self, name: str) -> None:
        """Stop heartbeat monitoring."""
        self._heartbeats.pop(name, None)

    def is_alive(self, name: str) -> bool:
        """Check if connection is alive."""
        state = self._heartbeats.get(name)
        if not state:
            return False

        elapsed = datetime.now(UTC) - state.last_heartbeat
        return elapsed < state.interval * 3  # 3x interval = timeout

    def _check_heartbeat(self, name: str) -> None:
        """Check heartbeat and trigger callbacks."""
        if not self.is_alive(name):
            for callback in self._timeout_callbacks:
                callback(name)


# ── Reconnect Manager ────────────────────────────────────────────────────

class ReconnectManagerImpl:
    """Automatic reconnection with backoff."""

    def __init__(self, metrics: MetricsCollector):
        self._metrics = metrics
        self._attempts: dict[str, int] = {}
        self._max_attempts: dict[str, int] = {}
        self._last_attempt: dict[str, float] = {}

    def on_disconnect(self, name: str) -> None:
        """Handle disconnection event."""
        self._attempts[name] = self._attempts.get(name, 0) + 1
        self._last_attempt[name] = time.monotonic()
        self._metrics.counter("reconnect.attempt", tags={"connection": name})

    def should_reconnect(self, name: str) -> bool:
        """Check if reconnection should be attempted."""
        attempts = self._attempts.get(name, 0)
        max_attempts = self._max_attempts.get(name, 5)
        return attempts < max_attempts

    def get_delay(self, name: str) -> float:
        """Get reconnection delay with exponential backoff."""
        attempts = self._attempts.get(name, 0)
        return min(2 ** attempts, 30)  # Max 30 seconds

    def reset(self, name: str) -> None:
        """Reset reconnection state."""
        self._attempts[name] = 0


# ── Configuration Manager ────────────────────────────────────────────────

class ConfigurationManagerImpl:
    """Configuration management with hot-reload."""

    def __init__(self, config_path: str | None = None):
        self._config: dict[str, Any] = {}
        self._watchers: dict[str, list[Callable[[Any], None]]] = {}
        self._config_path = config_path

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        old_value = self._config.get(key)
        self._config[key] = value

        # Notify watchers
        if key in self._watchers and old_value != value:
            for callback in self._watchers[key]:
                callback(value)

    def watch(self, key: str, callback: Callable[[Any], None]) -> None:
        """Watch for configuration changes."""
        if key not in self._watchers:
            self._watchers[key] = []
        self._watchers[key].append(callback)


# ── Secrets Manager ──────────────────────────────────────────────────────

class SecretsManagerImpl:
    """Secure secrets storage."""

    def __init__(self, storage: SecureStorage):
        self._storage = storage

    def get_secret(self, name: str) -> str:
        """Get secret value."""
        return self._storage.get(name)

    def store_secret(self, name: str, value: str) -> None:
        """Store secret value."""
        self._storage.put(name, value)

    def rotate_secret(self, name: str) -> str:
        """Rotate secret and return new value."""
        new_value = self._generate_secret()
        self._storage.put(name, new_value)
        return new_value


# ── Metrics Collector ────────────────────────────────────────────────────

class MetricsCollectorImpl:
    """Metrics collection for monitoring."""

    def __init__(self):
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def counter(self, name: str, value: float = 1.0, tags: dict = None) -> None:
        """Increment counter."""
        key = self._make_key(name, tags)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value

    def gauge(self, name: str, value: float, tags: dict = None) -> None:
        """Set gauge value."""
        key = self._make_key(name, tags)
        with self._lock:
            self._gauges[key] = value

    def histogram(self, name: str, value: float, tags: dict = None) -> None:
        """Record histogram value."""
        key = self._make_key(name, tags)
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = []
            self._histograms[key].append(value)

    def timer(self, name: str) -> TimerContext:
        """Start a timer."""
        return TimerContext(self, name)


# ── Tracing Manager ──────────────────────────────────────────────────────

class TracingManagerImpl:
    """Distributed tracing for debugging."""

    def __init__(self):
        self._spans: dict[str, Span] = {}
        self._trace_id = str(uuid.uuid4())

    def start_span(self, name: str) -> Span:
        """Start a new span."""
        span_id = str(uuid.uuid4())
        span = Span(
            id=span_id,
            name=name,
            trace_id=self._trace_id,
            start_time=datetime.now(UTC),
        )
        self._spans[span_id] = span
        return span

    def end_span(self, span: Span) -> None:
        """End a span."""
        span.end_time = datetime.now(UTC)

    def trace(self, name: str) -> ContextManager[Span]:
        """Context manager for tracing."""
        span = self.start_span(name)
        try:
            yield span
        finally:
            self.end_span(span)


# ── Logging Manager ──────────────────────────────────────────────────────

class LoggingManagerImpl:
    """Centralized logging configuration."""

    def __init__(self):
        self._loggers: dict[str, logging.Logger] = {}
        self._handlers: list[logging.Handler] = []

    def get_logger(self, name: str) -> logging.Logger:
        """Get or create a logger."""
        if name not in self._loggers:
            logger = logging.getLogger(name)
            for handler in self._handlers:
                logger.addHandler(handler)
            self._loggers[name] = logger
        return self._loggers[name]

    def configure(self, config: LoggingConfig) -> None:
        """Configure logging from config."""
        logging.basicConfig(
            level=config.level,
            format=config.format,
        )


# ── Health Monitor ───────────────────────────────────────────────────────

class HealthMonitorImpl:
    """System health monitoring."""

    def __init__(self):
        self._checks: dict[str, Callable[[], HealthStatus]] = {}
        self._callbacks: list[Callable[[str, HealthStatus], None]] = []
        self._lock = threading.Lock()

    def register(self, name: str, check: Callable[[], HealthStatus]) -> None:
        """Register a health check."""
        with self._lock:
            self._checks[name] = check

    def check(self, name: str) -> HealthStatus:
        """Run a specific health check."""
        check = self._checks.get(name)
        if not check:
            return HealthStatus.UNHEALTHY
        return check()

    def status(self) -> dict[str, HealthStatus]:
        """Get status of all checks."""
        return {name: self.check(name) for name in self._checks}

    def is_healthy(self) -> bool:
        """Check if system is healthy."""
        return all(
            status == HealthStatus.HEALTHY
            for status in self.status().values()
        )


# ── Memory Cache ─────────────────────────────────────────────────────────

class MemoryCacheImpl:
    """Generic cache with TTL and LRU eviction."""

    def __init__(self, max_size: int = 1000, default_ttl: float = 300):
        self._max_size = max_size
        self._default_ttl = default TTL
        self._cache: dict[str, CacheEntry] = {}
        self._access_order: list[str] = []
        self._lock = threading.RLock()
        self._stats = CacheStats()

    def get(self, key: str) -> Any | None:
        """Get value from cache."""
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                self._stats.misses += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._stats.misses += 1
                return None

            # Update access order
            self._access_order.remove(key)
            self._access_order.append(key)

            self._stats.hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: float = None) -> None:
        """Set value in cache."""
        with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self._max_size and key not in self._cache:
                self._evict()

            self._cache[key] = CacheEntry(
                value=value,
                ttl=ttl or self._default_ttl,
            )
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

    def invalidate(self, key: str) -> None:
        """Remove value from cache."""
        with self._lock:
            self._cache.pop(key, None)
            if key in self._access_order:
                self._access_order.remove(key)

    def _evict(self) -> None:
        """Evict least recently used entry."""
        if self._access_order:
            oldest = self._access_order.pop(0)
            self._cache.pop(oldest, None)


# ── DI Container ─────────────────────────────────────────────────────────

class DIContainerImpl:
    """Lightweight dependency injection container."""

    def __init__(self):
        self._singletons: dict[type, Any] = {}
        self._factories: dict[type, Callable] = {}
        self._lock = threading.Lock()

    def register(self, interface: type, implementation: Any, singleton: bool = False) -> None:
        """Register an implementation for an interface."""
        with self._lock:
            if singleton:
                self._singletons[interface] = implementation
            else:
                self._factories[interface] = lambda: implementation

    def resolve(self, interface: type) -> Any:
        """Resolve an implementation for an interface."""
        with self._lock:
            # Check singletons first
            if interface in self._singletons:
                return self._singletons[interface]

            # Check factories
            if interface in self._factories:
                return self._factories[interface]()

            raise KeyError(f"No implementation registered for {interface}")

    def singleton(self, interface: type, factory: Callable) -> None:
        """Register a singleton factory."""
        with self._lock:
            self._singletons[interface] = factory()


# ── Thread Pool Manager ──────────────────────────────────────────────────

class ThreadPoolManagerImpl:
    """Thread pool management for async operations."""

    def __init__(self, max_workers: int = 10):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: dict[str, Future] = {}

    def submit(self, fn: Callable, *args, **kwargs) -> Future:
        """Submit a task to the thread pool."""
        return self._executor.submit(fn, *args, **kwargs)

    def map(self, fn: Callable, items: list) -> list:
        """Map function over items in parallel."""
        return list(self._executor.map(fn, items))

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the thread pool."""
        self._executor.shutdown(wait=wait)


# ── Logging Manager ──────────────────────────────────────────────────────

class LoggingManagerImpl:
    """Centralized logging configuration."""

    def __init__(self):
        self._loggers: dict[str, logging.Logger] = {}
        self._handlers: list[logging.Handler] = []
        self._level = logging.INFO

    def get_logger(self, name: str) -> logging.Logger:
        """Get or create a logger."""
        if name not in self._loggers:
            logger = logging.getLogger(name)
            logger.setLevel(self._level)
            for handler in self._handlers:
                logger.addHandler(handler)
            self._loggers[name] = logger
        return self._loggers[name]

    def configure(self, config: LoggingConfig) -> None:
        """Configure logging."""
        self._level = getattr(logging, config.level.upper())
        for logger in self._loggers.values():
            logger.setLevel(self._level)

    def set_level(self, level: str) -> None:
        """Set log level."""
        self._level = getattr(logging, level.upper())
        for logger in self._loggers.values():
            logger.setLevel(self._level)
```

---

## 8. Dependency Injection Setup

```python
# ── Container Setup ──────────────────────────────────────────────────────

def create_container() -> DIContainer:
    """Create and configure the DI container with all infrastructure."""
    container = DIContainerImpl()

    # ── Configuration ────────────────────────────────────────────────
    config = ConfigurationManagerImpl()
    container.register(ConfigurationManager, config, singleton=True)

    # ── Secrets ──────────────────────────────────────────────────────
    secrets = SecretsManagerImpl(storage=SecureStorageImpl())
    container.register(SecretsManager, secrets, singleton=True)

    # ── Metrics ──────────────────────────────────────────────────────
    metrics = MetricsCollectorImpl()
    container.register(MetricsCollector, metrics, singleton=True)

    # ── Logging ──────────────────────────────────────────────────────
    logging_mgr = LoggingManagerImpl()
    container.register(LoggingManager, logging_mgr, singleton=True)

    # ── Tracing ──────────────────────────────────────────────────────
    tracing = TracingManagerImpl()
    container.register(TracingManager, tracing, singleton=True)

    # ── Health ───────────────────────────────────────────────────────
    health = HealthMonitorImpl()
    container.register(HealthMonitor, health, singleton=True)

    # ── Cache ────────────────────────────────────────────────────────
    cache = MemoryCacheImpl(max_size=10000, default_ttl=300)
    container.register(Cache, cache, singleton=True)

    # ── Thread Pool ──────────────────────────────────────────────────
    thread_pool = ThreadPoolManagerImpl(max_workers=10)
    container.register(ThreadPoolManager, thread_pool, singleton=True)

    # ── Scheduler ────────────────────────────────────────────────────
    scheduler = SchedulerImpl(thread_pool=thread_pool)
    container.register(Scheduler, scheduler, singleton=True)

    # ── Resilience ───────────────────────────────────────────────────
    circuit_breaker = CircuitBreakerImpl(
        config=CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            open_duration_ms=30000,
        )
    )
    container.register(CircuitBreaker, circuit_breaker, singleton=True)

    retry_engine = RetryEngineImpl(metrics=metrics)
    container.register(RetryEngine, retry_engine, singleton=True)

    rate_limiter = RateLimiterImpl(rate=100, per=1.0)  # 100 req/sec
    container.register(RateLimiter, rate_limiter, singleton=True)

    # ── Token Management ─────────────────────────────────────────────
    token_manager = TokenManagerImpl(
        config=config,
        scheduler=scheduler,
        cache=cache,
    )
    container.register(TokenManager, token_manager, singleton=True)

    # ── Authentication ───────────────────────────────────────────────
    auth_manager = AuthenticationManagerImpl(
        token_manager=token_manager,
        config=config,
    )
    container.register(AuthenticationManager, auth_manager, singleton=True)

    # ── Networking ───────────────────────────────────────────────────
    rest_client = RestClientImpl(
        config=config,
        circuit_breaker=circuit_breaker,
        retry_engine=retry_engine,
        rate_limiter=rate_limiter,
        metrics=metrics,
    )
    container.register(RestClient, rest_client, singleton=True)

    ws_client = WebSocketClientImpl(
        reconnect_manager=ReconnectManagerImpl(metrics=metrics),
        heartbeat_manager=HeartbeatManagerImpl(scheduler=scheduler),
        metrics=metrics,
    )
    container.register(WebSocketClient, ws_client, singleton=True)

    # ── Connection Management ────────────────────────────────────────
    connection_manager = ConnectionManagerImpl(health_monitor=health)
    container.register(ConnectionManager, connection_manager, singleton=True)

    # ── Session Management ───────────────────────────────────────────
    session_manager = SessionManagerImpl(di_container=container)
    container.register(SessionManager, session_manager, singleton=True)

    # ── Event Bus ────────────────────────────────────────────────────
    event_bus = EventBusImpl()
    container.register(EventBus, event_bus, singleton=True)

    return container
```

---

## 9. Migration Path

### 9.1 Phase 1: Extract Infrastructure (Week 1-2)

```
inc_trade/infrastructure/
├── auth/
│   ├── authentication_manager.py
│   └── token_manager.py
├── connection/
│   ├── session_manager.py
│   ├── connection_manager.py
│   └── heartbeat_manager.py
├── network/
│   ├── rest_client.py
│   ├── websocket_client.py
│   └── reconnect_manager.py
├── resilience/
│   ├── retry_engine.py
│   ├── circuit_breaker.py
│   └── rate_limiter.py
├── streaming/
│   ├── subscription_manager.py
│   ├── event_bus.py
│   └── scheduler.py
├── observability/
│   ├── metrics_collector.py
│   ├── tracing_manager.py
│   ├── health_monitor.py
│   └── logging_manager.py
├── support/
│   ├── configuration_manager.py
│   ├── secrets_manager.py
│   ├── memory_cache.py
│   ├── di_container.py
│   └── thread_pool_manager.py
```

### 9.2 Phase 2: Enhance Instrument Objects (Week 2-3)

```
inc_trade/market/
├── instruments/
│   ├── instrument.py (base)
│   ├── equity.py
│   ├── future.py
│   ├── option.py
│   └── index.py
├── option_chain.py
├── decorators/
│   ├── decorator.py (base)
│   ├── depth_decorators.py
│   ├── cache_decorator.py
│   └── logging_decorator.py
├── repository/
│   ├── instrument_repository.py
│   └── quote_state.py
```

### 9.3 Phase 3: Create Standalone Package (Week 3-4)

```
brokers-core/
├── pyproject.toml
├── src/
│   └── brokers_core/
│       ├── domain/
│       ├── ports/
│       ├── market/
│       ├── infrastructure/
│       └── adapters/
```

---

## 10. Summary

### What Exists Now ✅

| Component | Status | Location |
|-----------|--------|----------|
| Instrument base class | ✅ Complete | `inc_trade/market/instrument.py` |
| Equity/Future/Option detection | ✅ Complete | `Instrument.is_equity()`, etc. |
| Option Chain | ✅ Complete | `inc_trade/market/option_chain.py` |
| Decorator pattern | ✅ Complete | `inc_trade/market/decorators.py` |
| Depth decorators | ✅ Complete | `inc_trade/market/depth_decorators.py` |
| Instrument Registry | ✅ Complete | `inc_trade/market/instrument_registry.py` |
| Event Bus | ✅ Complete | `inc_trade/infrastructure/event_bus.py` |
| Circuit Breaker | ✅ Complete | `inc_trade/resilience/circuit_breaker.py` |

### What Needs Enhancement 🔧

| Component | Status | What's Needed |
|-----------|--------|---------------|
| Instrument subclasses | Partial | `Equity`, `Future`, `Option`, `Index` classes |
| Instrument Repository | Partial | Add search, lazy loading, state management |
| Infrastructure layer | Partial | Extract into reusable components |
| Standalone package | Not done | Create `brokers-core` package |

### Key Design Decisions

1. **No Gateway Pattern**: Instruments own their behavior
2. **Provider Injection**: Instruments receive capabilities via providers
3. **Composition**: Decorators extend behavior without inheritance
4. **One Identity**: Repository guarantees single instance per symbol
5. **Infrastructure Reuse**: All brokers share common infrastructure
