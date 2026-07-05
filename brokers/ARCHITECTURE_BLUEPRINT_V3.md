# Elite Quantitative Engineering Review Board — Institutional Broker Platform Architecture Blueprint

## Executive Summary

After thorough analysis of the actual codebase (1,449 test baseline, 60+ source files, 3 broker adapters), this document presents the complete architecture, migration plan, and implementation roadmap for transforming the TradeXV2 broker module from a **broker-centric Gateway architecture** to an **instrument-centric platform architecture**.

**Key Finding**: The codebase has already made significant progress — 80% of the foundation is in place. The remaining work is surgical integration of existing components (OMS, Event Bus, Extensions) and adding new bounded contexts (Replay, Scanner, Backtesting).

---

## 1. Current Architecture Assessment

### What Exists (Actual Code Analysis)

```
Layer        | Files | Tests | Status
─────────────|───────|───────|──────
domain/      | 12    | 200+  | ✅ Stable — entities, enums, validators, exceptions, events
ports/       | 18    | 67    | ✅ Stable — Protocols, runtime_checkable
services/    | 15    | 100+  | ✅ Stable — facade, session, router, services
market/      | 7     | 70+   | ✅ Stable — context, instrument, registry, streaming
trading/     | 4     | 60+   | ✅ Stable — context, account, registry, repository
adapters/    | 55+   | 80+   | ✅ Stable — Dhan (38 files), Upstox (25), Paper (1)
infrastructure/ | 17  | 30+  | ✅ Stable — cache, event_bus, http, credentials
oms/         | 2     | 0     | ⚠️ Built but UNTESTED, NOT integrated
```

### What's Already Correct

1. **Instrument-centric** — `Instrument` domain entity exists with `composite_key`, type detection, price/quantity validation
2. **InstrumentRegistry** — Thread-safe, one instance per symbol, factory pattern
3. **MarketDataContext** — InstrumentHandle with `quote()`, `depth()`, `ohlcv()`, `option_chain()`, `subscribe()`
4. **SubscriptionManager** — Ref-counted, deduplicated streaming
5. **StreamingRouter** — Multi-backend with priority-based selection and fallback
6. **HistoricalRouter** — Cache-first, multi-provider, pagination, merge
7. **BrokerCapabilities** — 40+ boolean capability fields, runtime discovery
8. **Architecture tests** — 59 enforceable rules (boundary, port structure, exceptions)
9. **Contract tests** — 9 files covering all port interfaces
10. **EventBus** — Exists but NOT wired into streaming/trading flows

### What's Missing

| Component | Status | Risk |
|-----------|--------|------|
| OMS integration into TradingContext | ❌ Not done | Orders bypass validation/idempotency |
| OMS tests | ❌ Not done | No regression safety net |
| ExecutionRouter integration | ❌ Not done | Multi-account routing unavailable |
| Event-driven streaming | ❌ Not done | State updates are imperative |
| Extension isolation | ❌ Not done | Broker-specific code in common ports |
| Gateway deprecation path | ❌ Not done | Old API still primary |
| Replay engine | ❌ Not done | No offline data support |
| Market Router (quote/depth) | ❌ Not done | No cache-first for quotes |
| Backtesting | ❌ Not done | No historical simulation |
| Scanner | ❌ Not done | No multi-instrument screening |

---

## 2. Future-State Architecture Blueprint

### 2.1 Package Organization

```
brokers/
├── __init__.py              # Public API: connect(), create_broker(), exports
│
├── domain/                  # ⭐ Layer 0 — Pure business logic
│   ├── __init__.py
│   ├── entities.py           # Order, Quote, Trade, Position, etc. (frozen dataclasses)
│   ├── enums.py              # Side, OrderType, OrderStatus, BrokerID, etc.
│   ├── capabilities.py       # BrokerCapabilities dataclass (40+ boolean fields)
│   ├── exceptions.py         # TradeXV2Error hierarchy (18 exception types)
│   ├── error_codes.py        # String constants for structured errors
│   ├── events.py             # DomainEvent — immutable event value object
│   ├── symbols.py            # Symbol/exchange normalization utilities
│   ├── order_lifecycle.py    # Order status state machine
│   ├── cache_policy.py       # TTL configuration for caching
│   ├── lifecycle_health.py   # HealthState enum, HealthStatus dataclass
│   ├── requests.py           # MarketOrder, LimitOrder, StopMarketOrder, StopLimitOrder
│   ├── constants/
│   │   ├── capabilities.py   # Feature constant names
│   │   └── exchanges.py      # Exchange set definitions
│   └── validators/
│       └── order_validator.py # 10+ pure validation functions
│
├── ports/                   # ⭐ Layer 1 — Interface contracts (Protocols)
│   ├── __init__.py           # Re-exports all ports
│   ├── broker.py             # BrokerGateway Protocol (primary broker interface)
│   ├── market_data.py        # MarketDataPort — ltp, quote, depth
│   ├── order_execution.py    # OrderExecutionPort — place, modify, cancel
│   ├── streaming.py          # StreamingPort — WebSocket lifecycle
│   ├── historical.py         # HistoricalPort — candles
│   ├── historical_provider.py # HistoricalProvider — pluggable data source
│   ├── options.py            # OptionsPort — option chains, expiries
│   ├── instruments.py        # InstrumentPort — search, resolve
│   ├── portfolio.py          # PortfolioPort — positions, holdings, funds
│   ├── auth.py               # AuthPort — login, logout, token
│   ├── cache_port.py         # CachePort — generic cache interface
│   ├── capabilities.py       # Extension Protocols (MarginProvider, SuperOrderProvider, etc.)
│   ├── clock.py              # ClockPort, SystemClock
│   ├── connection_lifecycle.py # ConnectionLifecyclePort
│   ├── event_publisher.py    # EventPublisherPort
│   ├── extension_registry.py # ExtensionRegistryPort
│   ├── http_client_port.py   # HttpClientPort
│   ├── risk_manager.py       # RiskManagerPort
│   └── token_store.py        # TokenStorePort
│
├── market/                  # ⭐ Market Data Context
│   ├── __init__.py
│   ├── context.py            # MarketDataContext + InstrumentHandle + SubscriptionHandle
│   ├── instrument.py         # Instrument (canonical domain entity)
│   ├── instrument_registry.py # Thread-safe one-instance-per-symbol registry
│   ├── quote_state.py        # Mutable quote state (updated by streaming)
│   ├── depth_state.py        # Mutable depth state (updated by streaming)
│   ├── subscription_manager.py # Ref-counted, deduplicated streaming
│   └── streaming_router.py   # Multi-backend streaming router with fallback
│
├── trading/                 # ⭐ Trading Context
│   ├── __init__.py
│   ├── account.py            # Account + AccountType + AccountStatus
│   ├── account_registry.py   # Thread-safe one-instance-per-account registry
│   ├── context.py            # TradingContext + AccountHandle
│   └── order_repository.py   # Thread-safe in-memory order store
│
├── services/                # ⭐ Application Services
│   ├── __init__.py
│   ├── broker_facade.py      # BrokerFacade (DEPRECATED — use BrokerSession)
│   ├── broker_session.py     # BrokerSession (composition root)
│   ├── broker_router.py      # BrokerRouter (multi-broker routing)
│   ├── capability_discovery.py # Feature discovery service
│   ├── historical_router.py  # Cache-first multi-provider historical router
│   ├── historical_service.py # HistoricalService
│   ├── instrument_service.py # InstrumentService
│   ├── market_data_service.py # MarketDataService
│   ├── options_service.py    # OptionsService
│   ├── order_service.py      # OrderService (DEPRECATED — use OMS)
│   ├── order_validation.py   # OrderValidation (DEPRECATED — use domain validators)
│   ├── portfolio_service.py  # PortfolioService
│   └── shadow_broker.py      # Shadow routing service
│
├── adapters/                # ⭐ Broker Implementations
│   ├── __init__.py
│   ├── base_streaming.py     # Base streaming adapter
│   ├── dhan/                 # Dhan adapter (38 files)
│   │   ├── gateway.py        # DhanGateway — implements BrokerGateway
│   │   ├── capabilities.py   # Dhan capability matrix
│   │   ├── orders.py         # OrderExecutionPort implementation
│   │   ├── market_data.py    # MarketDataPort implementation
│   │   ├── streaming.py      # StreamingPort implementation
│   │   ├── historical.py     # HistoricalPort implementation
│   │   ├── options.py        # OptionsPort implementation
│   │   ├── auth.py           # AuthPort implementation
│   │   ├── portfolio.py      # PortfolioPort implementation
│   │   ├── instruments.py    # InstrumentPort implementation
│   │   ├── extensions/       # Broker-specific extension modules
│   │   │   ├── forever_orders.py
│   │   │   ├── super_orders.py
│   │   │   ├── margin.py
│   │   │   └── models.py
│   │   └── ... (20+ supporting files)
│   ├── upstox/               # Upstox adapter (25 files)
│   │   ├── gateway.py        # UpstoxGateway — implements BrokerGateway
│   │   ├── capabilities.py
│   │   ├── orders.py
│   │   ├── market_data.py
│   │   ├── streaming.py
│   │   ├── historical.py
│   │   ├── options.py
│   │   ├── portfolio.py
│   │   ├── instruments.py
│   │   └── ... (15+ supporting files)
│   ├── paper/                # Paper trading adapter
│   │   ├── gateway.py        # PaperGateway — implements BrokerGateway
│   │   └── capabilities.py
│   └── replay/               # 🔜 Future: Replay engine
│
├── oms/                     # ⭐ Order Management System
│   ├── __init__.py
│   ├── manager.py            # BrokerManager (UNTESTED)
│   └── router.py             # OrderRouter (UNTESTED)
│
├── infrastructure/          # ⭐ Shared Infrastructure
│   ├── __init__.py
│   ├── bootstrap.py          # DI setup
│   ├── correlation.py        # Correlation ID tracking
│   ├── credentials.py        # Credential management
│   ├── event_bus.py          # In-process EventBus
│   ├── jwt_expiry.py         # JWT validity checking
│   ├── lifecycle.py          # Lifecycle manager
│   ├── logging.py            # Logging configuration
│   ├── reconnect_strategy.py # Backoff/reconnect policies
│   ├── registry.py           # Component registry
│   ├── secret_manager.py     # Secret storage
│   ├── seq_counter.py        # Monotonic sequence counter
│   ├── ssl_hardening.py      # SSL/TLS hardening
│   ├── token_broadcast.py    # Token change broadcasting
│   ├── totp_cooldown.py      # TOTP rate limiting
│   ├── websocket_pool.py     # WebSocket connection pool
│   ├── websocket_runner.py   # WebSocket runner
│   ├── cache/
│   │   ├── __init__.py
│   │   └── memory_cache.py   # MemoryCache — TTL, LRU, stale-while-revalidate
│   ├── http/
│   │   └── ...               # HTTP client implementations
│   ├── observability/
│   │   └── ...               # Metrics, tracing
│   └── storage/
│       └── ...               # Persistent storage
│
├── config/                  # Configuration
├── core/                    # Core utilities
├── resilience/              # Circuit breakers, retry
├── utils/                   # Shared utilities
│
└── tests/
    ├── __init__.py
    ├── pytest.ini
    ├── parity_validation.py
    ├── unit/                 # 1,449 unit tests
    │   ├── test_architecture.py  # 59 architecture guardrails
    │   ├── test_subscription_manager.py  # 27 tests
    │   ├── test_streaming_router.py  # 18 tests
    │   ├── test_historical_router.py  # 20+ tests
    │   ├── test_memory_cache.py  # 20+ tests
    │   ├── test_market_context.py  # 45+ tests
    │   ├── test_trading_context.py  # 50+ tests
    │   ├── test_broker_session.py
    │   ├── test_broker_facade.py
    │   ├── test_domain_entities.py
    │   ├── test_order_lifecycle.py
    │   ├── test_order_validation.py
    │   ├── test_paper_adapter.py
    │   └── ... (35+ test files)
    ├── contract/             # 9 contract test files
    │   ├── test_broker_contract.py
    │   ├── test_market_data_contract.py
    │   ├── test_order_contract.py
    │   ├── test_portfolio_contract.py
    │   ├── test_historical_contract.py
    │   ├── test_streaming_contract.py
    │   ├── test_options_contract.py
    │   ├── test_instruments_contract.py
    │   └── test_capability_contract.py
    └── integration/          # Integration tests (require credentials)
```

### 2.2 Directed Dependency Graph

```
                    ┌──────────────────────────────────────┐
                    │           adapters/                   │
                    │  (DhanGateway, UpstoxGateway,         │
                    │   PaperGateway, ReplayEngine🔜)       │
                    │                                       │
                    │  Depends on: ports, domain,           │
                    │  infrastructure                       │
                    └──────────┬───────────────────────────┘
                               │ implements
                               ▼
                    ┌──────────────────────────────────────┐
                    │           ports/                      │
                    │  (Protocols — BrokerGateway,          │
                    │   MarketDataPort, OrderExecutionPort, │
                    │   StreamingPort, HistoricalPort,      │
                    │   PortfolioPort, CachePort, etc.)     │
                    │                                       │
                    │  Depends on: domain only              │
                    └──────────┬───────────────────────────┘
                               │ consumed by
                    ┌──────────┴──────────┬─────────────────┐
                    │                     │                 │
                    ▼                     ▼                 ▼
        ┌───────────────────┐  ┌──────────────────┐  ┌──────────────┐
        │   market/         │  │   trading/       │  │   oms/       │
        │   (MarketDataCtx, │  │   (TradingCtx,   │  │   (Broker-   │
        │    Instrument,    │  │    Account,       │  │    Manager,  │
        │    Registry,      │  │    OrderRepo)     │  │    Exec-     │
        │    Subscription-  │  │                   │  │    Router)   │
        │    Manager)       │  │  Depends on:      │  │              │
        │                   │  │  domain, ports,   │  │  Depends on: │
        │  Depends on:      │  │  trading/ (self)  │  │  domain,     │
        │  domain, ports,   │  │                   │  │  ports, oms/ │
        │  market/ (self)   │  │  NEVER imports:   │  │  (self)      │
        │                   │  │  services/        │  │              │
        │  NEVER imports:   │  │  infrastructure/  │  │  MUST NOT    │
        │  services/        │  │  adapters/        │  │  import:     │
        │  trading/         │  │                   │  │  adapters/   │
        └───────────────────┘  └──────────────────┘  └──────┬───────┘
                                                             │
                    ┌────────────────────────────────────────┘
                    │
                    ▼
        ┌──────────────────────────────────────┐
        │         services/                    │
        │  (BrokerSession, BrokerFacade🔜,    │
        │   HistoricalRouter, Service impls)   │
        │                                      │
        │  Depends on: domain, ports,          │
        │  services/ (self), utils, market,    │
        │  trading, infrastructure             │
        └──────────────────────────────────────┘

        ┌──────────────────────────────────────┐
        │      infrastructure/                 │
        │  (EventBus, MemoryCache, Credentials,│
        │   Logging, HTTP, WebSocket, Token)   │
        │                                      │
        │  Depends on: domain, ports,          │
        │  infrastructure/ (self), config,     │
        │  core, resilience                    │
        └──────────────────────────────────────┘

        ┌──────────────────────────────────────┐
        │      domain/                         │
        │  (entities, enums, exceptions,       │
        │   validators, capabilities, events)  │
        │                                      │
        │  ZERO DEPENDENCIES (inner layer)     │
        └──────────────────────────────────────┘
```

### 2.3 Bounded Context Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TRADEVX2 BROKER PLATFORM                         │
├─────────────────┬─────────────────────┬─────────────────────────────┤
│  MARKET DATA     │      TRADING        │     INFRASTRUCTURE          │
│  CONTEXT         │      CONTEXT        │     CONTEXT                 │
├─────────────────┼─────────────────────┼─────────────────────────────┤
│ Instrument      │ Account             │ EventBus                    │
│ InstrumentReg.  │ AccountRegistry     │ MemoryCache                 │
│ QuoteState       │ OrderRepository    │ WebSocketPool               │
│ DepthState       │ TradingContext     │ Credentials                 │
│ MarketDataCtx   │ AccountHandle       │ Logging                     │
│ SubscriptionMgr │                     │ Token Management            │
│ StreamingRouter │ OMS                 │ HTTP Clients                │
│ HistoricalRouter│ OrderManagementSys  │ Circuit Breakers            │
│                 │ ExecutionRouter     │ Reconnection Strategies      │
├─────────────────┴─────────────────────┴─────────────────────────────┤
│                     CANONICAL DOMAIN MODEL                           │
│  Instrument | Order | Quote | Depth | Trade | Position | Holding    │
│  Balance | Candle | OptionChain | OptionStrike | OptionLeg          │
│  OrderRequest | OrderResponse | RiskCheckRequest | NewsItem         │
│  BrokerCapabilities | DomainEvent | HealthStatus                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Instrument-Centric Design

### 3.1 Public API

```python
import brokers

# NEW: Connect returns a BrokerSession (the primary API)
broker = brokers.connect("dhan", access_token="...", client_id="...")

# 1. INSTRUMENT-CENTRIC market data
instrument = broker.market.instrument("NSE:RELIANCE")
quote = instrument.quote()           # Returns Quote domain entity
depth = instrument.depth()           # Returns MarketDepth domain entity
candles = instrument.ohlcv("1D")     # Historical via cache-first router
chain = instrument.option_chain()    # Option chain (for derivatives)
instrument.subscribe(on_tick)        # Live streaming

# 2. ACCOUNT-CENTRIC trading
account = broker.trading.default_account()
resp = account.place_order("RELIANCE", "NSE", Side.BUY, 10)
orders = account.get_orders()
positions = account.positions()

# 3. Capability discovery
caps = broker.capabilities          # BrokerCapabilities dataclass
caps.supports("option_chain")       # True/False

# 4. Broker-specific extensions
forever = broker.extensions.get_extension("dhan", ForeverOrderProvider)
forever.place_forever_order({...})

# 5. Lifecycle
broker.close()                      # Graceful shutdown
```

---

## 4. Phased Implementation Plan

### Phase 6: OMS & Execution Router (🔴 CURRENT — 2 weeks)

**Definition of Done**:
- [ ] `trading/oms.py` — OrderManagementSystem with validation, idempotency, kill switch, repository tracking
- [ ] `trading/execution_router.py` — ExecutionRouter with account-based broker routing
- [ ] Integration into `TradingContext` (OMS injected, fallback to legacy path)
- [ ] Wired in `brokers/__init__.py connect()` — OMS created with repository + router
- [ ] 20+ unit tests passing (order_repository, oms, execution_router)
- [ ] All architecture tests passing (no boundary violations)
- [ ] Backward compatibility verified: legacy `account.place_order()` still works
- [ ] Integration tests verify OMS path vs legacy path equivalence

**Task List**:

| # | Task | File | Tests | Acceptance |
|---|------|------|-------|------------|
| 6.1 | Complete `trading/oms.py` | `trading/oms.py` | 8 tests | OMS validates fields, checks kill switch, checks idempotency, routes to correct adapter, saves to repository |
| 6.2 | Complete `trading/execution_router.py` | `trading/execution_router.py` | 4 tests | Router registers adapters, routes by account_id pattern, falls back gracefully |
| 6.3 | Write order_repository tests | `tests/unit/test_order_repository.py` | 8 tests | Save/get/update/query/thread-safety |
| 6.4 | Integrate OMS into TradingContext | `trading/context.py` | — | AccountHandle.place_order() checks OMS first |
| 6.5 | Wire OMS in connect() | `brokers/__init__.py` | — | connect() creates OMS, passes to TradingContext |
| 6.6 | Regression verification | — | — | Full suite: 1,449+ existing tests still pass |

**Risk**: OMS must NOT import `services/` (architecture rule). Validation must use `domain.validators` inline.

---

### Phase 7: Extension Isolation (2 weeks)

**Definition of Done**:
- [ ] All broker-specific extension Protocols moved from `ports/capabilities.py` to `adapters/{broker}/extensions/`
- [ ] Common extension Protocols stay in `ports/` but are broker-agnostic
- [ ] Plugin-based extension registry loads extensions dynamically
- [ ] Dhan-specific: `ForeverOrderProvider`, `SuperOrderProvider`, `SliceOrderProvider`, `MarginProvider`
- [ ] Upstox-specific: `GTTProvider`, `NewsProvider`
- [ ] Extension discovery via `BrokerCapabilities.extensions` field
- [ ] 15+ new architecture tests verifying extension isolation
- [ ] Backward compatibility maintained through deprecated re-exports

**Task List**:

| # | Task | Acceptance |
|---|------|------------|
| 7.1 | Move Dhan extensions to `adapters/dhan/extensions/` | No common port imports Dhan-specific types |
| 7.2 | Move Upstox extensions to `adapters/upstox/extensions/` | No common port imports Upstox-specific types |
| 7.3 | Create `ports/extensions.py` with broker-agnostic Protocols | Only generic extension protocols remain |
| 7.4 | Implement plugin-based extension loader | `broker.extensions.get("forever_order")` works |
| 7.5 | Add deprecated re-exports in original locations | Old imports emit deprecation warnings |
| 7.6 | Add architecture tests for extension boundary | Tests verify adapters/ ≠ ports/ extension leakage |

---

### Phase 8: Event Bus Integration (2 weeks)

**Definition of Done**:
- [ ] Typed event hierarchy: `MarketEvent`, `TradingEvent`, `AccountEvent`, `ConnectionEvent`
- [ ] Streaming callbacks publish events instead of directly updating state
- [ ] `EventBus.subscribe()` used by `MarketDataContext` to update `QuoteState`
- [ ] Order status updates published as `OrderEvent` → consumed by `OrderRepository`
- [ ] Connection lifecycle events: `Connected`, `Disconnected`, `Reconnected`, `TokenExpired`
- [ ] 20-25 new tests for event publishing/consumption
- [ ] Backward compatibility: direct callbacks still work (dual path)

**Task List**:

| # | Task | Acceptance |
|---|------|------------|
| 8.1 | Define typed event hierarchy in `domain/events.py` | `MarketEvent`, `TradingEvent`, `AccountEvent`, `ConnectionEvent` |
| 8.2 | Enhance `EventBus` with type filtering | Subscribe by event type class, not string |
| 8.3 | Wire streaming ticks → EventBus → QuoteState | Streaming publishes `QuoteUpdated` → MarketDataContext auto-updates |
| 8.4 | Wire order updates → EventBus → OrderRepository | OMS publishes `OrderPlaced/Modified/Filled/Rejected` |
| 8.5 | Wire connection events → EventBus → reconnect | Streaming adapter publishes `ConnectionLost/Recovered` |
| 8.6 | Add event logging/metrics middleware | Every event logged with correlation_id |

---

### Phase 9: Gateway Deprecation (1 week)

**Definition of Done**:
- [ ] `create_broker()` emits `DeprecationWarning` suggesting `connect()`
- [ ] `BrokerFacade` methods delegate to `BrokerSession` internals
- [ ] `_underlying_gateway` property removed (after verifying no consumers)
- [ ] All documentation references updated to use `connect()` + `BrokerSession`
- [ ] `BrokerGateway` Protocol remains for internal adapter contract (not deprecated)
- [ ] 10+ backward compatibility tests
- [ ] Full suite passes without deprecation warnings in new code

**Task List**:

| # | Task | Acceptance |
|---|------|------------|
| 9.1 | Add `DeprecationWarning` to `create_broker()` | Warning visible in test output |
| 9.2 | Replace `BrokerFacade._underlying_gateway` with delegation | No direct `_gateway` references in services/ |
| 9.3 | Update `brokers/__init__.py` exports | Session types prioritized over facade types |
| 9.4 | Add test verifying old path still works | `create_broker("paper")` returns valid facade |
| 9.5 | Archive old code paths (comment, not delete) | Deprecated paths marked with `# DEPRECATED` |

---

### Phase 10: Replay Engine & Paper Improvements (3 weeks)

**Definition of Done**:
- [ ] `adapters/replay/` — replay engine implementing `HistoricalProvider` + `StreamingPort`
- [ ] Replay reads from CSV, Parquet, or database
- [ ] Replay supports time-based seeking (start from specific datetime)
- [ ] Replay supports speed control (1x, 10x, 100x)
- [ ] PaperGateway enhanced with: fill simulation, slippage model, basic order book
- [ ] PaperGateway implements full `OrderExecutionPort` with state machine validation
- [ ] CSV provider for historical data (implements `HistoricalProvider`)
- [ ] 25-30 new tests for replay and paper enhancements
- [ ] Contract tests pass for replay adapter

**Task List**:

| # | Task | Acceptance |
|---|------|------------|
| 10.1 | Create `adapters/replay/engine.py` | ReplayEngine implements StreamingPort |
| 10.2 | Create replay data reader (CSV/Parquet) | Reads candle files, yields ticks |
| 10.3 | Implement time-based seeking | `replay.seek(datetime(2024, 1, 1))` |
| 10.4 | Implement speed control | `replay.set_speed(10.0)` → 10x playback |
| 10.5 | Enhance PaperGateway fills | Market orders filled at simulated price |
| 10.6 | Add slippage model to PaperGateway | Configurable slippage percentage |
| 10.7 | Add order book simulation to PaperGateway | Basic bid/ask tracking |
| 10.8 | Create CSV historical provider | `adapters/replay/csv_provider.py` |

---

### Phase 11: Market Router (2 weeks)

**Definition of Done**:
- [ ] `market/market_router.py` — unified quote/depth routing with cache-first
- [ ] Cache-first for quotes (TTL: 2 seconds)
- [ ] Cache-first for depth (TTL: 1 second)
- [ ] Multi-provider fallback (primary broker → fallback broker)
- [ ] Stale-while-revalidate pattern (serve stale quote while fetching fresh)
- [ ] Batch-aware routing (prefer providers that support batch)
- [ ] 20-25 new tests
- [ ] Integration into `MarketDataContext` as optional enhancement

**Task List**:

| # | Task | Acceptance |
|---|------|------------|
| 11.1 | Define `MarketRouter` class | Routes quote/depth requests through cache |
| 11.2 | Implement cache-first quote path | `router.quote(key)` → cache hit → return; cache miss → provider → cache → return |
| 11.3 | Implement cache-first depth path | Same pattern as quote |
| 11.4 | Implement stale-while-revalidate | Serve stale quote, fetch fresh in background |
| 11.5 | Wire router into MarketDataContext | Optional: if present, use; else direct adapter |

---

### Phase 12: Backtesting & Scanner (3 weeks)

**Definition of Done**:
- [ ] `trading/backtesting/` — backtesting engine
  - [ ] Account simulation with historical data
  - [ ] Order execution against historical fills
  - [ ] P&L calculation
  - [ ] Performance metrics (Sharpe, max drawdown, win rate)
- [ ] `market/scanner/` — multi-instrument screening
  - [ ] Scanner operates on Instrument objects (broker-agnostic)
  - [ ] Configurable scan criteria (price > X, volume > Y, etc.)
  - [ ] Real-time scanning via streaming subscriptions
  - [ ] Results published via EventBus
- [ ] 30-40 new tests
- [ ] Contract tests for backtesting adapter

---

## 5. Architecture Fitness Functions

Executable rules enforced by architecture tests (59 existing + new):

```python
# Phase 6 additions
def test_oms_does_not_import_services(): ...
def test_execution_router_does_not_import_adapters(): ...
def test_account_handle_can_use_oms(): ...
def test_connect_creates_oms_when_available(): ...

# Phase 7 additions
def test_dhan_extensions_not_in_common_ports(): ...
def test_upstox_extensions_not_in_common_ports(): ...
def test_extension_registry_accepts_any_protocol(): ...
def test_no_broker_specific_code_in_ports(): ...

# Phase 8 additions
def test_event_bus_subscribe_returns_token(): ...
def test_events_are_immutable(): ...
def test_streaming_publishes_quote_events(): ...
```

---

## 6. Testing Strategy

### Test Pyramid (Current: 1,449 unit + 10 contract = ~1,459)

```
           🔵 10 Integration (manual, requires credentials)
         🟢 10 Contract (automated CI)
       🟡 1,449+ Unit (automated CI, <60s)
     🔴 59 Architecture (automated CI, <2s)
```

### Phase 6 Test Plan (20+ new tests)

**test_order_repository.py** (8 tests):
```python
def test_save_and_get():          # Round-trip
def test_get_returns_none_for_missing():  # Not found
def test_update_status():         # Status transition
def test_get_by_account():        # Account-scoped query
def test_get_active_filters_terminal():  # Active filter
def test_thread_safety():         # Concurrent access
def test_clear():                 # Reset
def test_count():                 # Total count
```

**test_oms.py** (8 tests):
```python
def test_place_order_validates():       # Empty symbol → ValidationError
def test_place_order_kill_switch():     # kill_switch=True → blocks orders
def test_place_order_idempotency():     # Same correlation_id → cached response
def test_place_order_routes():          # Routes to correct adapter
def test_place_order_saves_to_repo():   # Order saved after place
def test_cancel_order():               # Cancel delegated to router
def test_modify_order():               # Modify delegated to router
def test_place_order_correlation_id(): # Idempotent with correlation_id
```

**test_execution_router.py** (4 tests):
```python
def test_register_and_route():          # Route by account_id → correct adapter
def test_route_unknown_raises():        # Unknown account → KeyError
def test_place_order_through_router():  # Full path: router.place → adapter.place
def test_fallback_routing():            # Primary broker down → fallback
```

---

## 7. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 1 | OMS creates circular dependency with services/ | Medium | High | Architecture tests enforce OMS doesn't import services/ |
| 2 | OMS bypassed by legacy path | High | Medium | Both paths coexist; OMS path is default; legacy deprecated |
| 3 | Thread safety in OMS (streaming callbacks + API calls) | Medium | High | RLock on all state mutations in repository |
| 4 | Extension isolation breaks existing consumers | Low | High | Deprecated re-exports with warnings; test backward compat |
| 5 | Event bus introduces latency in streaming path | Medium | Low | Synchronous (in-process) bus; no serialization overhead |
| 6 | Replay engine performance with large datasets | Medium | Medium | Streaming reader (not loading all into memory) |
| 7 | Scanner memory with thousands of instruments | Low | Medium | Configurable instrument limits; paginated results |

---

## 8. Rollback Strategy

Each phase has a feature-flag based rollback:

```python
# In connect():
def connect(name, ..., use_oms=True, use_event_bus=False, ...):
    if use_oms and name not in ("paper",):  # Paper doesn't need OMS yet
        oms = build_oms()
    else:
        oms = None  # Falls back to legacy path
    
    if use_event_bus:
        bus = EventBus()
        streaming_adapter.set_event_bus(bus)
    else:
        bus = None  # Direct callbacks (legacy)
```

Rollback = flip feature flag. No code revert needed.

---

## 9. Architecture Decision Records

### ADR-6: OMS Lives in trading/ NOT services/

**Decision**: The `OrderManagementSystem` lives in `trading/oms.py` alongside `TradingContext`.

**Rationale**:
- OMS is part of the Trading bounded context
- `services/` is for legacy orchestration (being deprecated)
- `trading/` already contains `OrderRepository` which OMS depends on
- Architecture rule: `services/` can import `trading/`, but `trading/` must NOT import `services/`

**Consequences**:
- OMS cannot use `services/order_service.py` (must use domain validators directly)
- OMS receives `OrderExecutionPort` directly (same protocol gateways implement)
- `BrokerFacade` (in services/) can wrap OMS for backward compat

### ADR-7: ExecutionRouter Parses Account IDs

**Decision**: `ExecutionRouter` extracts broker_id from account_id using pattern `{broker_id}/default`.

**Rationale**:
- Account IDs already follow this format (established in `TradingContext.__init__`)
- No separate broker→account mapping needed
- Simple, predictable, testable

**Consequences**:
- Router must validate account_id format
- Multi-account per broker requires `{broker_id}/{account_name}` convention

### ADR-8: EventBus is Synchronous and In-Process

**Decision**: The event bus operates synchronously within the same process.

**Rationale**:
- All consumers are in-process (no cross-process events needed)
- Zero serialization overhead
- Simpler debugging and testing
- Martin Kleppmann's ordering guarantees apply within a thread

**Consequences**:
- Cannot distribute events across processes (future: add external message bus adapter)
- Handler must be fast (blocking handlers block the publisher)
- Thread safety must be ensured by handlers (not the bus)

### ADR-9: Replay Engine Implements StreamingPort

**Decision**: The replay engine implements `StreamingPort` Protocol, making it a drop-in replacement for live WebSocket streaming.

**Rationale**:
- Same interface for live and historical streaming
- `MarketDataContext.subscribe()` works identically for both
- Backtesting engine can use replay as data source
- Zero code changes in market data context

**Consequences**:
- Replay engine must manage virtual time (not wall-clock time)
- Callback signature matches live streaming (consumers can't distinguish)

---

## 10. Phase 6 Implementation — Detailed Code

Let me now implement Phase 6 (OMS & Execution Router) with complete code and tests.

