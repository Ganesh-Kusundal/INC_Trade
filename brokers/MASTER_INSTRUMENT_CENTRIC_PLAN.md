# Master Plan: Instrument-Centric Broker Platform Architecture

## Architecture Blueprint — Elite Quantitative Engineering Review Board

---

# Current Codebase Assessment

## What Exists (Already Built)

### ✅ Market Context (Instrument-Centric Foundation)
| File | Status | Lines |
|------|--------|-------|
| `market/instrument.py` | ✅ Complete | `Instrument` domain entity with type detection, validation |
| `market/instrument_registry.py` | ✅ Complete | Thread-safe, one-instance-per-key guarantee |
| `market/quote_state.py` | ✅ Complete | Mutable state with snapshot, staleness, spread, VWAP |
| `market/depth_state.py` | ✅ Complete | Mutable depth, best bid/ask, spread |
| `market/context.py` | ✅ Complete | `MarketDataContext` + `InstrumentHandle` delegation |
| `market/subscription_manager.py` | 🔴 **UNTESTED** | Created but no tests, not wired into `connect()` |

### ✅ Trading Context (Account-Centric)
| File | Status | Lines |
|------|--------|-------|
| `trading/account.py` | ✅ Complete | `Account` entity, `AccountType`, `AccountStatus` enums |
| `trading/account_registry.py` | ✅ Complete | Thread-safe, one-instance-per-id |
| `trading/context.py` | ✅ Complete | `TradingContext` + `AccountHandle` with order delegation |

### ✅ Subscription Manager & Streaming Router (Phase 5 — COMPLETE)
| File | Status | Lines |
|------|--------|-------|
| `market/subscription_manager.py` | ✅ Tested | `SubscriptionState` + `SubscriptionManager` with ref counting, callbacks, thread safety |
| `market/streaming_router.py` | ✅ Complete | `StreamingRouter` with multi-backend, priority selection, fallback, reconnect |
| `market/context.py` | ✅ Updated | Accepts `subscription_manager` + `streaming_router`, subscribe/unsubscribe routes through manager |
| `brokers/__init__.py` | ✅ Wired | `connect()` creates `SubscriptionManager` wrapping gateway's streaming adapter |
| `tests/unit/test_subscription_manager.py` | ✅ 27 tests | State transitions, ref counting, callbacks, thread safety, clear |
| `tests/unit/test_streaming_router.py` | ✅ 18 tests | Backend selection, routing, fallback, lifecycle, clear |

### ✅ Historical Data Router (Cache-First Architecture)
| File | Status | Lines |
|------|--------|-------|
| `ports/cache_port.py` | ✅ Complete | `CachePort` Protocol |
| `ports/historical_provider.py` | ✅ Complete | `HistoricalProvider` Protocol |
| `infrastructure/cache/memory_cache.py` | ✅ Complete | LRU, TTL, stale-while-revalidate, thread-safe |
| `services/historical_router.py` | ✅ Complete | Cache-first, multi-provider, merge, batch |
| `services/historical_service.py` | ✅ Complete | Uses router when available, falls back to port |
| `domain/cache_policy.py` | ✅ Complete | TTL constants, `policy_for_resolution()` |
| Tests | ✅ 21+20=41 tests | `test_memory_cache.py` + `test_historical_router.py` |

### ✅ Unified Capability Model
| File | Status |
|------|--------|
| `domain/capabilities.py` | ✅ `BrokerCapabilities` with 30+ `supports_*` fields |
| `domain/constants/capabilities.py` | ✅ `FEATURE_*` constants |
| All adapters return `BrokerCapabilities` | ✅ Migrated from old Protocol |
| `services/capability_discovery.py` | ✅ Uses `supports()` |
| `services/broker_router.py` | ✅ Uses `supports()` |
| Tests | ✅ Contract tests + architecture tests |

### ✅ Adapter Implementations
| Broker | Files | Status |
|--------|-------|--------|
| Dhan | 42 files | ✅ Full implementation |
| Upstox | 23 files | ✅ Full implementation |
| Paper | 3 files | ✅ Basic implementation |

### ✅ Architecture Guardrails (59 tests)
| Rule | Tests | Status |
|------|-------|--------|
| Boundary rules per layer | 10 params | ✅ |
| Ports are `@runtime_checkable` Protocol | 22 ports | ✅ |
| Exception hierarchy | 2 tests | ✅ |
| Market ↔ Trading isolation | 2 tests | ✅ |
| No global singletons | 1 test | ✅ |
| No `hasattr()` on gateway | 1 test | ✅ |
| No broker DTO leakage | 2 tests | ✅ |
| One Instrument per key | 5 tests | ✅ |
| Trading not import services/infra | 3 tests | ✅ |
| Capability constants | 2 tests | ✅ |
| Adapters not import services | 1 test | ✅ |
| Service constructor arg limit | 1 test | ✅ |
| No duplicate `__all__` entries | 1 test | ✅ |
| Others | 6 tests | ✅ |

## What Is Missing (Needs Building)

### ✅ Phase 5: Subscription Manager & Streaming Router **(COMPLETE)**
- [x] `market/streaming_router.py` — Created with multi-backend, priority, fallback
- [x] `tests/unit/test_subscription_manager.py` — 27 tests covering state machine, ref counting, callbacks, thread safety
- [x] `tests/unit/test_streaming_router.py` — 18 tests covering backend selection, routing, fallback, lifecycle
- [x] Integration into `MarketDataContext` — subscribe/unsubscribe routes through SubscriptionManager
- [x] Integration into `brokers/__init__.py connect()` — wired for all brokers
- [x] Auto-update `QuoteState` on streaming ticks
- [x] `InstrumentHandle.quote_state()` method
- [x] `SimpleSubscriptionHandle` for new path
- [x] Backward compat maintained
- [x] No architecture boundary violations (market/ layer does not import services/)

### ⬜ Phase 6: OMS & Execution Router
- [ ] `trading/oms.py` — DOES NOT EXIST
- [ ] `trading/execution_router.py` — DOES NOT EXIST
- [ ] Order lifecycle state machine
- [ ] Execution routing (multi-broker order placement)
- [ ] Trade reconciliation

### ⬜ Phase 7: Extension Isolation
- [ ] Dhan extensions (ForeverOrder, SuperOrder, KillSwitch, SliceOrder, Margin)
- [ ] Upstox extensions (GTT, News)
- [ ] Move extension providers OUT of `ports/capabilities.py`
- [ ] Plugin-based extension loader

### ⬜ Phase 8: Event Bus Integration
- [ ] Typed events (not just `dict[str, Any]` payload)
- [ ] Market → Trading event wiring
- [ ] Streaming → QuoteState auto-update via events
- [ ] `DomainEvent` type hierarchy
- [ ] Event ordering guarantees

### ⬜ Phase 9: Gateway Deprecation
- [ ] `BrokerFacade` deprecation warnings
- [ ] Remove `create_broker()` → rename to `connect()`
- [ ] Remove `_underlying_gateway` compat path
- [ ] Clean up `BrokerGateway` Protocol (reduce surface area)

### ⬜ Phase 10: Replay Engine & Paper Advanced
- [ ] `market/replay/` directory
- [ ] Replay provider for `HistoricalRouter`
- [ ] Paper gateway advanced (fills, slippage, order book)
- [ ] `HistoricalProvider` for CSV files

### ⬜ Phase 11: Market Router (Multi-Provider)
- [ ] `market/market_router.py`
- [ ] Multi-provider quote/depth routing
- [ ] Provider selection strategy
- [ ] Cache-first for market data

### ⬜ Phase 12: Backtesting & Scanner
- [ ] `trading/backtesting/` directory
- [ ] Backtesting engine using replay data
- [ ] `market/scanner/` directory
- [ ] Scanner service (never knows brokers)

---

# Architecture Principles

## 1. Instrument-Centric Design

```
Client Code
    │
    ▼
Instrument  ←── Primary domain abstraction
    │
    ├── .quote()           → routes to market service
    ├── .depth()           → routes to market service
    ├── .ohlcv()           → routes to historical router
    ├── .option_chain()    → routes to options service
    ├── .subscribe()       → routes to subscription manager
    └── .analytics()       → routes to analytics service
```

**Rule**: Instrument NEVER knows broker APIs. It delegates to domain services.

## 2. Three Bounded Contexts

```
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  Market Data    │   │    Trading      │   │  Infrastructure │
│  Context        │   │    Context      │   │  Context        │
├─────────────────┤   ├─────────────────┤   ├─────────────────┤
│ Instrument      │   │ Account         │   │ Cache           │
│ QuoteState      │   │ Order           │   │ HTTP Client     │
│ DepthState      │   │ Portfolio       │   │ Auth Tokens     │
│ OptionChain     │   │ Positions       │   │ Event Bus       │
│ HistoricalData  │   │ Risk            │   │ Metrics         │
│ Streaming       │   │ OMS             │   │ Config          │
└─────────────────┘   └─────────────────┘   └─────────────────┘
        ║                      ║                     ║
        ║       NEVER import    ║         NEVER       ║
        ║    market → trading   ║      import from    ║
        ║    trading → market   ║      adapters       ║
        ║                      ║                     ║
        ▼                      ▼                     ▼
┌──────────────────────────────────────────────────────────┐
│                  Domain Layer (Pure)                      │
│  Entities, Value Objects, Enums, Exceptions, Events       │
│  Imports: nothing outside brokers.domain                  │
└──────────────────────────────────────────────────────────┘
```

## 3. Dependency Direction

```
domain  →  ports  →  services  →  infrastructure  →  adapters
  │          │           │               │                │
  │          │           │               │                │
  └──────────┴───────────┴───────────────┴────────────────┘
                     market/ (separate)
                     trading/ (separate)
```

**Enforced Rules**:
- `market/` → only `domain`, `ports`, `market`
- `trading/` → only `domain`, `ports`, `trading`
- `services/` → only `domain`, `ports`, `services`, `utils`
- `infrastructure/` → `domain`, `ports`, `infrastructure`, `config`, `core`, `resilience`
- `adapters/` → `domain`, `ports`, `infrastructure` (never `services/`)
- `adapters/` → never expose broker DTOs outside

---

# Phase Definitions with Full Checklists

---

## Phase 5: Subscription Manager & Streaming Router

**Goal**: Centralize streaming subscription lifecycle with deduplication, reference counting, and auto-unsubscribe. Wire into MarketDataContext so streaming ticks auto-update QuoteState.

**Dependencies**: None (self-contained within market/ layer)

**Estimated Tests**: 25-30 new

### Task 5.1: Create `market/streaming_router.py`

| # | Item | Type | Done |
|---|------|------|------|
| 5.1.1 | `StreamingRouter` class with `add_backend()`, `remove_backend()` | Create | ✅ |
| 5.1.2 | Route `subscribe()` to correct backend (WebSocket / polling) | Implement | ✅ |
| 5.1.3 | Route `unsubscribe()` to correct backend | Implement | ✅ |
| 5.1.4 | Support fallback: if WebSocket fails, fall back to polling | Implement | ✅ |
| 5.1.5 | Reconnect strategy delegation (via backend adapter) | Implement | ✅ |
| 5.1.6 | `disconnect_all()` lifecycle | Implement | ✅ |
| 5.1.7 | `active_subscriptions` query property | Implement | ✅ |
| 5.1.8 | Architecture: `market/` layer only — no `services/` imports | Verify | ✅ |
| 5.1.9 | Docstrings and module-level doc | Document | ✅ |

### Task 5.2: Test `SubscriptionManager`

| # | Item | Type | Done |
|---|------|------|------|
| 5.2.1 | `test_subscription_manager.py` file with `TestSubscriptionManager` class | Create | ✅ |
| 5.2.2 | `test_ref_counting_first_subscriber_actually_subscribes` | Test | ✅ |
| 5.2.3 | `test_ref_counting_second_subscriber_does_not_resubscribe` | Test | ✅ |
| 5.2.4 | `test_ref_counting_last_unsubscriber_actually_unsubscribes` | Test | ✅ |
| 5.2.5 | `test_callback_registration_and_invocation` | Test | ✅ |
| 5.2.6 | `test_callback_removal_on_unsubscribe` | Test | ✅ |
| 5.2.7 | `test_dispatch_tick_to_multiple_callbacks` | Test | ✅ |
| 5.2.8 | `test_thread_safety_concurrent_subscribe` | Test | ✅ |
| 5.2.9 | `test_state_transitions_inactive_to_active` | Test | ✅ |
| 5.2.10 | `test_state_transitions_active_to_inactive` | Test | ✅ |
| 5.2.11 | `test_unsubscribe_unknown_key_does_not_raise` | Test | ✅ |
| 5.2.12 | `test_clear_removes_all_and_unsubscribes_all` | Test | ✅ |
| 5.2.13 | `test_ref_count_query_methods` | Test | ✅ |
| 5.2.14 | `test_callback_error_does_not_crash_dispatcher` | Test | ✅ |
| 5.2.15 | `test_is_subscribed_returns_false_for_unknown_key` | Test | ✅ |
| 5.2.16 | `test_thread_safety_concurrent_subscribe_unsubscribe` | Test | ✅ |
| 5.2.17 | `test_dispatch_tick_to_correct_key_only` | Test | ✅ |
| 5.2.18 | `test_subscribe_multiple_keys_independent` | Test | ✅ |
| 5.2.19 | `TestSubscriptionState` — 8 state machine tests | Test | ✅ |

### Task 5.3: Test `StreamingRouter`

| # | Item | Type | Done |
|---|------|------|------|
| 5.3.1 | `test_streaming_router.py` file | Create | ✅ |
| 5.3.2 | `test_route_subscribe_to_correct_adapter` | Test | ✅ |
| 5.3.3 | `test_route_unsubscribe_to_correct_adapter` | Test | ✅ |
| 5.3.4 | `test_polling_fallback_when_websocket_not_available` | Test | ✅ |
| 5.3.5 | `test_fallback_on_adapter_failure` | Test | ✅ |
| 5.3.6 | `test_active_subscriptions_after_route` | Test | ✅ |
| 5.3.7 | `test_remove_backend_by_name` | Test | ✅ |
| 5.3.8 | `test_add_backend_sorted_by_priority` | Test | ✅ |
| 5.3.9 | `test_disconnect_all_disconnects_all_backends` | Test | ✅ |
| 5.3.10 | `test_clear_removes_all_backends` | Test | ✅ |
| 5.3.11 | `test_unsubscribe_cleans_up_all_backends` | Test | ✅ |
| 5.3.12 | `test_fallback_raises_when_no_fallback` | Test | ✅ |
| 5.3.13 | `test_route_subscribe_raises_when_no_backend` | Test | ✅ |

### Task 5.4: Integrate into `MarketDataContext`

| # | Item | Type | Done |
|---|------|------|------|
| 5.4.1 | `MarketDataContext.__init__` accepts `subscription_manager` param | Modify | ✅ |
| 5.4.2 | `MarketDataContext.subscribe()` uses `SubscriptionManager` | Modify | ✅ |
| 5.4.3 | Auto-update `QuoteState` on tick via callback | Implement | ✅ |
| 5.4.4 | `InstrumentHandle.quote_state()` method | Implement | ✅ |
| 5.4.5 | Backward compat: old subscribe path still works without SubscriptionManager | Verify | ✅ |
| 5.4.6 | `MarketDataContext.unsubscribe()` uses `SubscriptionManager` | Modify | ✅ |

### Task 5.5: Wire in `brokers/__init__.py connect()`

| # | Item | Type | Done |
|---|------|------|------|
| 5.5.1 | `connect()` creates `SubscriptionManager` wrapping gateway's streaming adapter | Modify | ✅ |
| 5.5.2 | Also create `StreamingRouter` with WebSocket backend | Modify | ✅ |
| 5.5.3 | Pass both to `MarketDataContext` | Modify | ✅ |

### Task 5.6: Integration Tests

| # | Item | Type | Done |
|---|------|------|------|
| 5.6.1 | `MarketDataContext` integration verified (53 existing context tests pass) | Verify | ✅ |
| 5.6.2 | QuoteState auto-update via callback in `subscribe()` | Implement | ✅ |
| 5.6.3 | `InstrumentHandle.quote_state()` returns auto-updated state | Implement | ✅ |

### Task 5.7: Run Full Suite & Verify

| # | Item | Type | Done |
|---|------|------|------|
| 5.7.1 | Run `python -m pytest tests/unit/ tests/contract/ -v -q` | Verify | ✅ |
| 5.7.2 | **No regressions** — count matches or exceeds 1,471 | Verify | ✅ |
| 5.7.3 | Run `python -m pytest tests/unit/test_architecture.py -m architecture -v` (59 pass) | Verify | ✅ |
| 5.7.4 | Run `python -m pytest tests/contract/ -v` (contracts pass) | Verify | ✅ |
| 5.7.5 | Run with coverage: `--cov=brokers` | Verify | ⬜ |

### ✅ Definition of Done for Phase 5 — COMPLETE
- [x] `SubscriptionManager` + `StreamingRouter` fully tested (45 tests — 27 + 18)
- [x] Integrated into `MarketDataContext` (subscribe/unsubscribe routed through manager)
- [x] Wired in `brokers/__init__.py connect()` for all brokers
- [x] Streaming ticks auto-update `QuoteState` via callback
- [x] `InstrumentHandle.quote_state()` returns auto-updated state
- [x] Backward compat maintained (old `subscribe()` path still works without manager)
- [x] **0 regressions** — full suite passes
- [x] Architecture tests pass (all 59)
- [x] `market/` layer does NOT import `services/` (architecture rule enforced)
- [x] `SimpleSubscriptionHandle` for new path cleanup

---

## Phase 6: OMS & Execution Router

**Goal**: Create a proper Order Management System within the Trading bounded context. Orders belong to Accounts, never to Instruments. Execution routing supports multi-broker placement.

**Dependencies**: Phase 5 complete

**Estimated Tests**: 30-35 new

### Task 6.1: Create `trading/oms.py`

| # | Item | Type | Done |
|---|------|------|------|
| 6.1.1 | `OrderManagementSystem` class | Create | ⬜ |
| 6.1.2 | Order lifecycle state machine validation | Implement | ⬜ |
| 6.1.3 | Order repository (in-memory) | Implement | ⬜ |
| 6.1.4 | Idempotency check (prevent duplicate placement) | Implement | ⬜ |
| 6.1.5 | Kill switch check (block when disabled) | Implement | ⬜ |
| 6.1.6 | Validation delegation (to domain validators) | Implement | ⬜ |
| 6.1.7 | Order event publishing (OrderPlaced, OrderFilled, OrderRejected) | Implement | ⬜ |
| 6.1.8 | `trading/oms.py` — only imports domain, ports, trading | Verify | ⬜ |

### Task 6.2: Create `trading/execution_router.py`

| # | Item | Type | Done |
|---|------|------|------|
| 6.2.1 | `ExecutionRouter` class | Create | ⬜ |
| 6.2.2 | Register execution adapters (one per broker) | Implement | ⬜ |
| 6.2.3 | Route by account's broker_id | Implement | ⬜ |
| 6.2.4 | Fallback routing (primary → secondary) | Implement | ⬜ |
| 6.2.5 | Capability-based routing (e.g., bracket orders → Dhan) | Implement | ⬜ |
| 6.2.6 | `trading/execution_router.py` — only imports domain, ports, trading | Verify | ⬜ |

### Task 6.3: Create `trading/order_repository.py`

| # | Item | Type | Done |
|---|------|------|------|
| 6.3.1 | In-memory order repository with thread safety | Create | ⬜ |
| 6.3.2 | `save()`, `get()`, `get_by_account()`, `get_active()` | Implement | ⬜ |
| 6.3.3 | `update_status()` with state machine validation | Implement | ⬜ |

### Task 6.4: Test OMS

| # | Item | Type | Done |
|---|------|------|------|
| 6.4.1 | `test_oms_place_order_validates` | Test | ⬜ |
| 6.4.2 | `test_oms_idempotency_prevents_duplicates` | Test | ⬜ |
| 6.4.3 | `test_oms_kill_switch_blocks_orders` | Test | ⬜ |
| 6.4.4 | `test_oms_lifecycle_state_transitions` | Test | ⬜ |
| 6.4.5 | `test_oms_events_published_on_state_change` | Test | ⬜ |
| 6.4.6 | `test_oms_get_active_orders_for_account` | Test | ⬜ |
| 6.4.7 | `test_oms_repository_thread_safety` | Test | ⬜ |
| 6.4.8 | `test_oms_rejects_invalid_transition` | Test | ⬜ |

### Task 6.5: Test Execution Router

| # | Item | Type | Done |
|---|------|------|------|
| 6.5.1 | `test_execution_router_routes_to_correct_adapter` | Test | ⬜ |
| 6.5.2 | `test_execution_router_fallback_on_failure` | Test | ⬜ |
| 6.5.3 | `test_execution_router_capability_routing` | Test | ⬜ |
| 6.5.4 | `test_execution_router_unknown_account_raises` | Test | ⬜ |

### Task 6.6: Integrate into `TradingContext`

| # | Item | Type | Done |
|---|------|------|------|
| 6.6.1 | `TradingContext` accepts `oms` parameter | Modify | ⬜ |
| 6.6.2 | `AccountHandle.place_order()` delegates to OMS | Modify | ⬜ |
| 6.6.3 | OMS → ExecutionRouter → adapter chain | Wire | ⬜ |
| 6.6.4 | Wire in `brokers/__init__.py connect()` | Modify | ⬜ |

### Definition of Done for Phase 6
- [ ] OMS with lifecycle, idempotency, kill switch, validation
- [ ] ExecutionRouter with multi-broker routing and fallback
- [ ] OrderRepository with thread safety
- [ ] 18-22 new tests
- [ ] Integrated into TradingContext
- [ ] **0 regressions**
- [ ] `trading/` layer does NOT import `services/`, `infrastructure/`, `adapters/`

---

## Phase 7: Extension Isolation

**Goal**: Move broker-specific extension providers OUT of `ports/capabilities.py` and into their respective adapter directories. Create a plugin-based extension loader. Extensions become discoverable and type-safe.

**Dependencies**: None

**Estimated Tests**: 15-20 new

### Task 7.1: Audit Current Extensions

| # | Item | Type | Done |
|---|------|------|------|
| 7.1.1 | List all extension providers in `ports/capabilities.py` | Audit | ⬜ |
| 7.1.2 | Identify which are Dhan-specific vs generic | Audit | ⬜ |
| 7.1.3 | Identify which are Upstox-specific vs generic | Audit | ⬜ |

### Task 7.2: Create Adapter-Specific Extension Modules

| # | Item | Type | Done |
|---|------|------|------|
| 7.2.1 | `adapters/dhan/extensions/__init__.py` with `DhanExtensions` | Create | ⬜ |
| 7.2.2 | Move `ForeverOrderProvider` to `adapters/dhan/extensions/` | Move | ⬜ |
| 7.2.3 | Move `SuperOrderProvider` to `adapters/dhan/extensions/` | Move | ⬜ |
| 7.2.4 | Move `KillSwitchProvider` to `adapters/dhan/extensions/` | Move | ⬜ |
| 7.2.5 | Move `SliceOrderProvider` to `adapters/dhan/extensions/` | Move | ⬜ |
| 7.2.6 | Move `MarginProvider` to `adapters/dhan/extensions/` | Move | ⬜ |
| 7.2.7 | `adapters/upstox/extensions/__init__.py` with `UpstoxExtensions` | Create | ⬜ |
| 7.2.8 | Move `GTTProvider` to `adapters/upstox/extensions/` | Move | ⬜ |
| 7.2.9 | Move `NewsProvider` to `adapters/upstox/extensions/` | Move | ⬜ |

### Task 7.3: Create Plugin Loader

| # | Item | Type | Done |
|---|------|------|------|
| 7.3.1 | `brokers/extensions/` directory | Create | ⬜ |
| 7.3.2 | `brokers/extensions/loader.py` — discovers extensions by convention | Create | ⬜ |
| 7.3.3 | `brokers/extensions/registry.py` — typed extension registry | Create | ⬜ |
| 7.3.4 | Extension base class / Protocol | Create | ⬜ |

### Task 7.4: Clean Up `ports/capabilities.py`

| # | Item | Type | Done |
|---|------|------|------|
| 7.4.1 | Remove all broker-specific extension providers | Remove | ⬜ |
| 7.4.2 | Keep only truly generic Protocols | Keep | ⬜ |
| 7.4.3 | Update `ports/__init__.py` exports | Modify | ⬜ |

### Task 7.5: Update `brokers/__init__.py connect()`

| # | Item | Type | Done |
|---|------|------|------|
| 7.5.1 | Replace `DictExtensionRegistry` with plugin loader | Modify | ⬜ |
| 7.5.2 | Remove inline `registry.register()` calls | Modify | ⬜ |
| 7.5.3 | Extensions auto-discovered from adapter modules | Implement | ⬜ |

### Task 7.6: Tests

| # | Item | Type | Done |
|---|------|------|------|
| 7.6.1 | `test_extension_loader_discovery` | Test | ⬜ |
| 7.6.2 | `test_extension_loader_typed_retrieval` | Test | ⬜ |
| 7.6.3 | `test_dhan_extensions_isolated` | Test | ⬜ |
| 7.6.4 | `test_upstox_extensions_isolated` | Test | ⬜ |
| 7.6.5 | `test_no_broker_extensions_in_ports` | Test | ⬜ |
| 7.6.6 | Update contract tests for extension isolation | Modify | ⬜ |
| 7.6.7 | Architecture test: no adapter imports from ports.capabilities extension classes | Create | ⬜ |

### Definition of Done for Phase 7
- [ ] All broker-specific extensions moved to adapter directories
- [ ] Plugin loader discovers extensions by convention
- [ ] `ports/capabilities.py` has zero broker-specific types
- [ ] 8-10 new tests
- [ ] **0 regressions**

---

## Phase 8: Event Bus Integration

**Goal**: Upgrade the event bus from `dict[str, Any]` to typed domain events. Wire Market → Trading events. Streaming → QuoteState auto-update via events.

**Dependencies**: Phase 5, Phase 6

**Estimated Tests**: 20-25 new

### Task 8.1: Typed Event Hierarchy

| # | Item | Type | Done |
|---|------|------|------|
| 8.1.1 | Define `MarketEvent(QuoteUpdated, DepthUpdated, TickReceived)` in `domain/events.py` | Create | ⬜ |
| 8.1.2 | Define `TradingEvent(OrderPlaced, OrderFilled, OrderRejected, OrderModified)` | Create | ⬜ |
| 8.1.3 | Define `AccountEvent(PositionUpdated, PortfolioUpdated, FundsChanged)` | Create | ⬜ |
| 8.1.4 | Define `ConnectionEvent(Connected, Disconnected, TokenExpired, TokenRefreshed)` | Create | ⬜ |
| 8.1.5 | All events are frozen dataclasses inheriting from `DomainEvent` | Verify | ⬜ |

### Task 8.2: Upgrade Event Bus

| # | Item | Type | Done |
|---|------|------|------|
| 8.2.1 | `EventBus` supports typed event subscription | Modify | ⬜ |
| 8.2.2 | Event ordering guarantee (per-instrument ordering) | Implement | ⬜ |
| 8.2.3 | Thread-safe publish with error isolation | Verify | ⬜ |
| 8.2.4 | Event bus metrics (events published, subscribers) | Implement | ⬜ |

### Task 8.3: Wire Market Events

| # | Item | Type | Done |
|---|------|------|------|
| 8.3.1 | `SubscriptionManager` publishes `QuoteUpdated` on tick | Modify | ⬜ |
| 8.3.2 | `SubscriptionManager` publishes `DepthUpdated` on depth tick | Modify | ⬜ |
| 8.3.3 | `QuoteState` subscribes to `QuoteUpdated` to auto-update | Wire | ⬜ |
| 8.3.4 | `DepthState` subscribes to `DepthUpdated` to auto-update | Wire | ⬜ |

### Task 8.4: Wire Trading Events

| # | Item | Type | Done |
|---|------|------|------|
| 8.4.1 | `AccountHandle.place_order()` publishes `OrderPlaced` | Modify | ⬜ |
| 8.4.2 | OMS publishes `OrderFilled`, `OrderRejected` on status change | Modify | ⬜ |
| 8.4.3 | Position updates publish `PositionUpdated` | Modify | ⬜ |

### Task 8.5: Tests

| # | Item | Type | Done |
|---|------|------|------|
| 8.5.1 | `test_typed_event_creation` | Test | ⬜ |
| 8.5.2 | `test_event_bus_subscription_and_publish` | Test | ⬜ |
| 8.5.3 | `test_event_ordering_guarantee` | Test | ⬜ |
| 8.5.4 | `test_quote_state_auto_update_via_event` | Test | ⬜ |
| 8.5.5 | `test_depth_state_auto_update_via_event` | Test | ⬜ |
| 8.5.6 | `test_event_bus_thread_safety` | Test | ⬜ |
| 8.5.7 | `test_event_bus_error_isolation` | Test | ⬜ |
| 8.5.8 | `test_domain_events_frozen_immutable` | Test | ⬜ |

### Definition of Done for Phase 8
- [ ] Typed event hierarchy (MarketEvent, TradingEvent, AccountEvent, ConnectionEvent)
- [ ] Event bus upgraded with ordering guarantees
- [ ] Streaming → QuoteState/DepthState auto-update via events
- [ ] Trading operations publish events
- [ ] 12-15 new tests
- [ ] **0 regressions**

---

## Phase 9: Gateway Deprecation

**Goal**: Safely deprecate the old `BrokerGateway`-centric API. `create_broker()` becomes an alias for `connect()`. `BrokerFacade` methods emit deprecation warnings. Remove `_underlying_gateway` compat path.

**Dependencies**: Phase 5, 6, 7, 8 (all new code uses session API)

**Estimated Tests**: 10-15 new

### Task 9.1: Deprecate `create_broker()`

| # | Item | Type | Done |
|---|------|------|------|
| 9.1.1 | `create_broker()` body = `return connect(...)` | Modify | ⬜ |
| 9.1.2 | `create_broker()` emits `DeprecationWarning` | Add | ⬜ |
| 9.1.3 | Add `warnings.warn()` with migration message | Add | ⬜ |

### Task 9.2: Deprecate `BrokerFacade`

| # | Item | Type | Done |
|---|------|------|------|
| 9.2.1 | All `BrokerFacade` public methods emit `DeprecationWarning` | Modify | ⬜ |
| 9.2.2 | `place_order()` → use `broker.trading.account().place_order()` | Warn | ⬜ |
| 9.2.3 | `get_quote()` → use `broker.market.quote()` | Warn | ⬜ |
| 9.2.4 | `get_positions()` → use `broker.trading.account().positions()` | Warn | ⬜ |
| 9.2.5 | `get_historical_candles()` → use `broker.market.ohlcv()` | Warn | ⬜ |

### Task 9.3: Remove `_underlying_gateway`

| # | Item | Type | Done |
|---|------|------|------|
| 9.3.1 | Remove `_underlying_gateway` property from `BrokerFacade` | Remove | ⬜ |
| 9.3.2 | Update any internal code using it | Modify | ⬜ |

### Task 9.4: Clean Up `BrokerGateway` Protocol

| # | Item | Type | Done |
|---|------|------|------|
| 9.4.1 | Reduce `BrokerGateway` to essential properties only | Audit | ⬜ |
| 9.4.2 | Remove `extensions` property (now via plugin loader) | Modify | ⬜ |
| 9.4.3 | Remove `options` property (now via market service) | Modify | ⬜ |

### Task 9.5: Tests

| # | Item | Type | Done |
|---|------|------|------|
| 9.5.1 | `test_create_broker_deprecation_warning` | Test | ⬜ |
| 9.5.2 | `test_broker_facade_deprecation_warnings` | Test | ⬜ |
| 9.5.3 | `test_new_api_no_warnings` | Test | ⬜ |
| 9.5.4 | `test_connect_returns_broker_session` | Test | ⬜ |

### Definition of Done for Phase 9
- [ ] `create_broker()` emits deprecation warning, delegates to `connect()`
- [ ] `BrokerFacade` methods emit deprecation warnings
- [ ] `_underlying_gateway` removed
- [ ] `BrokerGateway` protocol reduced
- [ ] 5-8 new tests
- [ ] **0 regressions**

---

## Phase 10: Replay Engine & Paper Advanced

**Goal**: Create replay engine as a `HistoricalProvider`. Upgrade Paper gateway with realistic fills, slippage model, and order book.

**Dependencies**: Phase 4 (HistoricalRouter), Phase 6 (OMS)

**Estimated Tests**: 25-30 new

### Task 10.1: Create `market/replay/` Directory

| # | Item | Type | Done |
|---|------|------|------|
| 10.1.1 | `market/replay/__init__.py` | Create | ⬜ |
| 10.1.2 | `market/replay/engine.py` — ReplayEngine | Create | ⬜ |
| 10.1.3 | `market/replay/provider.py` — ReplayHistoricalProvider | Create | ⬜ |
| 10.1.4 | `market/replay/repository.py` — stored replay data | Create | ⬜ |
| 10.1.5 | Replay speed control (1x, 2x, 10x, tick-by-tick) | Implement | ⬜ |
| 10.1.6 | Seek to timestamp | Implement | ⬜ |

### Task 10.2: Register Replay as `HistoricalProvider`

| # | Item | Type | Done |
|---|------|------|------|
| 10.2.1 | Replay provider implements `HistoricalProvider` Protocol | Verify | ⬜ |
| 10.2.2 | Register in `HistoricalRouter` alongside broker providers | Wire | ⬜ |
| 10.2.3 | Priority: cache → replay → broker (configurable) | Implement | ⬜ |

### Task 10.3: CSV Historical Provider

| # | Item | Type | Done |
|---|------|------|------|
| 10.3.1 | CSV file reader implementing `HistoricalProvider` | Create | ⬜ |
| 10.3.2 | Auto-detect CSV format (ohlcv columns) | Implement | ⬜ |

### Task 10.4: Paper Gateway Enhancements

| # | Item | Type | Done |
|---|------|------|------|
| 10.4.1 | Fill simulation with configurable latency | Implement | ⬜ |
| 10.4.2 | Slippage model (fixed percentage, market impact) | Implement | ⬜ |
| 10.4.3 | Order book for limit order fills | Implement | ⬜ |
| 10.4.4 | Partial fills | Implement | ⬜ |
| 10.4.5 | Position tracking | Implement | ⬜ |
| 10.4.6 | P&L calculation | Implement | ⬜ |

### Task 10.5: Tests

| # | Item | Type | Done |
|---|------|------|------|
| 10.5.1 | `test_replay_engine_playback` | Test | ⬜ |
| 10.5.2 | `test_replay_historical_provider` | Test | ⬜ |
| 10.5.3 | `test_replay_seek_timestamp` | Test | ⬜ |
| 10.5.4 | `test_csv_provider_load` | Test | ⬜ |
| 10.5.5 | `test_paper_fill_simulation` | Test | ⬜ |
| 10.5.6 | `test_paper_slippage_model` | Test | ⬜ |
| 10.5.7 | `test_paper_order_book_fills` | Test | ⬜ |
| 10.5.8 | `test_paper_position_tracking` | Test | ⬜ |

### Definition of Done for Phase 10
- [ ] Replay engine with speed control and seek
- [ ] Replay registered as HistoricalProvider in HistoricalRouter
- [ ] CSV historical provider
- [ ] Paper gateway upgraded with fills, slippage, order book
- [ ] 12-15 new tests
- [ ] **0 regressions**

---

## Phase 11: Market Router (Multi-Provider)

**Goal**: Route quote/depth requests through multiple providers with cache-first strategy. Supports broker adapters, replay, and future market-data vendors.

**Dependencies**: Phase 4 (cache infrastructure), Phase 10 (replay provider)

**Estimated Tests**: 20-25 new

### Task 11.1: Create `market/market_router.py`

| # | Item | Type | Done |
|---|------|------|------|
| 11.1.1 | `MarketRouter` class | Create | ⬜ |
| 11.1.2 | Register market data providers | Implement | ⬜ |
| 11.1.3 | Cache-first quote retrieval | Implement | ⬜ |
| 11.1.4 | Cache-first depth retrieval | Implement | ⬜ |
| 11.1.5 | Provider fallback strategy | Implement | ⬜ |
| 11.1.6 | Stale-while-revalidate for quotes | Implement | ⬜ |

### Task 11.2: Provider Selection Policy

| # | Item | Type | Done |
|---|------|------|------|
| 11.2.1 | Priority-based provider selection | Implement | ⬜ |
| 11.2.2 | Latency-based selection | Implement | ⬜ |
| 11.2.3 | Capability-based selection | Implement | ⬜ |

### Task 11.3: Integrate into `MarketDataContext`

| # | Item | Type | Done |
|---|------|------|------|
| 11.3.1 | `MarketDataContext` optionally accepts `MarketRouter` | Modify | ⬜ |
| 11.3.2 | `quote()` routes through router when available | Modify | ⬜ |
| 11.3.3 | `depth()` routes through router when available | Modify | ⬜ |

### Task 11.4: Tests

| # | Item | Type | Done |
|---|------|------|------|
| 11.4.1 | `test_market_router_cache_hit` | Test | ⬜ |
| 11.4.2 | `test_market_router_provider_fallback` | Test | ⬜ |
| 11.4.3 | `test_market_router_priority_selection` | Test | ⬜ |
| 11.4.4 | `test_market_router_stale_while_revalidate` | Test | ⬜ |
| 11.4.5 | `test_market_router_integration_context` | Test | ⬜ |

### Definition of Done for Phase 11
- [ ] MarketRouter with cache-first, multi-provider, fallback
- [ ] Provider selection policy (priority, latency, capability)
- [ ] Integrated into MarketDataContext
- [ ] 8-10 new tests
- [ ] **0 regressions**

---

## Phase 12: Backtesting & Scanner

**Goal**: Create backtesting engine using replay data. Create scanner service that never knows brokers.

**Dependencies**: Phase 6 (OMS), Phase 10 (Replay), Phase 11 (MarketRouter)

**Estimated Tests**: 30-40 new

### Task 12.1: Create `trading/backtesting/` Directory

| # | Item | Type | Done |
|---|------|------|------|
| 12.1.1 | `trading/backtesting/__init__.py` | Create | ⬜ |
| 12.1.2 | `trading/backtesting/engine.py` — BacktestEngine | Create | ⬜ |
| 12.1.3 | `trading/backtesting/report.py` — backtest report | Create | ⬜ |
| 12.1.4 | Strategy base class | Create | ⬜ |
| 12.1.5 | Fill engine (uses paper gateway or OMS) | Create | ⬜ |

### Task 12.2: Create `market/scanner/` Directory

| # | Item | Type | Done |
|---|------|------|------|
| 12.2.1 | `market/scanner/__init__.py` | Create | ⬜ |
| 12.2.2 | `market/scanner/service.py` — ScannerService | Create | ⬜ |
| 12.2.3 | Scanner criteria DSL | Create | ⬜ |
| 12.2.4 | Scanner results publisher (events) | Create | ⬜ |

### Task 12.3: Tests

| # | Item | Type | Done |
|---|------|------|------|
| 12.3.1 | `test_backtest_engine_run` | Test | ⬜ |
| 12.3.2 | `test_backtest_with_replay_data` | Test | ⬜ |
| 12.3.3 | `test_backtest_report_generation` | Test | ⬜ |
| 12.3.4 | `test_scanner_criteria_matching` | Test | ⬜ |
| 12.3.5 | `test_scanner_result_events` | Test | ⬜ |
| 12.3.6 | `test_scanner_no_broker_knowledge` | Test | ⬜ |

### Definition of Done for Phase 12
- [ ] Backtesting engine with replay data
- [ ] Scanner service (broker-agnostic)
- [ ] 10-15 new tests
- [ ] **0 regressions**

---

# Development Cycle

Each phase follows this cycle:

```
┌─────────────────────────────────────────────────────────────┐
│                     DEVELOPMENT CYCLE                        │
│                                                              │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐            │
│  │  PLAN    │────→│ EXECUTE  │────→│  TEST    │            │
│  │          │     │          │     │          │            │
│  │ Task     │     │ Write    │     │ Unit     │            │
│  │ Checklist│     │ Code     │     │ Contract │            │
│  │ Per item │     │ Per item │     │ Arch     │            │
│  └──────────┘     └──────────┘     └──────────┘            │
│        ↑                                    │               │
│        │                                    ▼               │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐            │
│  │ REVIEW   │←────│ FIX      │←────│ FAIL?    │            │
│  │          │     │          │     │          │            │
│  │ Code     │     │ Address  │     │ Any      │            │
│  │ Review   │     │ Issues   │     │ Failure  │            │
│  │ All Done │     │          │     │          │            │
│  └──────────┘     └──────────┘     └──────────┘            │
│        │                                                    │
│        ▼                                                    │
│  ┌──────────┐                                               │
│  │ NEXT     │                                               │
│  │ PHASE    │                                               │
│  └──────────┘                                               │
└─────────────────────────────────────────────────────────────┘
```

## Within Each Phase

```
For each task in phase:
  1. PLAN: Read task checklist, understand scope
  2. EXECUTE: Write code, one checklist item at a time
  3. TEST: Run ptest for that specific file/module
  4. If PASS: Mark item done, continue to next
  5. If FAIL: FIX immediately, re-test
  6. REVIEW: Once all items complete, run full suite
  7. If REGRESSION: Fix before proceeding
  8. If ALL PASS: Phase done, move to next
```

## Commit Cadence

```
After each task group (e.g., 5.2.1-5.2.15 completed):
  → Run full suite
  → If all pass, commit
  → Never commit with regressions
```

---

# Architecture Fitness Functions (CI Guardrails)

| # | Rule | Enforcement | Added By |
|---|------|-------------|----------|
| 1 | No cyclic dependencies | `test_architecture.py` | Phase 1 |
| 2 | No service locator | `test_no_global_singletons` | Phase 1 |
| 3 | No broker DTO leakage | `test_broker_dto_leakage` | Phase 1 |
| 4 | Domain never imports Infrastructure | `test_boundary` | Phase 1 |
| 5 | One Instrument per symbol | `test_one_instrument_per_symbol` | Phase 1 |
| 6 | Every adapter passes contract tests | `tests/contract/` | Phase 2 |
| 7 | No mutable global state | `test_no_global_singletons` | Phase 1 |
| 8 | Market ↔ Trading isolation | `test_market_trading_boundary` | Phase 2 |
| 9 | Services constructor ≤ 5 params | `test_service_constructor_arg_limit` | Phase 3 |
| 10 | No `hasattr()` on gateway | `test_no_hasattr_on_gateway` | Phase 3 |
| 11 | Adapters not import services | `test_adapter_imports_service` | Phase 1 |
| 12 | All ports are `@runtime_checkable` Protocol | `test_port_structure` | Phase 1 |
| 13 | All exceptions inherit `TradeXV2Error` | `test_exception_hierarchy` | Phase 1 |
| 14 | Cache-first for historical data | `test_historical_router` | Phase 4 |
| 15 | Unified capability model | `test_capability_constants` | Phase 3 |

---

# Contract Testing Matrix

| Contract | File | Phase | Status |
|----------|------|-------|--------|
| `BrokerGateway` | `test_broker_contract.py` | ✅ Phase 2 | Passes |
| `MarketDataPort` | `test_market_data_contract.py` | ✅ Phase 2 | Passes |
| `OrderExecutionPort` | `test_order_contract.py` | ✅ Phase 2 | Passes |
| `PortfolioPort` | `test_portfolio_contract.py` | ✅ Phase 2 | Passes |
| `HistoricalPort` | `test_historical_contract.py` | ✅ Phase 2 | Passes |
| `OptionsPort` | `test_options_contract.py` | ✅ Phase 2 | Passes |
| `InstrumentsPort` | `test_instruments_contract.py` | ✅ Phase 2 | Passes |
| `StreamingPort` | `test_streaming_contract.py` | ✅ Phase 2 | Passes |
| `CapabilityContract` | `test_capability_contract.py` | ✅ Phase 3 | Passes |
| `SubscriptionManager` | (new) | ⬜ Phase 5 | Not yet |
| `OMS` | (new) | ⬜ Phase 6 | Not yet |
| `ExecutionRouter` | (new) | ⬜ Phase 6 | Not yet |
| `EventBus` | (new) | ⬜ Phase 8 | Not yet |
| `MarketRouter` | (new) | ⬜ Phase 11 | Not yet |

---

# Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Test count regression | Medium | Low | Run `pytest -q` before every commit |
| Architecture boundary violation | High | Low | `test_architecture.py` runs in <1s |
| Streaming adapter incompatibility | High | Medium | Contract tests for StreamingPort |
| Cross-context dependency (market→trading) | High | Low | `test_market_trading_boundary` |
| Gateway deprecation breaks downstream | Medium | Medium | Deprecation warnings for 2 releases |
| Event ordering violation | Medium | Low | Seq counter + ordered subscription |
| Memory leak from subscription callbacks | Medium | Low | Reference counting + clear() |
| Thread safety in concurrent streaming | High | Medium | RLock in SubscriptionManager, MemoryCache |

---

# Acceptance Criteria (Overall)

| # | Criterion | Measurement |
|---|-----------|-------------|
| 1 | Instrument is primary domain abstraction | `market.instrument("NSE:RELIANCE")` returns `Instrument` |
| 2 | Market, Trading, Infrastructure separated | Architecture tests enforce boundary |
| 3 | Broker adapters are implementation details | Adapters never imported into domain/ports |
| 4 | One Instrument per symbol | `InstrumentRegistry` guarantee (tested) |
| 5 | Rich domain objects over anemic services | `Instrument` has behaviour (validate, is_expired, etc.) |
| 6 | No broker-specific leak into common contracts | `test_no_broker_dto_leakage` |
| 7 | SOLID compliance | Architecture tests enforce ISP, DIP, SRP |
| 8 | New brokers addable without modifying core | Plugin-based extension loader |
| 9 | Cache-first for historical data | `HistoricalRouter` tested |
| 10 | Deduplicated streaming subscriptions | `SubscriptionManager` reference counting |
| 11 | Orders owned by Accounts | `account.place_order()` vs `instrument.buy()` |
| 12 | All phases maintain 0 regressions | `pytest -q` baseline never drops |
| 13 | Event-driven architecture | Typed events, auto-update state |
| 14 | Capability-based feature discovery | `broker.capabilities.supports("gtt")` |
| 15 | Incremental migration | `create_broker()` → `connect()` → deprecation |

---

# Quick Start (Per Phase)

```bash
# Run architecture tests (<1s)
python -m pytest tests/unit/test_architecture.py -m architecture -v

# Run unit tests
python -m pytest tests/unit/ -v -q

# Run contract tests
python -m pytest tests/contract/ -v

# Run full suite
python -m pytest tests/unit/ tests/contract/ -v -q

# Run with coverage
python -m pytest tests/unit/ tests/contract/ --cov=brokers -v -q

# Run specific test file
python -m pytest tests/unit/test_historical_router.py -v

# Run specific test class
python -m pytest tests/unit/test_memory_cache.py::TestMemoryCache -v

# Run specific test
python -m pytest tests/unit/test_memory_cache.py::TestMemoryCache::test_ttl_expiration -v
```
