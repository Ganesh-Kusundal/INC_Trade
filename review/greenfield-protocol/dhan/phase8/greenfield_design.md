# Phase 8 — Greenfield Design Analysis

> **Scope:** Cross-cutting concerns not covered by Phases 0–7: gateway lifecycle, factory bootstrap, identity management, configuration system, domain models, extended features, options/futures trading, symbol validation, reconciliation, alerts, EDIS, segments, capabilities, IP management, metrics, session management, account registry, ledger, user profile, exception hierarchy, and secret management.

---

## Architecture Overview

### Archive Architecture (Monolithic)

The archive implements a **monolithic gateway pattern** with centralized orchestration:

```
BrokerFactory (bootstrap orchestrator)
  ├─ DhanSettingsLoader (env/JSON/.env config loading)
  ├─ DhanConnectionSettings (frozen dataclass, 15+ fields)
  ├─ DhanConfigLoader (multi-source resilience config)
  ├─ AuthManager + TokenState (auth orchestration)
  ├─ DhanTotpClient (TOTP with cooldown guard)
  ├─ DhanConnection (central hub, wraps HTTP + WS)
  │   ├─ MarketDataGateway (order/quote/depth streaming)
  │   ├─ ObservabilityProvider (health/metrics/circuit breakers)
  │   └─ Token broadcast (consumer notification)
  ├─ BrokerGateway (facade wrapping DhanConnection)
  │   ├─ DhanIdentityProvider (symbol resolution with audit trail)
  │   ├─ OptionsAdapter (option chain, expiries, MCX)
  │   ├─ FuturesAdapter (contract discovery, commodity detection)
  │   ├─ AlertsAdapter (typed requests, validation)
  │   ├─ EDISAdapter (TPIN, ISIN validation, authorization)
  │   ├─ LedgerAdapter (typed entries, date validation)
  │   ├─ UserProfileAdapter (typed UserProfile)
  │   ├─ IPManagementAdapter (IPv4 validation, PRIMARY/SECONDARY)
  │   ├─ DhanReconciliationService (full engine, auto-repair)
  │   └─ DhanExtendedCapabilities (super/forever/conditional orders)
  ├─ InstrumentLoader (CSV caching, MCX supplement)
  ├─ DhanSymbolValidator (4 regex patterns, F&O parsing)
  ├─ AccountConnectionRegistry (singleton per account)
  ├─ DhanSessionManager (lifecycle state, trading readiness)
  └─ Prometheus metrics (9 metrics, WS + HTTP)
```

**Key characteristics:**
- **Centralized composition**: `BrokerFactory` orchestrates all component creation
- **External dependency injection**: Factory builds pieces, gateway wraps connection
- **Rich type safety**: Frozen dataclasses for all domain models (AlertRequest, LedgerEntry, UserProfile, etc.)
- **Defence-in-depth**: Identity assertions before every API call (`assert_dhan_identity()`)
- **Multi-source configuration**: Env vars, JSON files, .env files with deep merge
- **Observability**: Full `ObservabilityProvider` protocol with circuit breaker states, token refresh metrics, per-feed connection status
- **Process-wide singleton**: `AccountConnectionRegistry` enforces one gateway per account

### Greenfield Architecture (Modular)

The greenfield implements a **modular adapter pattern** with internal composition:

```
DhanGateway (internal composition, builds all adapters)
  ├─ DhanAuth (TOTP inline, token state, IPv4 preference)
  ├─ TokenBroadcast (weak refs, idempotent registration)
  ├─ DhanInstrumentResolver (symbol resolution, simplified)
  ├─ DhanOptions (option chain with frozen dataclasses)
  ├─ DhanFutures (contract discovery, expiry parsing)
  ├─ DhanAlerts (thin HTTP wrapper)
  ├─ DhanEDIS (TPIN status, form)
  ├─ DhanLedger (raw dict returns)
  ├─ DhanUserProfile (raw dict returns, adds update)
  ├─ DhanIpManagement (whitelist add/remove)
  ├─ DhanReconciliation (basic position matching)
  ├─ DhanSuperOrders (extension adapter)
  ├─ DhanForeverOrders (extension adapter)
  ├─ DhanConditionalTriggers (extension adapter)
  ├─ DhanExitAll (extension adapter)
  ├─ DhanMTF (dedicated MTF adapter)
  ├─ DhanInstruments (InstrumentPort implementation)
  ├─ DhanSymbolValidator (simple resolve-or-False)
  ├─ DhanCapabilities (9 boolean flags)
  └─ Prometheus metrics (3 metrics, HTTP only)
```

**Key characteristics:**
- **Internal composition**: Gateway constructor builds all adapters inline
- **Port-based interfaces**: `BrokerGateway` Protocol composes narrow ports (ISP)
- **Simplified identity**: `DhanInstrumentResolver` without audit logging or constraints
- **Static configuration**: Hardcoded endpoints/rate limits in `config.py`
- **Explicit mapper**: `mapper.py` for DTO → domain entity conversion
- **Dedicated MTF adapter**: Separate from order product types
- **IPv4 workaround**: `_prefer_ipv4()` patches `socket.getaddrinfo` for auth.dhan.co IPv6 issues

---

## Improvements Over Archive

The greenfield introduces several intentional improvements:

### 1. **Port-Based Architecture (ISP Compliance)**

**Archive:** Single monolithic `BrokerGateway` class implementing all methods.

**Greenfield:** `BrokerGateway` Protocol composes narrow ports:
```python
class BrokerGateway(
    OrderExecutionPort,
    MarketDataPort,
    PortfolioPort,
    InstrumentPort,
    ...
):
```

**Benefit:** Clients depend only on the ports they use (Interface Segregation Principle). Easier to mock for testing.

### 2. **Explicit DTO Mapper**

**Archive:** Mapping scattered across adapters, no dedicated module.

**Greenfield:** `mapper.py` with explicit functions:
```python
def map_order(dto: dict) -> Order
def map_quote(dto: dict) -> Quote
def map_position(dto: dict) -> Position
```

**Benefit:** Single source of truth for DTO → entity conversion. Easier to test and maintain.

### 3. **Typed Option Chain Returns**

**Archive:** `OptionsAdapter.get_option_chain()` returns `TypedDict`.

**Greenfield:** `DhanOptions.get_option_chain()` returns frozen dataclasses:
```python
@dataclass(frozen=True)
class OptionChain:
    strikes: list[OptionStrike]
    
@dataclass(frozen=True)
class OptionStrike:
    strike: float
    calls: list[OptionLeg]
    puts: list[OptionLeg]
```

**Benefit:** Immutable, type-safe, IDE-friendly. Prevents accidental mutation.

### 4. **Token Broadcast with Weak Refs**

**Archive:** `connection.broadcast_token()` with strong refs.

**Greenfield:** `TokenBroadcast` with weak refs, idempotent registration, dead-ref cleanup:
```python
class TokenBroadcast:
    def register(self, consumer: TokenConsumer) -> None:
        # WeakRef + idempotent check
        # Dead-ref cleanup on broadcast
```

**Benefit:** Prevents memory leaks when consumers are garbage collected.

### 5. **IPv4 Preference Workaround**

**Archive:** No IPv4 handling.

**Greenfield:** `_prefer_ipv4()` patches `socket.getaddrinfo` to force IPv4 for auth.dhan.co.

**Benefit:** Works around Dhan's IPv6 DNS issues in certain environments.

### 6. **Dedicated MTF Adapter**

**Archive:** MTF handled via product type in orders.

**Greenfield:** `DhanMTF` dedicated adapter with `place_mtf_order()`.

**Benefit:** Clearer separation of concerns, easier to extend MTF-specific logic.

### 7. **Futures Chain Listing**

**Archive:** No futures chain method.

**Greenfield:** `DhanFutures.get_futures_chain()` returns all active contracts.

**Benefit:** More comprehensive futures discovery.

### 8. **Robust Option Underlying Resolution**

**Archive:** `ExtendedCapabilities.get_option_chain()` with MCX-specific futures resolution.

**Greenfield:** `DhanOptions._resolve_underlying()` with broad search + commodity futures fallback.

**Benefit:** More robust underlying symbol resolution for commodity options.

---

## Dropped Behaviors (Gaps)

### CRITICAL Severity (5 gaps)

These gaps break core functionality or prevent production deployment:

#### 1. **Account Connection Registry** (NOT_PORTED)

**Archive:** `AccountConnectionRegistry` singleton per account with thread-safe dict:
```python
class AccountConnectionRegistry:
    def get_or_create(self, account_id: str) -> BrokerGateway
    def get(self, account_id: str) -> BrokerGateway | None
    def release(self, account_id: str) -> None
    def active_count(self) -> int
```

**Greenfield:** No singleton enforcement. Each `DhanGateway` construction creates a new instance.

**Impact:** Multiple gateways for the same account can coexist, causing duplicate WebSocket connections, token refresh races, and order conflicts.

**Recommendation:** Port the registry pattern or use dependency injection framework.

#### 2. **Factory Bootstrap** (NOT_PORTED)

**Archive:** `BrokerFactory.create()` orchestrates full bootstrap:
```python
class BrokerFactory:
    @classmethod
    def create(cls, env: str = "production") -> BrokerGateway:
        settings = DhanSettingsLoader.from_env()
        auth = AuthManager(...)
        http_client = build_http_client(...)
        connection = DhanConnection(...)
        gateway = BrokerGateway(connection)
        cls._wire_websocket_services(gateway)
        cls._setup_token_refresh_scheduler(gateway)
        register_broker_health_check(BrokerId.DHAN, gateway)
        return gateway
```

**Greenfield:** No factory class. `DhanGateway.__init__()` takes explicit params.

**Impact:** Clients must manually orchestrate bootstrap, increasing complexity and error risk.

**Recommendation:** Add `DhanGatewayFactory.create()` class method or module-level factory function.

#### 3. **Settings Loader** (NOT_PORTED)

**Archive:** `DhanSettingsLoader` with env var loading, sandbox support, secrets manager integration:
```python
class DhanSettingsLoader:
    @classmethod
    def from_env(cls, prefix: str = "DHAN_") -> DhanConnectionSettings:
        # Load from env vars, .env file, secrets manager
        # Apply sandbox overrides
        # Return frozen dataclass
```

**Greenfield:** No settings loader. Gateway takes explicit constructor params.

**Impact:** No standardized way to load settings from environment. Clients must manually parse env vars.

**Recommendation:** Add `DhanSettings` dataclass + `DhanSettingsLoader.from_env()`.

#### 4. **Resilience Config Loader** (NOT_PORTED)

**Archive:** `DhanConfigLoader` with multi-source loading (env vars, JSON, .env, deep merge):
```python
class DhanConfigLoader:
    def load(self) -> DhanResilienceConfig:
        # Load from env vars with ENV_KEY_MAPPING
        # Load from JSON file
        # Load from .env file
        # Deep merge all sources
        # Return DhanRateLimitConfig, DhanRetryConfig, DhanCircuitBreakerConfig, DhanTokenConfig
```

**Greenfield:** Static config in `config.py` (hardcoded constants).

**Impact:** Cannot tune rate limits, retry backoff, circuit breaker thresholds per environment.

**Recommendation:** Port `DhanConfigLoader` or use environment-specific config files.

#### 5. **Session Manager** (NOT_PORTED)

**Archive:** `DhanSessionManager` with lifecycle state, trading readiness:
```python
class DhanSessionManager:
    def token_valid(self) -> bool
    def connection_state(self) -> str
    def subscription_snapshot(self) -> dict
    def lifecycle_state(self) -> str
    def is_ready_for_trading(self) -> bool
    def health_summary(self) -> dict
```

**Greenfield:** No session manager. Gateway has `health()` but no lifecycle state machine.

**Impact:** No way to check if gateway is ready for trading before placing orders.

**Recommendation:** Add `DhanSessionManager` or integrate lifecycle state into `DhanGateway`.

---

### HIGH Severity (9 gaps)

These gaps reduce observability, robustness, or feature completeness:

#### 1. **ObservabilityProvider Protocol** (NOT_PORTED)

**Archive:** Full implementation with `get_connection_status()`, `get_connection_metadata()`, `get_circuit_breaker_states()`, `get_token_refresh_metrics()`.

**Greenfield:** Not implemented.

**Impact:** No visibility into circuit breaker states, token refresh metrics, per-feed connection status.

**Recommendation:** Port `ObservabilityProvider` or integrate into `health()` method.

#### 2. **CommonBrokerGateway Async Port** (NOT_PORTED)

**Archive:** `_DhanCommonBrokerGateway` wraps sync gateway as async with `QuotaToken`:
```python
class _DhanCommonBrokerGateway:
    async def place_order(self, ...) -> OrderResponse:
        async with self._quota:
            return await self._loop.run_in_executor(...)
```

**Greenfield:** Not implemented.

**Impact:** No async adapter for legacy sync gateway. Cannot use greenfield in async codebases.

**Recommendation:** Add `AsyncDhanGateway` wrapper or make gateway natively async.

#### 3. **Full Symbol Validator** (DIVERGENT)

**Archive:** 437-line `DhanSymbolValidator` with 4 regex patterns, F&O parsing, expired detection, ambiguous matching:
```python
class DhanSymbolValidator:
    def parse_fo_symbol(self, symbol: str) -> list[FoCandidate]
    def _validate_fo(self, symbol: str, exchange: str) -> bool
    def _validate_standard(self, symbol: str, exchange: str) -> bool
    def _get_segment_code(self, segment: str) -> int
    def _get_inst_type_code(self, inst_type: str) -> int
```

**Greenfield:** 26-line stub with simple resolve-or-False:
```python
class DhanSymbolValidator:
    def validate_symbol(self, symbol: str, exchange: str) -> bool:
        try:
            self._resolver.resolve(symbol, exchange)
            return True
        except Exception:
            return False
```

**Impact:** No F&O symbol parsing, no expired option detection, no segment code mapping.

**Recommendation:** Port full validator with regex patterns and F&O parsing.

#### 4. **Full Reconciliation** (DIVERGENT)

**Archive:** `DhanReconciliationService` with `ReconciliationEngine`, order + position comparison, auto-repair, `DriftItem` severity:
```python
class DhanReconciliationService:
    def reconcile(self) -> list[DriftItem]:
        # Compare local OMS vs broker positions
        # Compare local OMS vs broker orders
        # Auto-repair: upsert missing orders/positions
        # Return drift items with severity
```

**Greenfield:** `DhanReconciliation.reconcile_positions()` — simple dict comparison.

**Impact:** No order reconciliation, no auto-repair, no drift severity tracking.

**Recommendation:** Port `ReconciliationEngine` with auto-repair.

#### 5. **Instrument Loader Caching** (DIVERGENT)

**Archive:** `InstrumentLoader.load_cached()` with 6-hour TTL, 7-day cleanup, MCX detailed supplement:
```python
class InstrumentLoader:
    def load_cached(self) -> pd.DataFrame:
        # Check cache (6-hour TTL)
        # Download CSV if stale
        # Cleanup old caches (> 7 days)
        # Supplement with MCX detailed CSV
        # Return merged DataFrame
```

**Greenfield:** `DhanInstrumentResolver._do_load()` fetches CSV on every load.

**Impact:** Slower startup, no MCX detailed supplement, no cache cleanup.

**Recommendation:** Port caching logic and MCX supplement.

#### 6. **Capabilities Matrix** (DIVERGENT)

**Archive:** `dhan_capabilities()` → `BrokerCapabilities` with rate limits, historical windows, stream limits, product types, order types, batch size:
```python
@dataclass
class BrokerCapabilities:
    max_orders_per_second: int
    max_websocket_subscriptions: int
    supported_product_types: list[str]
    supported_order_types: list[str]
    historical_data_window_days: int
    batch_order_size: int
```

**Greenfield:** `DhanCapabilities` dataclass with 9 boolean flags:
```python
@dataclass
class DhanCapabilities:
    supports_options: bool = True
    supports_futures: bool = True
    supports_mtf: bool = True
    ...
```

**Impact:** No rate limit info, no historical window info, no batch size info.

**Recommendation:** Expand `DhanCapabilities` to include numeric limits.

#### 7. **Identity Provider Audit Trail** (PARTIAL)

**Archive:** `DhanIdentityProvider` with audit logging, `DhanIdentitySource`, `coerce_identity_provider()`, `expected_segment` constraint:
```python
class DhanIdentityProvider:
    def resolve(self, symbol: str, exchange: str) -> DhanInstrumentRef:
        # Log audit: source, resolution path, constraints
        # Check expected_segment constraint
        # Return DhanInstrumentRef with source metadata
```

**Greenfield:** `DhanInstrumentResolver` without audit logging or constraints.

**Impact:** No audit trail for symbol resolution, no segment constraint checking.

**Recommendation:** Add audit logging and `expected_segment` constraint.

#### 8. **Extension Registry** (NOT_PORTED)

**Archive:** `register_dhan_extensions()` with `ExtensionBundle`, `SuperOrderProvider`, `ForeverOrderProvider`, `NativeSliceOrderProvider`:
```python
def register_dhan_extensions() -> None:
    registry = get_extension_registry()
    registry.register(ExtensionBundle(
        super_order_provider=SuperOrderProvider(),
        forever_order_provider=ForeverOrderProvider(),
        slice_order_provider=NativeSliceOrderProvider(),
    ))
```

**Greenfield:** Not implemented.

**Impact:** No integration with platform extension registry.

**Recommendation:** Port extension registry integration.

#### 9. **Stream Handle Lifecycle** (NOT_PORTED)

**Archive:** `_DhanStreamHandle` with `disconnect()`, `is_connected()`, session tracking:
```python
class _DhanStreamHandle:
    def disconnect(self) -> None
    def is_connected(self) -> bool
    def session_id(self) -> str
```

**Greenfield:** Streaming uses direct adapter pattern, no handle abstraction.

**Impact:** No way to disconnect individual streams, no session tracking.

**Recommendation:** Add stream handle abstraction or integrate into gateway lifecycle.

---

### MEDIUM Severity (11 gaps)

These gaps reduce type safety or feature completeness:

1. **Domain model dataclasses** (NOT_PORTED): Archive has `MarginRequest`, `AlertRequest`, `SuperOrder`, `ForeverOrder`, `ConditionalTrigger`, `LedgerEntry`, `UserProfile`, `IPConfig`, `ExitAllResponse`. Greenfield uses raw dicts.

2. **Segment wire functions** (PARTIAL): Archive has `to_dhan_wire()`, `to_sdk_int()`, `from_sdk_int()`, `DhanSegmentMapper`. Greenfield lacks these.

3. **Exception hierarchy granularity** (DIVERGENT): Archive has 14 exception classes (per-feature). Greenfield has 5 generic classes.

4. **WebSocket metrics** (PARTIAL): Archive has 9 metrics (WS subscriptions, callbacks, reconnects, ticks, dropped ticks). Greenfield has 3 HTTP-only metrics.

5. **EDIS authorization** (NOT_PORTED): Archive has `authorize_edis()` with ISIN validation. Greenfield has `get_edis_form()` instead.

6. **Commodity detection** (NOT_PORTED): Archive has `FuturesAdapter.is_commodity()` against `COMMON_COMMODITIES` set. Greenfield lacks this.

7. **Secret utils** (NOT_PORTED): Archive has `read_secret()` with env var + file fallback. Greenfield handles credentials directly in auth.

8. **Instrument adapter** (NOT_PORTED): Archive has `to_instrument_id()` / `from_instrument_id()` converters. Greenfield uses `DhanInstrumentRef` directly.

9. **Constants module** (NOT_PORTED): Archive has `DHAN_DEPTH_20_MAX_INSTRUMENTS=50`, `DHAN_DEPTH_200_MAX_INSTRUMENTS=1`, `DHAN_IDEMPOTENCY_MAX_SIZE=1000`, `DHAN_IDEMPOTENCY_TTL_SECONDS=3600`. Greenfield lacks these.

10. **Dhan-specific enums** (NOT_PORTED): Archive has `Exchange`, `InstrumentType`, `OptionType` enums. Greenfield uses `brokers.domain.enums`.

11. **Identity assertions** (NOT_PORTED): Archive calls `assert_dhan_identity()` before every API call. Greenfield drops defence-in-depth.

---

### LOW Severity (6 gaps)

These gaps are minor or cosmetic:

1. **Expired options TypedDict** (PARTIAL): Archive returns `ExpiredOptionsResult` TypedDict. Greenfield returns raw dict.

2. **Ledger typed entries** (DIVERGENT): Archive returns `LedgerEntry` dataclass. Greenfield returns raw dicts.

3. **User profile typed** (DIVERGENT): Archive returns `UserProfile` dataclass. Greenfield returns raw dict.

4. **IP management types** (DIVERGENT): Archive has `IPConfig` dataclass, PRIMARY/SECONDARY types. Greenfield has whitelist add/remove.

5. **Futures expiry listing** (NOT_PORTED): Archive has `FuturesAdapter.get_expiries()`. Greenfield resolves contracts directly.

6. **Alert typed requests** (DIVERGENT): Archive has `AlertRequest`/`Alert` dataclasses. Greenfield uses raw dict payload.

---

## Key Architectural Decisions

### Decision 1: Gateway Composition Pattern

**Archive:** External composition via factory.
```python
# Factory builds pieces
connection = DhanConnection(settings, auth, http_client)
gateway = BrokerGateway(connection)
```

**Greenfield:** Internal composition in gateway constructor.
```python
# Gateway builds all adapters
class DhanGateway:
    def __init__(self, credentials: dict, ...):
        self._auth = DhanAuth(credentials)
        self._options = DhanOptions(self._auth, self._resolver)
        self._futures = DhanFutures(self._auth, self._resolver)
        ...
```

**Rationale:** Greenfield prioritizes encapsulation. Gateway owns its dependencies.

**Trade-off:** Harder to test individual adapters in isolation. Harder to swap implementations.

**Recommendation:** Keep internal composition but add factory method for bootstrap.

---

### Decision 2: Factory/Bootstrap Approach

**Archive:** Full `BrokerFactory` with env loading, health registration, WS wiring.

**Greenfield:** No factory. Direct gateway construction.

**Rationale:** Greenfield prioritizes explicit dependency injection.

**Trade-off:** Clients must orchestrate bootstrap manually.

**Recommendation:** Add `DhanGatewayFactory.create()` class method to simplify bootstrap.

---

### Decision 3: Identity Management Strategy

**Archive:** Rich `DhanIdentityProvider` with audit logging, constraints, source tracking.

**Greenfield:** Simplified `DhanInstrumentResolver` without audit trail.

**Rationale:** Greenfield prioritizes simplicity and performance.

**Trade-off:** No audit trail for debugging symbol resolution issues.

**Recommendation:** Add optional audit logging (debug level) and `expected_segment` constraint.

---

### Decision 4: Configuration System Design

**Archive:** Multi-source loading (env vars, JSON, .env) with deep merge.

**Greenfield:** Static config in `config.py`.

**Rationale:** Greenfield prioritizes simplicity and predictability.

**Trade-off:** Cannot tune config per environment without code changes.

**Recommendation:** Add `DhanSettings` dataclass + `DhanSettingsLoader.from_env()` for production deployment.

---

### Decision 5: Options/Futures Trading Approach

**Archive:** `OptionsAdapter` with TypedDict returns, `FuturesAdapter` with cache-based discovery.

**Greenfield:** `DhanOptions` with frozen dataclass returns, `DhanFutures` with expiry parsing from symbol strings.

**Rationale:** Greenfield prioritizes type safety (options) and simpler discovery (futures).

**Trade-off:** Futures discovery is less robust (no cache).

**Recommendation:** Keep typed options. Add caching to futures discovery.

---

### Decision 6: Symbol Validation Approach

**Archive:** 437-line validator with regex patterns, F&O parsing, expired detection.

**Greenfield:** 26-line stub with resolve-or-False.

**Rationale:** Greenfield prioritizes simplicity.

**Trade-off:** No F&O symbol parsing, no expired option detection.

**Recommendation:** Port full validator. Critical for preventing bad orders.

---

## Design Principles Applied

### 1. **Interface Segregation Principle (ISP)**

Greenfield `BrokerGateway` Protocol composes narrow ports:
```python
class BrokerGateway(
    OrderExecutionPort,
    MarketDataPort,
    PortfolioPort,
    InstrumentPort,
):
```

**Benefit:** Clients depend only on the ports they use.

### 2. **Single Responsibility Principle (SRP)**

Each adapter has a single responsibility:
- `DhanAuth`: Authentication only
- `DhanOptions`: Options trading only
- `DhanFutures`: Futures trading only
- `DhanLedger`: Ledger queries only

**Benefit:** Easier to test, maintain, and extend.

### 3. **Dependency Inversion Principle (DIP)**

Greenfield depends on port abstractions, not concrete implementations:
```python
class DhanGateway:
    def __init__(self, auth: AuthPort, ...):
```

**Benefit:** Easy to swap implementations (e.g., mock auth for testing).

### 4. **Open/Closed Principle (OCP)**

Greenfield adapters are open for extension, closed for modification:
```python
class DhanOptions:
    def get_option_chain(self, ...): ...
    
class DhanOptionsWithGreeks(DhanOptions):
    def get_option_chain_with_greeks(self, ...): ...
```

**Benefit:** Can extend functionality without modifying existing code.

### 5. **Defence in Depth**

Archive uses identity assertions before every API call:
```python
def place_order(self, ...):
    assert_dhan_identity(self._identity)
    # ... place order
```

**Greenfield drops this.** Recommendation: Re-add for production.

---

## Recommended Architecture for Greenfield Cross-Cutting Concerns

### Layer 1: Configuration & Bootstrap

```
brokers/adapters/dhan/
  config.py              # Static endpoints, rate limits, exchange maps
  settings.py            # DhanSettings dataclass (NEW)
  settings_loader.py     # DhanSettingsLoader.from_env() (NEW)
  factory.py             # DhanGatewayFactory.create() (NEW)
```

**Responsibility:** Load config from environment, bootstrap gateway with all dependencies.

### Layer 2: Core Infrastructure

```
brokers/adapters/dhan/
  auth.py                # DhanAuth (TOTP, token state, IPv4)
  identity.py            # DhanInstrumentResolver (add audit logging)
  token_broadcast.py     # TokenBroadcast (weak refs)
  session_manager.py     # DhanSessionManager (NEW)
  account_registry.py    # AccountConnectionRegistry (NEW)
```

**Responsibility:** Authentication, symbol resolution, token lifecycle, session state, singleton registry.

### Layer 3: Trading Adapters

```
brokers/adapters/dhan/
  options.py             # DhanOptions (typed returns)
  futures.py             # DhanFutures (add caching)
  orders.py              # DhanOrders (order execution)
  mtf.py                 # DhanMTF (margin trading facility)
  super_orders.py        # DhanSuperOrders (extension)
  forever_orders.py      # DhanForeverOrders (extension)
  conditional_triggers.py # DhanConditionalTriggers (extension)
  exit_all.py            # DhanExitAll (extension)
```

**Responsibility:** All trading functionality (options, futures, orders, extensions).

### Layer 4: Data & Query Adapters

```
brokers/adapters/dhan/
  alerts.py              # DhanAlerts (add typed requests)
  edis.py                # DhanEDIS (add authorization)
  ledger.py              # DhanLedger (add typed entries)
  user_profile.py        # DhanUserProfile (add typed profile)
  ip_management.py       # DhanIpManagement (add types)
  reconciliation.py      # DhanReconciliation (add full engine)
```

**Responsibility:** Non-trading queries and operations.

### Layer 5: Observability & Metrics

```
brokers/adapters/dhan/
  metrics.py             # Prometheus metrics (add WS metrics)
  observability.py       # ObservabilityProvider (NEW)
  health.py              # Health check registration (NEW)
```

**Responsibility:** Metrics, health checks, circuit breaker states, token refresh metrics.

### Layer 6: Validation & Utilities

```
brokers/adapters/dhan/
  symbol_validator.py    # DhanSymbolValidator (port full validator)
  instrument_loader.py   # InstrumentLoader (add caching, MCX supplement)
  instrument_adapter.py  # to_instrument_id() / from_instrument_id() (NEW)
  constants.py           # WS limits, idempotency config (NEW)
  exceptions.py          # Expand to 14 classes (per-feature)
  secret_utils.py        # read_secret() with env + file fallback (NEW)
```

**Responsibility:** Validation, instrument loading, utilities, exceptions.

---

## Implementation Priority

### Phase 8a: Critical Infrastructure (Week 1)

1. **Account registry singleton** — Prevent duplicate gateways
2. **Factory bootstrap** — Simplify gateway construction
3. **Settings loader** — Standardize env var loading
4. **Session manager** — Check trading readiness

### Phase 8b: Observability & Robustness (Week 2)

5. **ObservabilityProvider** — Circuit breaker states, token metrics
6. **Full symbol validator** — F&O parsing, expired detection
7. **Full reconciliation** — Order + position comparison, auto-repair
8. **Instrument loader caching** — 6-hour TTL, MCX supplement

### Phase 8c: Type Safety & Completeness (Week 3)

9. **Domain model dataclasses** — Typed requests/responses for all features
10. **Exception hierarchy** — Per-feature exceptions
11. **Capabilities matrix** — Rate limits, historical windows, batch sizes
12. **WebSocket metrics** — Subscriptions, callbacks, reconnects, ticks

### Phase 8d: Polish & Integration (Week 4)

13. **Extension registry** — Integration with platform extensions
14. **Identity audit trail** — Debug logging for symbol resolution
15. **Constants module** — WS limits, idempotency config
16. **Secret utils** — Env var + file fallback

---

## Conclusion

The greenfield architecture is **fundamentally sound** but **incomplete**. It successfully ports the core trading functionality (options, futures, orders) with improvements (typed returns, port-based interfaces, weak-ref token broadcast). However, it drops critical infrastructure (account registry, factory bootstrap, settings loader, session manager) and reduces observability (no ObservabilityProvider, simplified metrics).

**Key recommendations:**

1. **Port critical infrastructure** (account registry, factory, settings loader, session manager) — these are blocking production deployment.
2. **Restore type safety** — replace raw dicts with frozen dataclasses for all domain models.
3. **Port full symbol validator** — critical for preventing bad orders.
4. **Add observability** — port ObservabilityProvider, expand metrics to include WS.
5. **Add factory bootstrap** — simplify gateway construction for clients.

The greenfield is **70% complete** for Phase 8 cross-cutting concerns. With the recommended additions, it will exceed the archive in type safety, modularity, and maintainability.
