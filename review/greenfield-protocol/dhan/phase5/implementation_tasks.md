# Phase 5 — Order Management: Implementation Tasks

> **Protocol:** Greenfield Broker Replication — Dhan  
> **Phase:** 5 (Order Management)  
> **Date:** 2026-07-03

---

## 1. Task Dependency Graph

```
Layer 0 (Foundation)
  T01 ── Domain entities for Super/Forever orders
  T02 ── Idempotency cache implementation
  T03 ── Event bus port + in-memory impl
  T04 ── Risk manager port + basic impl

Layer 1 (Missing Subsystems)
  T05 ── Super Orders adapter          ← T01
  T06 ── Forever Orders adapter        ← T01
  T07 ── Kill switch adapter
  T08 ── Trade book / history adapter

Layer 2 (Service Layer Completion)
  T09  ── SuperOrderService            ← T05
  T10  ── ForeverOrderService          ← T06
  T11  ── Wire idempotency into OrderService   ← T02
  T12  ── Wire risk manager into OrderService  ← T04
  T13  ── Wire event bus into OrderService     ← T03

Layer 3 (Streaming + Reconciliation)
  T14  ── Conditional trigger validation       ← T08 (trade book for LLM)
  T15  ── Conditional trigger modify/get
  T16  ── WebSocket → state machine integration
  T17  ── Reconciliation engine implementation ← T16, T03

Layer 4 (Hardening)
  T18  ── Cancel error response parsing
  T19  ── Slice orders adapter
  T20  ── Exit-all: use native /exitall as primary
  T21  ── Integration test suite
  T22  ── Status mapper registry (multi-broker prep)
```

---

## 2. Task Definitions

### Layer 0 — Foundation

---

#### T01: Domain Entities for Super/Forever Orders

| Field | Value |
|---|---|
| **Priority** | P0 |
| **Gap Reference** | GAP-01, GAP-02 |
| **Effort** | 1 day |
| **Depends On** | — |

**Implementation Steps:**
1. Create `SuperOrder` frozen dataclass in `brokers/domain/entities.py`:
   - Fields: `order_id`, `symbol`, `exchange`, `side`, `quantity`, `price`, `target_price`, `stop_loss_price`, `trailing_jump`, `product_type`, `order_type`, `status`, `correlation_id`, `legs: tuple[SuperOrderLeg, ...]`
2. Create `SuperOrderLeg` frozen dataclass:
   - Fields: `leg_name`, `transaction_type`, `quantity`, `price`, `trigger_price`, `status`
3. Create `ForeverOrder` frozen dataclass:
   - Fields: `order_id`, `symbol`, `exchange`, `order_flag` (SINGLE/OCO), `side`, `quantity`, `price`, `trigger_price`, `product_type`, `order_type`, `status`, `price1`, `trigger_price1`, `quantity1`
4. Create `ConditionalTrigger` frozen dataclass:
   - Fields: `alert_id`, `symbol`, `exchange`, `comparison_type`, `operator`, `comparing_value`, `exp_date`, `frequency`, `status`, `orders`, `user_note`
5. Add `OrderFlag` enum to `enums.py`: `SINGLE`, `OCO`
6. Add `TriggerOperator` enum to `enums.py`: `CROSSING_UP`, `CROSSING_DOWN`, `GREATER_THAN`, `LESS_THAN`

**Acceptance Criteria:**
- [ ] All entities are `@dataclass(frozen=True)`
- [ ] All entities have zero infrastructure imports
- [ ] Unit tests verify immutability (attempting to set field raises `FrozenInstanceError`)
- [ ] Enums have expected members and values

---

#### T02: Idempotency Cache Implementation

| Field | Value |
|---|---|
| **Priority** | P1 |
| **Gap Reference** | GAP-04 |
| **Effort** | 1 day |
| **Depends On** | — |

**Implementation Steps:**
1. Define `IdempotencyCachePort` Protocol in `brokers/ports/idempotency.py`:
   ```python
   class IdempotencyCachePort(Protocol):
       def check_and_set(self, key: str) -> bool: ...
       def get(self, key: str) -> OrderResponse | None: ...
       def put(self, key: str, response: OrderResponse) -> None: ...
   ```
2. Implement `InMemoryIdempotencyCache` in `brokers/infrastructure/idempotency.py`:
   - Use `dict` + `threading.Lock` for thread safety
   - TTL-based expiry (default 5 minutes)
   - `check_and_set` atomically checks and marks key as in-flight
3. Implement `put()` to store the final `OrderResponse` after order completes
4. Add unit tests:
   - Concurrent `check_and_set` with same key → only one returns `True`
   - `get()` returns cached response after `put()`
   - Expired keys are cleaned up

**Acceptance Criteria:**
- [ ] Thread-safe under concurrent access
- [ ] TTL expiry works (configurable, default 5 min)
- [ ] `check_and_set` returns `False` on duplicate (prevents double submission)
- [ ] Unit tests pass with `pytest -x`

---

#### T03: Event Bus Port + In-Memory Implementation

| Field | Value |
|---|---|
| **Priority** | P1 |
| **Gap Reference** | GAP-06 |
| **Effort** | 1 day |
| **Depends On** | — |

**Implementation Steps:**
1. Define `EventBusPort` Protocol in `brokers/ports/event_bus.py`:
   ```python
   @dataclass(frozen=True)
   class DomainEvent:
       event_type: str
       payload: dict
       symbol: str
       timestamp: datetime
       source: str
   
   class EventBusPort(Protocol):
       def publish(self, event: DomainEvent) -> None: ...
       def subscribe(self, event_type: str, handler: Callable) -> None: ...
   ```
2. Implement `InMemoryEventBus` in `brokers/infrastructure/event_bus.py`:
   - Synchronous publish (iterate subscribers, call handler)
   - Error isolation (one handler failure doesn't block others)
   - Log unhandled exceptions
3. Unit tests:
   - Publish event → subscriber receives it
   - Multiple subscribers → all receive
   - Subscriber raises → others still receive, error logged

**Acceptance Criteria:**
- [ ] Protocol defined with `publish` and `subscribe`
- [ ] In-memory impl is thread-safe
- [ ] Handler errors are isolated and logged
- [ ] Unit tests pass

---

#### T04: Risk Manager Port + Basic Implementation

| Field | Value |
|---|---|
| **Priority** | P1 |
| **Gap Reference** | GAP-05 |
| **Effort** | 1 day |
| **Depends On** | — |

**Implementation Steps:**
1. Define `RiskManagerPort` Protocol in `brokers/ports/risk_manager.py`:
   ```python
   @dataclass(frozen=True)
   class RiskCheckResult:
       allowed: bool
       reason: str = ""
   
   class RiskManagerPort(Protocol):
       def check_order(self, order: Order) -> RiskCheckResult: ...
   ```
2. Implement `BasicRiskManager` in `brokers/services/risk_manager.py`:
   - Max order quantity check (configurable)
   - Max notional value check (configurable)
   - Max orders per minute check (configurable)
   - All checks return `RiskCheckResult(allowed=True)` if no limits configured
3. Unit tests:
   - Order within limits → allowed
   - Order exceeds quantity → rejected with reason
   - Order exceeds notional → rejected with reason

**Acceptance Criteria:**
- [ ] Protocol defined
- [ ] Basic impl with configurable limits
- [ ] Returns structured `RiskCheckResult`
- [ ] Unit tests pass

---

### Layer 1 — Missing Subsystems

---

#### T05: Super Orders Adapter

| Field | Value |
|---|---|
| **Priority** | P0 |
| **Gap Reference** | GAP-01 |
| **Effort** | 2 days |
| **Depends On** | T01 |

**Implementation Steps:**
1. Create `DhanSuperOrders` class in `brokers/adapters/dhan/super_orders.py`
2. Implement `place_super_order()`:
   - Resolve instrument via `DhanInstrumentResolver`
   - Validate: target > entry (BUY) or target < entry (SELL); SL < entry (BUY) or SL > entry (SELL)
   - Build payload with `targetPrice`, `stopLossPrice`, `trailingJump`
   - Call `assert_valid_dhan_payload()`
   - POST to `/super/orders`
   - Parse response into `SuperOrder` using `map_super_order()`
3. Implement `modify_super_order_leg()`:
   - PUT `/super/orders/{id}` with `legName`, optional `quantity`, `price`, `triggerPrice`
4. Implement `cancel_super_order_leg()`:
   - DELETE `/super/orders/{id}/{leg_name}`
   - Parse success/failure response
5. Implement `get_super_orders()`:
   - GET `/super/orders`
   - Parse list into `list[SuperOrder]`
6. Create `map_super_order()` and `map_super_order_leg()` in `brokers/adapters/dhan/mapper.py`
7. Add endpoint constants to `brokers/adapters/dhan/config.py`

**Acceptance Criteria:**
- [ ] Place/modify/cancel/get all work
- [ ] Validation rejects invalid target/SL directions
- [ ] Invariant assertion called before every POST/PUT
- [ ] Response parsing handles nested `data` key
- [ ] Unit tests with mocked HTTP client

---

#### T06: Forever Orders Adapter

| Field | Value |
|---|---|
| **Priority** | P0 |
| **Gap Reference** | GAP-02 |
| **Effort** | 2 days |
| **Depends On** | T01 |

**Implementation Steps:**
1. Create `DhanForeverOrders` class in `brokers/adapters/dhan/forever_orders.py`
2. Implement `place_forever_order()`:
   - Validate `order_flag` ∈ {SINGLE, OCO}
   - OCO requires `price1`, `trigger_price1`, `quantity1`
   - Build payload with OCO fields when applicable
   - POST to `/forever/orders`
3. Implement `modify_forever_order()`:
   - PUT `/forever/orders/{id}` with full re-submission
4. Implement `cancel_forever_order()`:
   - DELETE `/forever/orders/{id}`
5. Implement `get_all_forever_orders()`:
   - GET `/forever/all`
6. Create `map_forever_order()` in mapper module
7. Add endpoint constants

**Acceptance Criteria:**
- [ ] SINGLE and OCO placement work
- [ ] OCO validation rejects missing fields
- [ ] Modify re-submits full payload
- [ ] Unit tests with mocked HTTP client

---

#### T07: Kill Switch Adapter

| Field | Value |
|---|---|
| **Priority** | P1 |
| **Gap Reference** | GAP-03 |
| **Effort** | 0.5 days |
| **Depends On** | — |

**Implementation Steps:**
1. Create `DhanKillSwitch` class in `brokers/adapters/dhan/kill_switch.py`
2. Implement `activate()` and `deactivate()`:
   - POST `/killswitch?killSwitchStatus=ACTIVATE` or `DEACTIVATE`
   - Parse response: `status` ∈ {success, ok} → True
3. Define `KillSwitchPort` Protocol in domain:
   ```python
   class KillSwitchPort(Protocol):
       def activate(self) -> bool: ...
       def deactivate(self) -> bool: ...
   ```
4. Unit tests

**Acceptance Criteria:**
- [ ] Activate/deactivate work
- [ ] `allow_live_orders` guard applied
- [ ] Unit tests pass

---

#### T08: Trade Book / History Adapter

| Field | Value |
|---|---|
| **Priority** | P2 |
| **Gap Reference** | GAP-08 |
| **Effort** | 1 day |
| **Depends On** | — |

**Implementation Steps:**
1. Add `get_trade_book()` to `DhanOrders`:
   - GET `/trades`
   - Parse into `list[Trade]`
2. Add `get_trade_history(from_date, to_date, page)` to `DhanOrders`:
   - Validate date format (YYYY-MM-DD)
   - GET `/trades/{from}/{to}/{page}`
   - Parse into `list[Trade]`
3. Create `map_trade()` in mapper module
4. Define `TradeQueryPort` Protocol:
   ```python
   class TradeQueryPort(Protocol):
       def get_trade_book(self) -> list[Trade]: ...
       def get_trade_history(self, from_date: str, to_date: str, page: int = 0) -> list[Trade]: ...
   ```
5. Unit tests

**Acceptance Criteria:**
- [ ] Trade book returns today's trades
- [ ] Trade history validates date format
- [ ] Trade parsing handles all Dhan field names
- [ ] Unit tests pass

---

### Layer 2 — Service Layer Completion

---

#### T09: SuperOrderService

| Field | Value |
|---|---|
| **Priority** | P0 |
| **Gap Reference** | GAP-01 |
| **Effort** | 1 day |
| **Depends On** | T05 |

**Implementation Steps:**
1. Create `SuperOrderService` in `brokers/services/super_order_service.py`
2. Define `SuperOrderExecutionPort` Protocol
3. Implement `place_super_order()` with:
   - Pre-flight validation (target/SL direction)
   - Delegate to adapter via port
   - Publish `SUPER_ORDER_PLACED` event
4. Implement `modify_leg()`, `cancel_leg()`, `list_orders()`
5. Unit tests

**Acceptance Criteria:**
- [ ] Service validates before delegating
- [ ] Events published on state changes
- [ ] Unit tests pass

---

#### T10: ForeverOrderService

| Field | Value |
|---|---|
| **Priority** | P0 |
| **Gap Reference** | GAP-02 |
| **Effort** | 1 day |
| **Depends On** | T06 |

**Implementation Steps:**
1. Create `ForeverOrderService` in `brokers/services/forever_order_service.py`
2. Define `ForeverOrderExecutionPort` Protocol
3. Implement CRUD methods with validation
4. OCO field validation in service layer
5. Publish events on state changes
6. Unit tests

**Acceptance Criteria:**
- [ ] SINGLE and OCO flows work end-to-end
- [ ] OCO validation catches missing fields before adapter call
- [ ] Unit tests pass

---

#### T11: Wire Idempotency into OrderService

| Field | Value |
|---|---|
| **Priority** | P1 |
| **Gap Reference** | GAP-04 |
| **Effort** | 0.5 days |
| **Depends On** | T02 |

**Implementation Steps:**
1. Change `OrderService.__init__` to accept `IdempotencyCachePort` instead of `Any`
2. Generate `correlation_id` (UUID4) if not provided
3. Call `idempotency.check_and_set(correlation_id)` before executor call
4. On success, call `idempotency.put(correlation_id, response)`
5. On idempotency conflict, return `OrderResponse.already_executed()`
6. Unit tests:
   - First call → passes through
   - Duplicate call with same correlation_id → returns cached response
   - Concurrent calls → only one reaches executor

**Acceptance Criteria:**
- [ ] Type-safe (uses `IdempotencyCachePort`, not `Any`)
- [ ] Duplicate prevention works
- [ ] Unit tests pass

---

#### T12: Wire Risk Manager into OrderService

| Field | Value |
|---|---|
| **Priority** | P1 |
| **Gap Reference** | GAP-05 |
| **Effort** | 0.5 days |
| **Depends On** | T04 |

**Implementation Steps:**
1. Add `risk_manager: RiskManagerPort | None` to `OrderService.__init__`
2. Before calling executor, build preview `Order` and call `risk_manager.check_order(preview)`
3. If `not result.allowed`, return `OrderResponse.fail(result.reason, error_code="RISK_CHECK_FAILED")`
4. Unit tests:
   - No risk manager → order passes through
   - Risk manager allows → order proceeds
   - Risk manager rejects → `OrderResponse.fail()` returned

**Acceptance Criteria:**
- [ ] Risk check runs before every order placement
- [ ] Rejection returns structured error
- [ ] Optional (None risk manager = no check)
- [ ] Unit tests pass

---

#### T13: Wire Event Bus into OrderService

| Field | Value |
|---|---|
| **Priority** | P1 |
| **Gap Reference** | GAP-06 |
| **Effort** | 0.5 days |
| **Depends On** | T03 |

**Implementation Steps:**
1. Add `event_bus: EventBusPort | None` to `OrderService.__init__`
2. After successful placement, publish `DomainEvent("ORDER_PLACED", {...}, symbol=symbol)`
3. After successful cancellation, publish `DomainEvent("ORDER_CANCELLED", {...})`
4. Unit tests:
   - Event published on place success
   - No event on place failure
   - Event published on cancel success

**Acceptance Criteria:**
- [ ] Events published for all state changes
- [ ] Optional (None event bus = no publish)
- [ ] Unit tests pass

---

### Layer 3 — Streaming + Reconciliation

---

#### T14: Conditional Trigger Validation

| Field | Value |
|---|---|
| **Priority** | P2 |
| **Gap Reference** | GAP-07 |
| **Effort** | 0.5 days |
| **Depends On** | — |

**Implementation Steps:**
1. Add validation to `DhanConditionalTriggers.place_conditional_order()`:
   - `operator` ∈ {CROSSING_UP, CROSSING_DOWN, GREATER_THAN, LESS_THAN}
   - `comparison_type` == "PRICE_WITH_VALUE" (only supported type)
   - `comparing_value` > 0
2. Raise `OrderRejectedError` on validation failure
3. Unit tests

**Acceptance Criteria:**
- [ ] Invalid operator rejected before API call
- [ ] Non-PRICE_WITH_VALUE comparison type rejected
- [ ] Unit tests pass

---

#### T15: Conditional Trigger Modify/Get

| Field | Value |
|---|---|
| **Priority** | P3 |
| **Gap Reference** | GAP-13 |
| **Effort** | 0.5 days |
| **Depends On** | — |

**Implementation Steps:**
1. Add `modify_conditional_order(alert_id, ...)` to `DhanConditionalTriggers`:
   - PUT `/conditionalOrders/{alert_id}`
2. Add `get_conditional_order(alert_id)` to `DhanConditionalTriggers`:
   - GET `/conditionalOrders/{alert_id}`
3. Parse responses into `ConditionalTrigger` entity (use T01 entity)
4. Unit tests

**Acceptance Criteria:**
- [ ] Modify and get-by-ID work
- [ ] Response parsing into domain entity
- [ ] Unit tests pass

---

#### T16: WebSocket → State Machine Integration

| Field | Value |
|---|---|
| **Priority** | P1 |
| **Gap Reference** | — |
| **Effort** | 1 day |
| **Depends On** | — |

**Implementation Steps:**
1. Create `OrderUpdateHandler` in `brokers/services/order_update_handler.py`:
   - Receives `Order` from `DhanOrderStream.on_order_update`
   - Looks up current state in local ledger
   - Calls `validate_transition(current_status, new_status)` from `order_lifecycle.py`
   - On valid transition: updates ledger, publishes domain event
   - On invalid transition: logs warning, publishes `INVALID_TRANSITION` alert
2. Wire `DhanOrderStream.on_order_update = handler.handle_update`
3. Unit tests:
   - OPEN → FILLED: valid, ledger updated
   - FILLED → OPEN: invalid, alert raised
   - Unknown order: added to ledger as new

**Acceptance Criteria:**
- [ ] All incoming updates validated against state machine
- [ ] Invalid transitions logged and alerted
- [ ] Ledger kept consistent
- [ ] Unit tests pass

---

#### T17: Reconciliation Engine Implementation

| Field | Value |
|---|---|
| **Priority** | P1 |
| **Gap Reference** | GAP-10 |
| **Effort** | 2 days |
| **Depends On** | T16, T03 |

**Implementation Steps:**
1. Implement `_sync_orders()` in `ReconciliationEngine`:
   - Fetch full order book via `BrokerGateway.get_orderbook()`
   - Build broker state dict: `{order_id: Order}`
   - Compare against `local_order_ledger`
2. Drift detection:
   - **Missing broker order:** In local but not in broker → raise `HIGH` alert, remove from local
   - **Missing local order:** In broker but not in local → add to local, synthesize `ORDER_DISCOVERED` event
   - **Status mismatch:** Same ID, different status → validate transition, update local, raise `MEDIUM` alert if invalid
3. Define `LocalOrderLedgerPort` Protocol:
   ```python
   class LocalOrderLedgerPort(Protocol):
       def get(self, order_id: str) -> Order | None: ...
       def put(self, order: Order) -> None: ...
       def remove(self, order_id: str) -> None: ...
       def all_orders(self) -> dict[str, Order]: ...
   ```
4. Implement `InMemoryOrderLedger`
5. Wire `ReconciliationEngine` to `EventBusPort` for drift alerts
6. Unit tests:
   - Normal sync: no drift
   - Missing broker order: detected, alert raised
   - Missing local order: synthesized, added
   - Status mismatch: validated, updated

**Acceptance Criteria:**
- [ ] Full sync loop works
- [ ] All three drift types detected and handled
- [ ] Alerts published via event bus
- [ ] Unit tests pass

---

### Layer 4 — Hardening

---

#### T18: Cancel Error Response Parsing

| Field | Value |
|---|---|
| **Priority** | P3 |
| **Gap Reference** | GAP-14 |
| **Effort** | 0.5 days |
| **Depends On** | — |

**Implementation Steps:**
1. Update `DhanOrders.cancel_order()` to parse broker response body:
   - Check `data.get("status")` ∈ {success, ok} → success
   - Otherwise extract `errorCode` and `errorMessage`
   - Return `OrderResponse.fail(message, error_code=error_code)`
2. Unit tests:
   - Success response → `OrderResponse(success=True)`
   - Error response → `OrderResponse(success=False, error_code="...")`
   - Malformed response → `OrderResponse(success=False, error_code="MALFORMED_RESPONSE")`

**Acceptance Criteria:**
- [ ] Broker error codes surfaced in `OrderResponse.error_code`
- [ ] Unit tests pass

---

#### T19: Slice Orders Adapter

| Field | Value |
|---|---|
| **Priority** | P3 |
| **Gap Reference** | GAP-11 |
| **Effort** | 0.5 days |
| **Depends On** | — |

**Implementation Steps:**
1. Add `place_slice_order()` to `DhanOrders`:
   - POST to `/orders/slicing`
   - Same payload structure as `place_order()`
   - No idempotency/risk (broker-managed)
2. Unit tests

**Acceptance Criteria:**
- [ ] Slice order placement works
- [ ] Invariant assertion called
- [ ] Unit tests pass

---

#### T20: Exit-All Native Endpoint

| Field | Value |
|---|---|
| **Priority** | P2 |
| **Gap Reference** | — |
| **Effort** | 0.5 days |
| **Depends On** | — |

**Implementation Steps:**
1. Add `exit_all_native()` to `DhanExitAll`:
   - POST `/exitall`
   - Parse `ExitAllResponse` (positions_closed, orders_cancelled, success)
2. Make native the primary; keep manual as fallback
3. Create `ExitAllResponse` domain entity
4. Unit tests

**Acceptance Criteria:**
- [ ] Native endpoint used as primary
- [ ] Manual fallback available
- [ ] Response parsed into domain entity
- [ ] Unit tests pass

---

#### T21: Integration Test Suite

| Field | Value |
|---|---|
| **Priority** | P1 |
| **Gap Reference** | — |
| **Effort** | 2 days |
| **Depends On** | T05-T17 |

**Implementation Steps:**
1. Create `tests/integration/test_order_lifecycle.py`:
   - Place → modify → cancel flow
   - Place → fill (mocked) → verify state machine
   - Idempotency: duplicate call returns cached response
   - Risk check: rejection prevents placement
2. Create `tests/integration/test_super_order_lifecycle.py`:
   - Place → modify leg → cancel leg flow
3. Create `tests/integration/test_forever_order_lifecycle.py`:
   - SINGLE place → modify → cancel
   - OCO place → modify → cancel
4. Create `tests/integration/test_reconciliation.py`:
   - Sync with drift scenarios
5. Create `tests/integration/test_order_stream.py`:
   - WebSocket message → state machine → ledger update

**Acceptance Criteria:**
- [ ] All integration tests pass
- [ ] Coverage > 80% for order management code
- [ ] Tests run in < 30 seconds

---

#### T22: Status Mapper Registry

| Field | Value |
|---|---|
| **Priority** | P3 |
| **Gap Reference** | GAP-09 |
| **Effort** | 0.5 days |
| **Depends On** | — |

**Implementation Steps:**
1. Create `StatusMapperRegistry` in `brokers/domain/status_mapper.py`:
   - `register(broker_id: str, mappings: dict[str, OrderStatus])`
   - `get(broker_id: str) -> dict[str, OrderStatus]`
2. Register Dhan mappings in `brokers/adapters/dhan/status_mapper.py`
3. Update `map_order()` to use registry instead of inline mapping
4. Unit tests

**Acceptance Criteria:**
- [ ] Registry supports multiple brokers
- [ ] Dhan mappings registered at init
- [ ] Unit tests pass

---

## 3. Parallelization Opportunities

| Parallel Group | Tasks | Rationale |
|---|---|---|
| **Group A** (Foundation) | T01, T02, T03, T04 | All independent; can be done in parallel by 4 developers |
| **Group B** (Adapters) | T05, T06, T07, T08 | All independent adapters; can be done in parallel after Group A |
| **Group C** (Services) | T09, T10, T11, T12, T13 | T09 depends on T05; T10 depends on T06; T11-T13 depend on T02-T04. After their deps, all parallel |
| **Group D** (Streaming/Recon) | T14, T15, T16 | T14 and T15 independent; T16 independent. All parallel |
| **Group E** (Hardening) | T18, T19, T20, T22 | All independent; can be done in parallel |
| **Sequential** | T17 (after T16), T21 (after all) | Must wait for dependencies |

**Maximum parallelism:** 4 developers can work concurrently through most of the plan.

---

## 4. Critical Path Analysis

```
Critical Path (longest chain):

T01 (1d) → T05 (2d) → T09 (1d) → T21 (2d) = 6 days
T01 (1d) → T06 (2d) → T10 (1d) → T21 (2d) = 6 days

Secondary Path:
T04 (1d) → T12 (0.5d) → T21 (2d) = 3.5 days
T02 (1d) → T11 (0.5d) → T21 (2d) = 3.5 days
T03 (1d) → T13 (0.5d) → T17 (2d) → T21 (2d) = 5.5 days

Streaming Path:
T16 (1d) → T17 (2d) → T21 (2d) = 5 days
```

**Critical path duration:** 6 days (with 4 developers working in parallel)  
**Bottleneck:** T01 (domain entities) blocks both Super Orders and Forever Orders  
**Second bottleneck:** T21 (integration tests) blocks on everything

---

## 5. Execution Summary

| Metric | Value |
|---|---|
| **Total tasks** | 22 |
| **Total effort** | ~22 person-days |
| **Critical path** | 6 days (4 developers) |
| **P0 tasks** | 5 (T01, T05, T06, T09, T10) |
| **P1 tasks** | 8 (T02, T03, T04, T07, T11, T12, T13, T16, T17, T21) |
| **P2 tasks** | 3 (T08, T14, T20) |
| **P3 tasks** | 5 (T15, T18, T19, T22) |
| **Parallelizable** | 80% of tasks can run in parallel within their layer |

### Recommended Execution Order

| Day | Developer 1 | Developer 2 | Developer 3 | Developer 4 |
|---|---|---|---|---|
| 1 | T01 (entities) | T02 (idempotency) | T03 (event bus) | T04 (risk mgr) |
| 2 | T05 (super orders) | T06 (forever orders) | T07 (kill switch) | T08 (trade book) |
| 3 | T09 (super svc) | T10 (forever svc) | T11 (wire idem) | T12 (wire risk) |
| 4 | T13 (wire events) | T14 (trigger valid) | T15 (trigger mod/get) | T16 (WS→state) |
| 5 | T17 (reconciliation) | T18 (cancel parse) | T19 (slice orders) | T20 (exit-all native) |
| 6 | T22 (status registry) | T21 (integration tests — all) | — | — |

**Day 6** is dedicated to integration testing and any remaining hardening tasks.
