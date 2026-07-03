# Architectural Smell Catalogue — Full Detail

## A — Shotgun Surgery

### A-1: Idempotency Cache Alias
- **Evidence**: `adapters/dhan/orders.py:51` uses `TypedIdempotencyCache()`, `adapters/upstox/orders.py:35` uses `InMemoryIdempotencyCache()`
- **Root Cause**: Historical divergence — Upstox was added later with a different alias
- **Priority**: P3 | **Confidence**: H
- **Fix**: Alias both to `TypedIdempotencyCache` or export a single shared name from `core/`

### A-2: Kill-switch Duplication
- **Evidence**: All 3 adapters + `services/order_service.py` replicate the `allow_live_orders` guard
- **Files**: `adapters/dhan/gateway.py:124`, `adapters/dhan/orders.py:115-118`, `adapters/upstox/gateway.py:56`, `adapters/upstox/orders.py:41-49`, `brokers/__init__.py:146`
- **Priority**: P1 | **Confidence**: H
- **Fix**: Single kill-switch in `OrderService`; adapters should not check it

### A-3: Payload Construction Duplication
- **Evidence**: `adapters/dhan/orders.py:303-317` (`place_slice_order`) builds same payload as `use_cases/place_order.py:152-170`
- **Priority**: P1 | **Confidence**: H
- **Fix**: Extract shared `_build_dhan_order_payload()` function

### A-4: Validation via Temp Entity
- **Evidence**: `services/order_validation.py:37-47` creates temp `Order()` with `Side.BUY` placeholder only to call `order.validate()`
- **Priority**: P2 | **Confidence**: H
- **Fix**: Extract validation rules as standalone functions, call from both `Order.validate()` and `validate_order_fields()`

### A-5: Opaque Event Payload
- **Evidence**: `domain/events.py:16` — `payload: dict[str, Any]`
- **Priority**: P2 | **Confidence**: H
- **Fix**: Typed event subclasses (`OrderPlaced`, `TokenRefreshed`)

### A-6: Segment→Exchange Mapping Duplication
- **Evidence**: Both `adapters/dhan/config.py` and `adapters/upstox/config.py` have `SEGMENT_TO_EXCHANGE`
- **Priority**: P2 | **Confidence**: H
- **Fix**: Extract to `domain/constants/segments.py`

## B — Duplication

### B-1: WebSocket Streaming Boilerplate
- **Evidence**: Both `DhanStreaming` and `UpstoxStreaming` override same 8 methods from `BaseWebSocketStreaming`
- **Files**: `adapters/dhan/streaming.py`, `adapters/upstox/streaming.py`
- **Priority**: P2 | **Confidence**: H
- **Fix**: Parameterized message format strategy

### B-2: Three Reconnect Loops
- **Evidence**: `infrastructure/websocket_runner.py:86`, `infrastructure/websocket_pool.py:180`, `adapters/base_streaming.py:137` — all implement exponential backoff
- **Priority**: P1 | **Confidence**: H
- **Fix**: Extract `ReconnectStrategy` class

### B-3: Mapper Duplication
- **Evidence**: Both `adapters/dhan/mapper.py` and `adapters/upstox/mapper.py` have `map_order`, `map_order_response`
- **Priority**: P3 | **Confidence**: M
- **Fix**: Accept as broker-specific; verify consistent null handling

### B-4: Price→Wire Ternary Pattern
- **Evidence**: `to_wire_float(price) if price > 0 else 0.0` repeated in 3+ locations
- **Priority**: P3 | **Confidence**: H
- **Fix**: Add `default=0.0` parameter to `to_wire_float`

## C — Hidden Coupling

### C-1: Class-Level GatewayRegistry State
- **Evidence**: `infrastructure/registry.py:24-25` — `_instances` and `_lock` are class-level
- **Priority**: P1 | **Confidence**: H
- **Fix**: Make instance-level; manage via DI container

### C-2: Global WS Pool Singleton
- **Evidence**: `infrastructure/websocket_pool.py:290-294` — module-level state + `atexit`
- **Priority**: P2 | **Confidence**: H
- **Fix**: Instance-level pool with factory

### C-3: DCLP Singleton
- **Evidence**: `infrastructure/secret_manager.py:49-50` — double-checked locking, `reset_instance()` doesn't reset lock
- **Priority**: P3 | **Confidence**: L
- **Fix**: Reset `_instance_lock` in `reset_instance()`

### C-4: Config Temporal Coupling
- **Evidence**: `config/defaults.py:28-36` — `get_config()` must be called after env vars are set
- **Priority**: P2 | **Confidence**: M
- **Fix**: Lazy load with explicit `load()` method

### C-5: Token-in-Session at Construction
- **Evidence**: `adapters/dhan/gateway.py:155-160` — `self._auth.get_token()` at construction time
- **Priority**: P2 | **Confidence**: M
- **Fix**: Defer first token acquisition; use `update_token()` for all token delivery

## D — Naming Coupling

### D-1: `hasattr` Duck Typing in BrokerFacade
- **Evidence**: `services/broker_facade.py:193,204,212,223` — 4 `hasattr` gates
- **Priority**: P1 | **Confidence**: H
- **Fix**: Migrate to `ExtensionRegistry.resolve()`

### D-2: Capability String-Keyed Reflection
- **Evidence**: `domain/capabilities.py:75-76` — `supports(feature: str)` uses `getattr`
- **Priority**: P2 | **Confidence**: M
- **Fix**: Validate feature name against known capabilities

### D-3: `hasattr` in Registry close_all
- **Evidence**: `infrastructure/registry.py:211-215` — `getattr(gw, "close", None)`
- **Priority**: P3 | **Confidence**: M
- **Fix**: Use `BrokerGateway` protocol (has `.close()`)

## E — Fragmented Ownership

### E-1: Token Refresh Across 6 Modules
- **Evidence**: `adapters/dhan/auth.py`, `gateway.py`, `resilience/token_manager.py`, `token_scheduler.py`, `infrastructure/totp_cooldown.py`, `secret_manager.py`
- **Priority**: P2 | **Confidence**: H
- **Fix**: `TokenOrchestrator` in infrastructure

### E-2: Circuit Breaker + Retry Interaction
- **Evidence**: `resilience/circuit_breaker.py`, `infrastructure/http/resilient_client.py` — retry can mask failures from circuit breaker
- **Priority**: P2 | **Confidence**: M
- **Fix**: Ensure circuit breaker counts actual failures (not retry-wrapped ones)

## F — Parallel Hierarchies

### F-1: Parallel Adapter Structures
- **Evidence**: Dhan and Upstox mirror each other's class hierarchy
- **Priority**: P3 | **Confidence**: L
- **Fix**: Accept as intentional; document the convention

### F-2: Streaming Pool Near-Duplicates
- **Evidence**: `adapters/dhan/streaming_pool.py` — `PooledDhanDepth20Stream`, `PooledDhanDepth200Stream`, `PooledDhanOrderStream`
- **Priority**: P1 | **Confidence**: H
- **Fix**: Parameterized `DhanStreamChannel` class

## G — Inconsistent Abstraction

### G-1: PlaceOrderRequest Redefines Order Fields
- **Evidence**: `adapters/dhan/use_cases/place_order.py:39-51` — mirrors `domain/entities.py:23-40`
- **Priority**: P2 | **Confidence**: H
- **Fix**: Create `OrderRequest` value object in domain

### G-2: Defensive `getattr` on RiskCheckResult
- **Evidence**: `adapters/dhan/use_cases/place_order.py:147-149` — `getattr(risk_result, "allowed", True)`
- **Priority**: P2 | **Confidence**: H
- **Fix**: Trust the type — remove `getattr` fallback

### G-3: `object.__setattr__` Workaround
- **Evidence**: `domain/entities.py:190-202` — bypasses frozen dataclass immutability
- **Priority**: P2 | **Confidence**: H
- **Fix**: Use `__post_init__` with tuple conversion

### G-4: 60-Method URL Builder
- **Evidence**: `config/endpoints.py:91-374` — `_UpstoxUrls` with 60+ methods
- **Priority**: P2 | **Confidence**: M
- **Fix**: Dict-based URL registry

## H — Boundary Violations

### H-1: Hardcoded Circuit Breaker Thresholds (Minor)
- **Evidence**: `infrastructure/http/resilient_client.py:58-62`
- **Priority**: P3 | **Confidence**: L
- **Fix**: Accept as reasonable defaults

### H-2: Adapter Imports Service ❌
- **Evidence**: `adapters/dhan/use_cases/place_order.py:21` — `from brokers.services.order_validation import check_notional_warning`
- **Priority**: P1 | **Confidence**: H
- **Fix**: Move `check_notional_warning` to domain or inject port

### H-3: Reconciliation Imports Full Gateway
- **Evidence**: `services/reconciliation.py:10` — imports `BrokerGateway`
- **Priority**: P2 | **Confidence**: H
- **Fix**: Import `OrderExecutionPort` + `PortfolioPort` instead

### H-4: Use Case Imports Config at Module Level
- **Evidence**: `adapters/dhan/use_cases/place_order.py:11-12` — `from brokers.config.endpoints import Dhan`
- **Priority**: P2 | **Confidence**: H
- **Fix**: Inject `ENDPOINTS` in constructor

## I — SOLID Violations

### I-1: BrokerFacade Violates OCP
- **Evidence**: `services/broker_facade.py:193-224` — 4 `hasattr` gates for optional features
- **Priority**: P1 | **Confidence**: H
- **Fix**: ExtensionRegistry

### I-2: DhanGateway.__init__ Violates SRP
- **Evidence**: `adapters/dhan/gateway.py:118-233` — 115-line constructor, 10 responsibilities
- **Priority**: P1 | **Confidence**: H
- **Fix**: Extract builder

### I-3: UpstoxGateway.__init__ Violates SRP
- **Evidence**: `adapters/upstox/gateway.py:51-169` — 118-line constructor
- **Priority**: P1 | **Confidence**: H
- **Fix**: Extract builder

### I-4: _parse_binary_message Violates SRP
- **Evidence**: `adapters/dhan/streaming.py:196-276` — 3 parsers (Ticker/Quote/Full) in one method
- **Priority**: P2 | **Confidence**: H
- **Fix**: Separate parser per feed code

## J — Clean Architecture Violations

### J-1: Adapter Imports Infrastructure
- **Evidence**: `adapters/dhan/gateway.py:51-54` — imports `infrastructure.storage.token_store`
- **Priority**: P2 | **Confidence**: H
- **Fix**: Inject via `TokenStorePort`

### J-2: Lazy Import in Domain Entity
- **Evidence**: `domain/entities.py:47` — `from brokers.domain.exceptions import ValidationError` inside method
- **Priority**: P2 | **Confidence**: H
- **Fix**: Move to top-level (circular import is avoidable)

### J-3: Policy Leakage in Config
- **Evidence**: `config/endpoints.py:91-374` — URL builder with 60+ computation methods
- **Priority**: P3 | **Confidence**: L
- **Fix**: Move URL building to adapter layer; config holds only host constants

## K — DDD Violations

### K-1: Anemic Domain — Logic in Adapters
- **Evidence**: `adapters/dhan/use_cases/place_order.py:201-248` has domain validation logic
- **Priority**: P1 | **Confidence**: H
- **Fix**: Move validation to `domain/validators/`

### K-2: Unused State Machine
- **Evidence**: `domain/order_lifecycle.py` defines transitions but `Order` entity doesn't use them
- **Priority**: P2 | **Confidence**: H
- **Fix**: Wire `validate_transition()` into `Order`

### K-3: Passive Data Holders
- **Evidence**: `Trade`, `Holding` have no behavior methods
- **Priority**: P3 | **Confidence**: M
- **Fix**: Acceptable for simple data; enrich when use cases demand it

### K-4: Missing OptionChain Aggregate
- **Evidence**: `OptionChain` has no invariant enforcement
- **Priority**: P3 | **Confidence**: L
- **Fix**: Add factory method with invariant validation
