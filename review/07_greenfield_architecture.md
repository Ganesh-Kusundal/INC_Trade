# Phase 7 — Greenfield Architecture Blueprint

**Date:** 2026-07-02
**Status:** DRAFT — pending Phase 1-6 completion for broker-specific findings

---

## 1. Design Principles

1. **Behaviour preservation** — External observable behaviour MUST NOT change
2. **Clean Architecture** — Strict dependency direction: domain → application → adapters → infrastructure
3. **Domain-Driven Design** — Rich domain model with aggregates, entities, value objects, domain events
4. **Interface Segregation** — Narrow protocols, no god-interfaces
5. **Explicit over implicit** — No hidden behaviour in decorators or magic methods
6. **Test-driven** — Every module designed for testability from day one
7. **Async-first** — Native async, no sync→async bridging layer needed
8. **Observability built-in** — Metrics, tracing, structured logging from the start

---

## 2. Improvements Over Archived Implementation

| Archived Issue | Greenfield Improvement | Behaviour Change? |
|---------------|----------------------|-------------------|
| v1/v2 gateway duality | Single async gateway protocol | NO — internal only |
| `MarketDataGateway` god-interface (25+ methods) | ISP-decomposed protocols (already done in v2) | NO |
| Sync→async bridge (`async_compat.py`) | Native async throughout | NO — internal only |
| Hidden behaviour in `@routed()` decorator | Explicit method calls | NO — same quota logic |
| `generate_alternate_symbol_keys()` (30+ variants) | Clean symbol resolution with explicit strategies | NO — same resolution, cleaner code |
| Repeated atomic file I/O pattern | Single `AtomicFileWriter` utility | NO — same atomicity |
| `EventLog` deprecated but present | Removed | NO — dead code |
| `DataLakeGateway` stub raising errors | Not implemented until needed | NO — YAGNI |
| `StateMachine` not thread-safe | Thread-safe implementation or explicit single-thread owner | NO — same transitions |
| No vault integration | Optional vault secret backend | NO — same secrets, better storage |
| `services/` as utility trap | Split into focused domain services | NO — same logic, better cohesion |

**All improvements are architectural only. No externally observable broker behaviour changes.**

---

## 3. Proposed Package Structure

```
src/
├── domain/                          # Pure business logic (ZERO deps)
│   ├── entities/                    # Aggregates and entities
│   │   ├── order.py                 # Order aggregate root
│   │   ├── position.py              # Position aggregate root
│   │   ├── trade.py                 # Trade entity
│   │   ├── instrument.py            # Instrument entity
│   │   ├── quote.py                 # Quote value object
│   │   ├── depth.py                 # MarketDepth value object
│   │   ├── option_chain.py          # OptionChain aggregate
│   │   └── account.py              # AccountInfo value object
│   ├── enums/                       # All enumerations
│   │   ├── side.py
│   │   ├── order_type.py
│   │   ├── product_type.py
│   │   ├── order_status.py
│   │   ├── exchange.py
│   │   └── instrument_type.py
│   ├── events/                      # Domain events
│   │   ├── order_events.py
│   │   ├── position_events.py
│   │   └── stream_events.py
│   ├── ports/                       # Outbound ports (interfaces)
│   │   ├── order_executor.py        # Place/cancel/modify
│   │   ├── order_query.py           # Orderbook, tradebook
│   │   ├── market_data.py           # Quote, LTP, depth
│   │   ├── portfolio.py             # Positions, holdings, funds
│   │   ├── historical.py            # Historical bars
│   │   ├── instrument_source.py     # Instrument master
│   │   ├── token_store.py           # Token persistence
│   │   ├── event_publisher.py       # Domain event dispatch
│   │   └── clock.py                 # Time abstraction
│   ├── services/                    # Domain services
│   │   ├── order_state_machine.py
│   │   ├── position_tracker.py
│   │   ├── symbol_resolver.py
│   │   └── trading_costs.py
│   ├── value_objects/               # Value objects
│   │   ├── money.py
│   │   ├── quantity.py
│   │   ├── price.py
│   │   ├── instrument_id.py
│   │   ├── order_request.py
│   │   ├── order_response.py
│   │   └── historical_bar.py
│   └── exceptions.py                # Domain exceptions
│
├── application/                     # Application services (thin)
│   ├── order_service.py             # Order use cases
│   ├── market_data_service.py       # Market data use cases
│   ├── instrument_service.py        # Instrument management
│   ├── portfolio_service.py         # Portfolio queries
│   ├── historical_service.py        # Historical data use cases
│   └── auth_service.py              # Authentication use cases
│
├── infrastructure/                  # Infrastructure implementations
│   ├── broker/                      # Broker adapter framework
│   │   ├── gateway.py               # BrokerGateway protocol (composed)
│   │   ├── providers.py             # ISP provider protocols
│   │   ├── registry.py              # Broker registry
│   │   ├── router.py                # Request routing
│   │   ├── quota.py                 # API quota management
│   │   └── extensions.py            # Extension registry
│   ├── auth/                        # Authentication infrastructure
│   │   ├── token_manager.py
│   │   ├── totp.py
│   │   ├── jwt.py
│   │   ├── credential_store.py      # Env / Vault / File backends
│   │   └── session.py
│   ├── http/                        # HTTP client
│   │   ├── client.py                # Async HTTP client
│   │   ├── pool.py                  # Connection pool
│   │   ├── tls.py                   # TLS hardening
│   │   └── retry.py                 # HTTP retry policy
│   ├── websocket/                   # WebSocket infrastructure
│   │   ├── client.py                # Async WebSocket client
│   │   ├── reconnect.py             # Auto-reconnect
│   │   ├── heartbeat.py             # Heartbeat monitoring
│   │   └── subscription.py          # Subscription management
│   ├── persistence/                 # Data persistence
│   │   ├── instrument_cache.py      # Parquet-backed instrument cache
│   │   ├── historical_cache.py      # Parquet-backed historical cache
│   │   ├── token_store.py           # JSON/env token persistence
│   │   └── event_log.py             # JSONL event log
│   ├── resilience/                  # Resilience patterns
│   │   ├── circuit_breaker.py
│   │   ├── rate_limiter.py
│   │   ├── retry.py
│   │   └── bulkhead.py
│   ├── observability/               # Observability
│   │   ├── metrics.py               # Prometheus metrics
│   │   ├── tracing.py               # OpenTelemetry
│   │   ├── logging.py               # Structured logging + redaction
│   │   ├── health.py                # Health checks
│   │   └── alerting.py              # Alerting engine
│   ├── events/                      # Event infrastructure
│   │   ├── event_bus.py             # In-process event bus
│   │   └── dead_letter.py           # Dead letter queue
│   └── lifecycle/                   # Service lifecycle
│       ├── manager.py               # Start/stop ordering
│       └── readiness.py             # Readiness probes
│
├── adapters/                        # Broker-specific adapters
│   ├── dhan/                        # Dhan adapter
│   │   ├── gateway.py               # Implements BrokerGateway
│   │   ├── auth.py                  # Dhan auth flow
│   │   ├── orders.py                # OrderCommand implementation
│   │   ├── market_data.py           # MarketDataProvider implementation
│   │   ├── instruments.py           # InstrumentSource implementation
│   │   ├── websocket.py             # Dhan WebSocket
│   │   ├── mappers.py               # Dhan-specific data mappers
│   │   └── config.py                # Dhan endpoints, constants
│   ├── upstox/                      # Upstox adapter
│   │   ├── gateway.py
│   │   ├── auth.py                  # OAuth2 + PKCE
│   │   ├── orders.py
│   │   ├── market_data.py
│   │   ├── instruments.py
│   │   ├── websocket.py             # Protobuf v3 decoder
│   │   ├── mappers.py
│   │   └── config.py
│   └── paper/                       # Paper trading adapter
│       ├── gateway.py
│       ├── orders.py
│       ├── market_data.py
│       └── portfolio.py
│
├── runtime/                         # Composition root
│   ├── bootstrap.py                 # Application bootstrap
│   ├── container.py                 # DI container
│   └── config.py                    # Configuration loading
│
└── shared/                          # Cross-cutting utilities
    ├── atomic_io.py                 # Atomic file operations
    ├── correlation.py               # Correlation ID (ContextVar)
    ├── result.py                    # Result[T] monad
    └── types.py                     # Shared type aliases
```

---

## 4. Key Architectural Decisions

### ADR-001: Single Async Gateway Protocol

**Decision:** Use only the async `BrokerGateway` protocol (composed from ISP providers). Remove the sync `MarketDataGateway` ABC entirely.

**Rationale:** The archived code maintains two gateway abstractions (v1 sync, v2 async) with a bridge layer (`async_compat.py`, `MarketDataGatewayAdapter`). This adds complexity without value — all modern Python supports async natively.

**Behaviour impact:** NONE — internal refactoring only. External callers already use the async interface.

### ADR-002: Aggregate-Root State Machines

**Decision:** Embed state machine logic directly in aggregate roots (Order, Position) with explicit transition methods.

**Rationale:** The archived code has separate `StateMachine[T]` (not thread-safe) and entity state logic. Combining them ensures invariants are enforced at the aggregate boundary.

**Behaviour impact:** NONE — same transitions, better encapsulation.

### ADR-003: Explicit Routing (No Decorator Magic)

**Decision:** Replace `@routed()` decorator with explicit `router.route()` calls in application services.

**Rationale:** The decorator hides quota acquisition and routing, making the code harder to understand and test. Explicit calls are clearer.

**Behaviour impact:** NONE — same routing logic, same quota acquisition.

### ADR-004: Symbol Resolution Strategy Pattern

**Decision:** Replace `generate_alternate_symbol_keys()` (30+ fuzzy variants) with explicit `SymbolResolutionStrategy` implementations per exchange.

**Rationale:** The archived fuzzy matching is powerful but opaque. Strategy pattern makes each resolution approach testable and composable.

**Behaviour impact:** NONE — same resolution results, explicit strategies.

### ADR-005: Atomic I/O Utility

**Decision:** Single `AtomicFileWriter` context manager replacing all scattered fcntl+tmp+fsync+replace patterns.

**Rationale:** The archived code repeats this pattern in 3+ places (env_token.py, parquet.py, token_persistence.py). Single utility reduces duplication.

**Behaviour impact:** NONE — same atomicity guarantees.

### ADR-006: Credential Store Abstraction

**Decision:** `CredentialStore` port with `EnvFileStore`, `VaultStore`, `InMemoryStore` adapters.

**Rationale:** The archived code hardcodes .env file access. Abstracting enables vault integration without changing broker code.

**Behaviour impact:** NONE — default adapter uses same .env files.

### ADR-007: Thread-Safe State Machines

**Decision:** Either make state machines thread-safe (with RLock) or explicitly document single-thread ownership and enforce via lifecycle manager.

**Rationale:** The archived `StateMachine[T]` is explicitly NOT thread-safe, which is a latent bug in concurrent scenarios.

**Behaviour impact:** NONE — same transitions, safer concurrency.

---

## 5. Dependency Rules

```
domain/          → NOTHING (zero imports from other packages)
application/     → domain/ only
infrastructure/  → domain/, application/ (for port implementations)
adapters/        → domain/, application/, infrastructure/broker/
runtime/         → ALL (composition root only)
shared/          → NOTHING (pure utilities, no domain knowledge)
```

**Enforcement:** Import linter rules in CI. No circular dependencies permitted.

---

## 6. Testing Strategy

| Layer | Test Type | Coverage Target | Framework |
|-------|-----------|----------------|-----------|
| Domain | Unit | 100% | pytest |
| Application | Unit + Integration | 95% | pytest + mocks |
| Infrastructure | Integration | 90% | pytest + testcontainers |
| Adapters | Contract | 100% of port methods | pytest + archived contract suites |
| Runtime | E2E | Critical paths | pytest |
| Resilience | Chaos | Failure modes | pytest + fault injection |
| Performance | Load/Bench | Latency targets | pytest-benchmark |

### Parity Oracle

The archived test suite becomes the **parity oracle**:
- All archived contract tests must pass against the new implementation
- All archived integration tests must pass
- Regression tests are ported first

---

## 7. Migration Strategy

**Strangler Fig pattern** — not applicable since this is greenfield.

Instead: **Parallel validation**
1. Build new implementation module by module
2. Run archived + new side-by-side for each module
3. Compare outputs for identical inputs
4. Archived test suite as acceptance criteria
5. Switch over when parity is verified

---

*This blueprint will be refined as Phase 1-6 audits complete with broker-specific findings.*
