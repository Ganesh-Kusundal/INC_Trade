# Phase 1 — Complete Source Code Audit

**Date:** 2026-07-02
**Scope:** `archive/` — 863 Python files across 120+ directories
**Method:** Exhaustive file-by-file read, class/method/protocol extraction

---

## 1. Repository Structure Overview

```
archive/
├── application/          # Application services (OMS)
├── brokers/
│   ├── common/           # Shared broker abstraction layer (hexagonal architecture)
│   │   ├── adapters/     # Sync→Async gateway bridge
│   │   ├── api/          # API contracts, SPI, broker source enum
│   │   ├── auth/         # Token lifecycle, TOTP, credential management
│   │   ├── config/       # Endpoints, indices, feature flags
│   │   ├── connection/   # Bootstrap, readiness probes, WS auth coordination
│   │   ├── contracts/    # Broker contract test suites
│   │   ├── core/         # Constants (auth, market, exchanges, timeouts, resilience)
│   │   ├── domain/       # Entities, events, ports, repositories, value objects
│   │   ├── extensions/   # Broker-specific extension registry (11 extensions)
│   │   ├── gateway/      # (re-exports)
│   │   ├── idempotency/  # Idempotency service
│   │   ├── infrastructure/ # Event bus, lifecycle, metrics, observability, IO
│   │   ├── lifecycle/    # Managed service lifecycle
│   │   ├── observability/ # Audit events, health checks, alerting
│   │   ├── oms/          # Order management, margin provider
│   │   ├── options/      # Option chain normalization
│   │   ├── orchestrator/ # Stream orchestration
│   │   ├── reconciliation/ # Order/position reconciliation engine
│   │   ├── resilience/   # Retry, circuit breaker, rate limiter, error hierarchy
│   │   ├── services/     # Benchmark, validation, download engine, historical data
│   │   └── websocket/    # WebSocket reconnection
│   ├── dhan/             # Dhan broker adapter
│   │   ├── instruments/  # Instrument master download/management
│   │   ├── resilience/   # Dhan-specific resilience
│   │   ├── websocket/    # Dhan WebSocket streaming
│   │   └── tests/        # Unit, integration, contract, regression
│   ├── paper/            # Paper trading broker
│   │   └── tests/        # Paper contract tests
│   ├── upstox/           # Upstox broker adapter
│   │   ├── auth/         # OAuth2+PKCE, TOTP, token manager, redirect server
│   │   ├── capabilities/ # Orders, instruments, market_data, streaming, portfolio, snapshot
│   │   ├── config/       # Upstox-specific config
│   │   ├── fundamentals/ # Company financials
│   │   ├── instruments/  # Instrument master
│   │   ├── ipo/          # IPO adapter
│   │   ├── kill_switch/  # Emergency kill switch
│   │   ├── mappers/      # Data mappers
│   │   ├── market_data/  # Market data services
│   │   ├── market_intelligence/ # OI analysis, FII/DII, smartlists
│   │   ├── mutual_funds/ # Mutual fund adapter
│   │   ├── news/         # News feed
│   │   ├── orders/       # Order management
│   │   ├── payments/     # Payments adapter
│   │   ├── reconciliation/ # Reconciliation service
│   │   ├── static_ip/    # Static IP management
│   │   ├── websocket/    # Protobuf v3 decoder, feed authorizer, auto-reconnect
│   │   └── tests/        # Unit, integration, contract, conformance
│   └── tests/            # Cross-broker e2e and integration tests
├── config/               # Platform configuration (profiles, schema, validation)
├── datalake/             # Data lake gateway
├── domain/               # Platform domain layer
│   ├── constants/        # Domain-wide constants
│   ├── entities/         # Core domain entities
│   ├── events/           # Domain events
│   ├── execution/        # Execution domain
│   ├── models/           # Domain models
│   ├── ports/            # Domain port interfaces
│   ├── repositories/     # Repository interfaces
│   └── utils/            # Domain utilities
├── infrastructure/       # Platform infrastructure
│   ├── db/               # Database
│   ├── event_bus/        # Event bus infrastructure
│   ├── events/           # Event infrastructure
│   ├── io/               # File I/O
│   ├── lifecycle/        # Service lifecycle
│   ├── metrics/          # Metrics infrastructure
│   ├── observability/    # Observability infrastructure
│   ├── persistence/      # Persistence layer
│   └── security/         # Security infrastructure
├── runtime/              # Runtime entry point
├── runtime-dev/          # Development runtime (instruments)
└── tests/                # Platform-level tests (e2e, integration)
```

---

## 2. Architecture Pattern

The codebase implements **hexagonal / clean architecture** with strict dependency flow:

```
domain/  (innermost — zero external deps)
  ↑
infrastructure/  (DI container, event bus, observability, logging)
  ↑
application/  (OMS, orchestration composers)
  ↑
adapters/  (bridge legacy sync gateways → async CommonBrokerGateway port)
```

### Two Gateway Abstractions

| Gateway | Type | Direction | Era |
|---------|------|-----------|-----|
| `MarketDataGateway` | ABC, sync | Producer-side | Legacy (v1) |
| `CommonBrokerGateway` | Protocol, async | Consumer-side | Modern (v2) |

The `CommonBrokerGateway` is decomposed via **Interface Segregation Principle** into 8 narrow provider protocols:
1. `MarketDataProvider` — quote, ltp, depth
2. `PortfolioProvider` — positions, holdings, funds, trades
3. `OrderCommand` — place/cancel/modify orders
4. `OrderQuery` — orderbook, trade book
5. `OptionsProvider` — option chain, future chain, expiries
6. `FuturesProvider` — future chain
7. `MarketStatusProvider` — market status
8. `NewsProvider` — news feed

---

## 3. Module Inventory — brokers/common/

### 3.1 Domain Layer (`common/domain/`)

#### Entities (all frozen dataclasses — immutable)

| Entity | File | Key Fields | Purpose |
|--------|------|------------|---------|
| `Order` | `entities/order_lifecycle.py` | order_id, symbol, exchange, side, type, product, quantity, price, status, ... | Canonical order with status state machine |
| `Position` | `entities/position.py` | symbol, exchange, quantity, avg_price, ... | Position with state: FLAT→OPEN→REDUCING→CLOSED→REVERSED |
| `Trade` | `entities/trade.py` | trade_id, order_id, symbol, quantity, price, ... | Individual fill record |
| `Quote` | `entities/market.py` | ltp, open, high, low, close, volume, ... | Market quote snapshot |
| `MarketDepth` | `entities/market.py` | bids, asks (list of DepthLevel) | Order book depth |
| `Balance` | `entities/market.py` | available, used, total | Account balance |
| `Holding` | `entities/market.py` | symbol, quantity, avg_price, ... | CNC holdings |
| `OptionContract` | `entities/options.py` | strike, option_type, premium, ... | Option chain leg |
| `OptionChain` | `entities/options.py` | underlying, expiry, strikes | Full option chain |
| `FutureChain` | `entities/options.py` | underlying, expiry, price | Futures chain |
| `Alert` | `entities/alerts.py` | symbol, condition, threshold | Conditional alert |
| `Instrument` | `entities/instrument.py` | symbol, exchange, lot_size, tick_size, option_type, strike, expiry | Canonical instrument |
| `AccountInfo` | `entities/account.py` | broker_id, client_id, ... | Broker account metadata |

#### Enums

| Enum | Values | File |
|------|--------|------|
| `Side` | BUY, SELL | `enums.py` |
| `OrderType` | MARKET, LIMIT, SL, SL-M | `enums.py` |
| `ProductType` | INTRADAY, CNC, MARGIN, NORMAL | `enums.py` |
| `Validity` | DAY, IOC | `enums.py` |
| `OrderStatus` | 13 states (PENDING→OPEN→PARTIALLY_FILLED→FILLED/CANCELLED/REJECTED/...) | `enums.py` |
| `InstrumentType` | EQUITY, OPTIONS, FUTURES, INDEX, OTHER | `enums.py` |
| `ExchangeSegment` | NSE, BSE, NFO, MCX, BCD, CDS, IDX_I, ... | `market_enums.py` |

#### Domain Events (frozen dataclasses)

| Event | File |
|-------|------|
| `OrderPlacedEvent` | `events/types.py` |
| `OrderModifiedEvent` | `events/types.py` |
| `OrderCancelledEvent` | `events/types.py` |
| `OrderFilledEvent` | `events/types.py` |
| `PositionUpdatedEvent` | `events/types.py` |
| `TradeReportedEvent` | `events/types.py` |
| `StreamConnectedEvent` | `events/types.py` |
| `StreamDisconnectedEvent` | `events/types.py` |
| `StreamDataEvent` | `events/types.py` |
| `BrokerCapabilitiesChangedEvent` | `events/types.py` |

#### Ports (Protocol / ABC)

| Port | File | Purpose |
|------|------|---------|
| `MarketDataPort` | `ports/market_data.py` | LTP, quote, depth, history, search |
| `MarginProvider` | `ports/margin_provider.py` | Margin calculation |
| `RiskManager` | `ports/risk_manager.py` | Pre-trade risk checks |
| `EventPublisher` | `ports/event_publisher.py` | Publish domain events |
| `MetricsPort` | `ports/observability.py` | Metrics abstraction |
| `TracingPort` | `ports/observability.py` | Tracing abstraction |
| `StrategyEvaluator` | `ports/strategy_evaluator.py` | Strategy DSL evaluation |
| `OmsBacktestAdapter` | `ports/oms_backtest_adapter.py` | Backtesting OMS adapter |

#### Repositories (ABC)

| Repository | File | Purpose |
|------------|------|---------|
| `OrderRepository` | `repositories/` | Persist/retrieve orders |
| `PositionRepository` | `repositories/` | Persist/retrieve positions |

#### Key Domain Types

| Type | File | Purpose |
|------|------|---------|
| `GatewayResult[T]` | `result.py` | Monadic result (ok/err) |
| `InstrumentId` | `instrument_id.py` | Canonical instrument identifier |
| `HistoricalBar` | `historical.py` | OHLCV bar with provenance |
| `HistoricalSeries` | `historical.py` | Collection of bars |
| `DateRange` | `historical.py` | Time range for queries |
| `Gap` | `historical.py` | Missing data range |
| `DataProvenance` | `provenance.py` | Data lineage tracking |
| `TradingCosts` | `trading_costs.py` | STT/GST/fee calculations (Indian market) |
| `HealthState` / `HealthStatus` | `lifecycle_health.py` | Service health reporting |
| `StreamHealth` / `StreamState` | `stream_health.py` | WebSocket stream health |
| `ReconciliationResult` | `reconciliation.py` | Reconciliation outcomes |
| `StatusMapper` | `status_mapper.py` | Broker status normalization |
| `CapabilityMatrix` | `capabilities.py` | Broker capability declarations |
| `FieldMapping` | `field_mapping.py` | Broker field name mapping |
| `OrderRequest` / `OrderResponse` | `models/trading.py` | Order request/response with ok()/fail() |
| `BrokerFeature` / `FeatureSet` | `models/features.py` | Feature declarations |

#### Domain Constants

| File | Contents |
|------|----------|
| `constants/auth.py` | Token expiry, refresh thresholds |
| `constants/market.py` | Exchange hours, holiday calendars |
| `constants/exchanges.py` | Exchange code mappings |
| `constants/observability.py` | Metric names, alert thresholds |
| `constants/timeouts.py` | HTTP/WS timeout constants |
| `constants/defaults.py` | BATCH_MAX_WORKERS, etc. |
| `constants/resilience.py` | Circuit breaker thresholds, retry defaults |

### 3.2 Gateway Layer (`common/`)

| Module | Key Types | Purpose |
|--------|-----------|---------|
| `gateway.py` | `MarketDataGateway` (ABC) | Legacy sync gateway — 25+ methods |
| `broker_port.py` | `CommonBrokerGateway` (Protocol) | v2 async gateway — 8 ISP protocols |
| `gateway_interfaces.py` | Provider protocols | Extended ISP: GTT, CoverOrder, ConditionalAlert, SliceOrder, IdempotencyCache, Margin |
| `intelligent_market_gateway.py` | `IntelligentMarketDataGateway` | Smart routing gateway with quota |
| `infrastructure.py` | `BrokerInfrastructure` | DI container facade |
| `bootstrap.py` | `bootstrap_from_gateways()` | Composition root |
| `registry.py` | `BrokerRegistry` | Broker registration + lookup |
| `router.py` | `BrokerRouter` | 5 routing modes: fixed, priority_list, capability_match, quota_aware, latency_aware |
| `policy.py` | `SourceSelectionPolicy` | Routing policy configuration |
| `stream_orchestrator.py` | `StreamOrchestrator` | Multi-broker WebSocket lifecycle |
| `quota_scheduler.py` | `QuotaScheduler` | API quota coordination (5 priority levels) |
| `historical_coordinator.py` | `HistoricalDataCoordinator` | Federated multi-broker historical data |
| `connection_pool.py` | `ConnectionPoolManager` | HTTP session pool (singleton) |
| `submission_pipeline.py` | `build_payload()` | Shared order submission pipeline |
| `responses.py` | `OrderResponseFactory` | Order response construction |
| `instrument_resolver.py` | `generate_alternate_symbol_keys()` | Fuzzy instrument resolution (30+ variants) |
| `instruments.py` | `InstrumentRegistry` | Broker-agnostic instrument registry |
| `ssl_hardening.py` | `hardened_ssl_context()` | TLS 1.2+, strong ciphers, Mozilla Intermediate profile |

### 3.3 Authentication (`common/auth/`)

| Module | Key Types | Purpose |
|--------|-----------|---------|
| `token.py` | `TokenState`, `TokenStateStore`, `AuthManager`, `TotpGenerator` | Core auth: TOTP (HMAC-SHA1), token lifecycle |
| `token_policy.py` | `should_generate_token()` | Decision: when to generate (missing, expired, rejected, proactive) |
| `token_persistence.py` | `TokenPersistence` | JSON↔env reconciliation |
| `env_token.py` | `update_env_token()` | Atomic env file update (fcntl.flock, tmp, fsync, os.replace) |
| `jwt_expiry.py` | `JwtExpiry` | JWT exp claim parsing (no verification) |
| `credential_resolver.py` | `CredentialResolver` | Broker→.env file mapping |
| `credential_validator.py` | `CredentialValidator` | Broker-specific credential validation |
| `totp_cooldown.py` | `TotpCooldownGuard` | Per-broker TOTP rate limiting (dhan=120s, upstox=600s) |
| `environment_bootstrap.py` | `bootstrap_environment()` | Load broker .env files at startup |

### 3.4 Infrastructure (`common/infrastructure/`)

| Module | Key Types | Purpose |
|--------|-----------|---------|
| `event_bus/event_bus.py` | `EventBus` | In-process pub/sub with typed dispatch |
| `event_bus/dead_letter_queue.py` | `DeadLetterQueue` | Bounded FIFO for failed handlers |
| `event_bus/processed_trade_repository.py` | `ProcessedTradeRepository` | Idempotent trade processing with TTL cleanup |
| `lifecycle/lifecycle.py` | `LifecycleManager` | Service start/stop ordering, health snapshot |
| `metrics/registry.py` | `MetricsRegistry` | Counter/gauge/histogram/timer, Prometheus export |
| `observability/alerting.py` | `AlertingEngine` | Glob-pattern metric rules, 6 default rules |
| `observability/http_server.py` | `HttpObservabilityServer` | /healthz, /readyz, /metrics (aiohttp) |
| `observability/tracing.py` | `trace_operation()` | OpenTelemetry integration |
| `observability/event_metrics.py` | `EventMetrics` | Sliding-window rate counters |
| `io/parquet.py` | `atomic_parquet_write()` | Atomic file I/O (fcntl, tmp, fsync, replace) |
| `logging_config.py` | `configure_logging()` | 9 regex token redaction patterns, JSON + human formatters |
| `state_machine.py` | `StateMachine[T]` | Generic state machine (NOT thread-safe) |
| `time_service.py` | `TimeService`, `ExchangeCalendar` | NSE/BSE/MCX/NYSE/NASDAQ/LSE calendars |
| `health.py` | `HealthRegistry` | Health check registry |
| `event_log.py` | `BufferedEventLog` | JSONL append-only with day rotation, idempotency |

### 3.5 Extensions (`common/extensions/`)

| Extension | Protocol | Brokers | Purpose |
|-----------|----------|---------|---------|
| `DeepDepthProvider` | `deep_depth.py` | Dhan | 20/200-level depth |
| `EdisProvider` | `edis.py` | Dhan | CNC delivery sell auth (eDIS TPIN) |
| `ExpiredOptionsHistoryProvider` | `expired_options_history.py` | Dhan | Rolling option history |
| `ForeverOrderProvider` | `forever_order.py` | Dhan (native) + Upstox (GTT) | Single/OCO forever orders |
| `FundamentalsProvider` | `fundamentals.py` | Upstox | Company financials |
| `MarketIntelligenceProvider` | `market_intelligence.py` | Upstox | OI analysis, FII/DII, smartlists |
| `NativeSliceOrderProvider` | `native_slice_order.py` | Dhan | Server-side slice orders |
| `NewsProvider` | `news.py` | Upstox | Symbol/market news |
| `OptionGreeksStreamProvider` | `option_greeks_stream.py` | Upstox | Live BSM greeks streaming |
| `SuperOrderProvider` | `super_order.py` | Dhan | 3-leg super order |

### 3.6 Resilience (`common/resilience/`)

| Module | Key Types | Purpose |
|--------|-----------|---------|
| `retry.py` | `RetryExecutor` | Exponential backoff + jitter |
| `circuit_breaker.py` | `CircuitBreaker` | CLOSED→OPEN→HALF_OPEN state machine |
| `rate_limiter.py` | `TokenBucketRateLimiter` | Multi-bucket token bucket |
| `errors.py` | `TradeXV2Error` hierarchy | Full error taxonomy (15+ exception types) |

### 3.7 Error Hierarchy

```
TradeXV2Error
├── BrokerError
│   ├── AuthenticationError
│   ├── BrokerDegradedError
│   ├── BrokerUnavailableError
│   ├── OrderError
│   ├── DataError
│   └── StreamError / StreamAuthError / StreamStalenessError
├── CircuitBreakerOpenError
├── RateLimitError
├── RetryableError
├── NonRetryableError
├── ValidationError
├── ConfigError
├── NotSupportedError
├── InstrumentNotFoundError
├── ExitAllError
├── QuotaExhaustedError
├── RoutingError
├── HistoricalFetchError
├── MergeConflictError
└── UnsupportedGatewayOperationError
```

### 3.8 Services (`common/services/`)

| Module | Key Types | Purpose |
|--------|-----------|---------|
| `benchmark.py` | `BenchmarkSuite` | Compare broker gateways (latency, throughput) |
| `data_validator.py` | `DataQualityValidator` | Missing candles, duplicates, OI/volume anomalies |
| `download_engine.py` | `HistoricalDownloadEngine` | Chunked downloads, parallel, Parquet cache |
| `historical_data.py` | `HistoricalDataService` | Paginated fetch, gap detection, backfill |
| `instrument_registry.py` | `CanonicalInstrumentRegistry` | Hides broker-specific IDs |
| `production_readiness.py` | `ProductionReadinessChecker` | 13+ pre-flight checks |

---

## 4. Module Inventory — brokers/dhan/

*(Pending — background audit in progress)*

## 5. Module Inventory — brokers/upstox/

*(Pending — background audit in progress)*

## 6. Module Inventory — Platform Layer

*(Pending — background audit in progress)*

---

## 7. Dependency Graph

### Internal Dependency Direction

```
brokers/common/domain/          ← ZERO external deps (pure business logic)
brokers/common/infrastructure/  ← depends on domain/
brokers/common/resilience/      ← depends on domain/ (errors)
brokers/common/auth/            ← depends on domain/, infrastructure/
brokers/common/services/        ← depends on domain/, infrastructure/
brokers/common/ (top-level)     ← depends on all above
brokers/common/adapters/        ← depends on top-level (bridge layer)
brokers/dhan/                   ← depends on brokers/common/ (NEVER reverse)
brokers/upstox/                 ← depends on brokers/common/ (NEVER reverse)
brokers/paper/                  ← depends on brokers/common/ (NEVER reverse)
domain/ (platform)              ← ZERO external deps
infrastructure/ (platform)      ← depends on domain/
application/                    ← depends on domain/, infrastructure/
config/                         ← depends on domain/
```

### No circular dependencies detected in common/ layer.

### External Dependencies

| Dependency | Used By | Purpose |
|------------|---------|---------|
| `asyncio` | Throughout | Async runtime |
| `aiohttp` | Observability server | HTTP server |
| `requests` | HTTP clients | REST API calls |
| `websockets` | WebSocket clients | Live streaming |
| `pandas` | Historical data | DataFrame operations |
| `pyarrow` / `parquet` | Data persistence | Columnar storage |
| `protobuf` | Upstox WebSocket | v3 market feed decoding |
| `python-dotenv` | NOT used (custom loader) | .env parsing |
| `opentelemetry` | Tracing | Distributed tracing (optional) |
| `fcntl` | File locking | Atomic file operations (macOS/Linux) |

---

## 8. Runtime Lifecycle

### Initialization Order

```
1. bootstrap_environment()          — Load .env files
2. CredentialResolver.resolve()     — Map broker → credentials
3. CredentialValidator.validate()   — Verify credential completeness
4. TokenStateStore.load()           — Load token state
5. should_generate_token()          — Decide if login needed
6. AuthManager.acquire()            — Login if needed (TOTP + token)
7. BrokerGateway.connect()          — Establish REST session
8. ConnectionPoolManager.init()     — HTTP connection pool
9. LifecycleManager.start_all()     — Start background services
10. StreamOrchestrator.start()      — Start WebSocket streams
11. HttpObservabilityServer.start() — Start /healthz, /metrics
12. ProductionReadinessChecker.run() — Pre-flight checks
```

### Shutdown Order (reverse)

```
1. StreamOrchestrator.stop()        — Close WebSocket streams
2. LifecycleManager.stop_all()      — Stop background services (reverse order)
3. ConnectionPoolManager.close()    — Close HTTP sessions
4. BrokerGateway.close()            — Close broker connections
5. BufferedEventLog.flush()         — Flush pending events
```

---

## 9. Threading/Concurrency Model

| Pattern | Where | Mechanism |
|---------|-------|-----------|
| Correlation ID propagation | Throughout | `ContextVar` (async-safe) |
| Immutable entities | Domain layer | Frozen dataclasses |
| Thread-safe singletons | ConnectionPool, ProcessedTradeRepo, TotpCooldown | Double-checked locking / RLock |
| Parallel batch ops | Historical downloads, batch queries | `ThreadPoolExecutor` |
| Sync→async bridge | MarketDataGatewayAdapter | `asyncio.to_thread()` |
| Dedicated threads | HttpObservabilityServer | Own event loop |
| Daemon threads | TTL cleanup, stop enforcement | Background cleanup |
| State machine | Order/position lifecycle | NOT thread-safe by design |

---

## 10. Key Design Patterns Identified

| Pattern | Implementation |
|---------|---------------|
| Hexagonal Architecture | domain → infrastructure → application → adapters |
| Interface Segregation | 8 narrow provider protocols |
| Strategy | 5 routing modes in BrokerRouter |
| Adapter | MarketDataGatewayAdapter (sync→async bridge) |
| Registry | BrokerRegistry, ExtensionRegistry, InstrumentRegistry |
| Circuit Breaker | CLOSED→OPEN→HALF_OPEN |
| Token Bucket | Rate limiting with priority classes |
| Monadic Result | GatewayResult[T] (ok/err) |
| Dead Letter Queue | Failed event handler buffering |
| Composition Root | bootstrap.py |
| Factory | ExtensionBundle factory registry |
| Observer | EventBus with typed dispatch |
| State Machine | Order/position lifecycle |
| Facade | BrokerInfrastructure |
| Decorator | @routed() for quota acquisition |
