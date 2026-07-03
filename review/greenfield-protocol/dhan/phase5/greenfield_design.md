# Phase 5 — Order Management: Greenfield Design Document

> **Protocol:** Greenfield Broker Replication — Dhan  
> **Phase:** 5 (Order Management)  
> **Date:** 2026-07-03

---

## 1. Architecture Overview

### 1.1 Archive Architecture (Monolithic)

The archive implements order management as a set of **fat adapter classes** that each own their full lifecycle:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Consumer (CLI / UI)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────────┐
        │                    │                         │
   OrdersAdapter    SuperOrdersAdapter    ForeverOrdersAdapter
   (725 lines)      (334 lines)           (291 lines)
        │                    │                         │
        │    ConditionalTriggersAdapter    ExitAllAdapter
        │    (269 lines)                  (55 lines)
        │                    │                         │
        └────────────────────┼─────────────────────────┘
                             │
                    DhanHttpClient (shared)
                             │
                    Dhan REST API
```

Each adapter:
- Owns validation, payload building, API call, response parsing, and logging
- Directly imports from `brokers.common.*` (idempotency, validation, DTOs)
- Directly imports domain entities from `domain.*`
- Has its own error hierarchy (`SuperOrderError`, `ForeverOrderError`, etc.)
- Calls `assert_dhan_payload()` inline before every HTTP call

**Key characteristics:**
- Validation is co-located with the adapter (no separate service layer)
- Idempotency cache is owned by the adapter
- Risk manager is injected into the adapter
- Event bus publishing happens inside the adapter
- Status mapping uses a registry pattern (`StatusMapperRegistry`)

### 1.2 Greenfield Architecture (Layered)

The greenfield separates concerns into **domain → ports → adapters → services**:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Consumer (CLI / UI)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    │  Service Layer   │
                    │  OrderService    │
                    │  (validation,    │
                    │   idempotency)   │
                    └────────┬────────┘
                             │ OrderExecutionPort (Protocol)
                    ┌────────┴────────┐
                    │  Adapter Layer   │
                    │  DhanOrders      │
                    │  DhanExitAll     │
                    │  DhanCond.Trig.  │
                    │  DhanOrderStream │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         DhanHttpClient  DhanMapper   DhanInvariants
              │              │              │
              └──────────────┼──────────────┘
                             │
                    Dhan REST API / WebSocket
```

**Key characteristics:**
- `OrderExecutionPort` (Protocol) defines the contract; `DhanOrders` implements it
- `OrderService` sits above the port, adding validation, idempotency, and logging
- Domain entities (`Order`, `OrderResponse`, `Trade`) are frozen dataclasses with zero infrastructure deps
- `order_lifecycle.py` provides a formal state machine (archive lacks this)
- Adapter returns domain types; service translates errors into domain exceptions

---

## 2. Improvements Over Archive

| # | Improvement | Description |
|---|---|---|
| 1 | **Formal state machine** | `order_lifecycle.py` defines legal status transitions. Archive has no transition validation. |
| 2 | **Port-based adapter contract** | `OrderExecutionPort` is a `Protocol` — any broker adapter can be swapped without changing the service. Archive's `OrdersAdapter` is a concrete class. |
| 3 | **Frozen domain entities** | All entities are `@dataclass(frozen=True)` — immutable value objects. Archive entities are mutable. |
| 4 | **Structured exception hierarchy** | `OrderRejectedError`, `NetworkError`, `RateLimitError`, etc. with error codes. Archive uses generic `OrderError`. |
| 5 | **Post-cancel race detection** | `DhanOrders.cancel_order()` re-fetches the order after cancel to detect FILLED race. Archive doesn't. |
| 6 | **Concurrent exit-all** | `DhanExitAll` uses `ThreadPoolExecutor` for parallel position squaring. Archive uses single bulk API call (faster but all-or-nothing). |
| 7 | **WebSocket order streaming** | `DhanOrderStream` provides real-time order updates. Archive has no streaming. |
| 8 | **Reconciliation engine** | `ReconciliationEngine` provides background state sync. Archive has no reconciliation. |
| 9 | **Decoupled validation** | `order_validation.py` is a standalone module with pure functions. Archive co-locates validation in the adapter. |
| 10 | **Error code constants** | `error_codes.py` defines canonical error codes. Archive uses string literals. |

---

## 3. Dropped Behaviors (Gaps)

### 3.1 Critical Gaps (P0)

| Gap ID | Behavior | Archive Source | Impact |
|---|---|---|---|
| GAP-01 | **Super Orders (bracket/cover)** | `super_orders.py` (334 lines) | Cannot place bracket orders with entry+target+SL legs. Trading strategies that rely on automated profit-booking and stop-loss are blocked. |
| GAP-02 | **Forever Orders (GTD SINGLE/OCO)** | `forever_orders.py` (291 lines) | Cannot place Good-Till-Triggered orders with OCO (One-Cancels-Other) semantics. Long-term conditional strategies are blocked. |
| GAP-03 | **Kill switch** | `orders.py` `kill_switch()` | Cannot activate/deactivate Dhan's kill switch via API. Emergency position liquidation via broker-side mechanism is unavailable. |

### 3.2 High-Priority Gaps (P1)

| Gap ID | Behavior | Archive Source | Impact |
|---|---|---|---|
| GAP-04 | **Idempotency cache (concrete)** | `orders.py` — `SimpleIdempotencyCache` | Service accepts `idempotency_cache: Any` but no implementation is wired. Retry storms could cause duplicate orders. |
| GAP-05 | **Risk manager integration** | `orders.py` — `risk_manager.check_order()` | No pre-trade risk check in greenfield order path. Over-leveraged or oversized orders can reach the exchange. |
| GAP-06 | **Event bus publishing** | `orders.py` — `_publish("ORDER_PLACED", order)` | Downstream consumers (notifications, analytics, audit) receive no order events. |

### 3.3 Medium-Priority Gaps (P2)

| Gap ID | Behavior | Archive Source | Impact |
|---|---|---|---|
| GAP-07 | **Conditional trigger validation** | `conditional_triggers.py` — operator + comparison_type checks | Invalid triggers can be submitted to the API, wasting rate limits and potentially creating unintended positions. |
| GAP-08 | **Trade book / trade history** | `orders.py` — `get_trade_book()`, `get_trade_history()` | Cannot query executed trades for reconciliation, P&L calculation, or tax reporting. |
| GAP-09 | **Status mapper registry** | `status_mapper.py` — `StatusMapperRegistry` | Greenfield uses direct mapper function. Adding a second broker requires code changes rather than registration. |
| GAP-10 | **Reconciliation (implementation)** | N/A (greenfield-only) | `ReconciliationEngine._sync_orders()` is a stub. Ghost fills and dropped WS events go undetected. |

### 3.4 Low-Priority Gaps (P3)

| Gap ID | Behavior | Archive Source | Impact |
|---|---|---|---|
| GAP-11 | **Slice orders** | `orders.py` — `place_slice_order()` | Large orders cannot be auto-split by the broker. Manual slicing required. |
| GAP-12 | **Order status convenience method** | `orders.py` — `get_order_status()` | Minor ergonomic gap. Consumer must call `get_order()` and extract `.status`. |
| GAP-13 | **Conditional trigger modify/get-by-ID** | `conditional_triggers.py` — `modify_trigger()`, `get_trigger()` | Cannot update or query individual triggers. Must cancel and re-place. |
| GAP-14 | **Cancel error response parsing** | `orders.py` — parses `errorCode`/`errorMessage` from cancel response | Cancel failures return generic error instead of broker-specific error code. |

---

## 4. Key Architectural Decisions

### 4.1 Service Layer vs Direct Adapter Calls

**Decision:** Greenfield introduces `OrderService` as an application service between the consumer and the adapter.

**Rationale:**
- Archive's fat adapters mix validation, idempotency, risk, and event publishing with HTTP transport
- Greenfield's `OrderService` owns cross-cutting concerns; adapter owns only HTTP transport
- `OrderExecutionPort` (Protocol) enables testing with a fake adapter and swapping brokers without changing service logic

**Trade-offs:**
- Extra indirection layer adds complexity for simple pass-through operations
- `OrderService` currently duplicates some validation that the adapter also does (e.g., `allow_live_orders` check)

**Recommendation:** Keep the service layer. Move ALL validation to the service; adapter should only build payloads and parse responses.

### 4.2 Order Validation Approach (Pre-flight vs Server-side)

**Decision:** Greenfield uses **pre-flight validation** in `order_validation.py` (pure functions) called by `OrderService`.

**Rationale:**
- Archive validates inside the adapter, mixing domain rules with transport concerns
- Greenfield's pure-function validators are testable in isolation and reusable across adapters
- Validation is split into:
  - `validate_order_fields()` — required fields, positive quantities, LIMIT requires price
  - `validate_lot_size()` — derivative lot size multiples
  - `validate_tick_alignment()` — price tick size compliance
  - `validate_product_segment()` — product type × exchange compatibility
  - `check_notional_warning()` — high-value order warning (non-blocking)

**Trade-offs:**
- Archive resolves the instrument inside validation to check lot size; greenfield passes `lot_size` and `tick_size` as constructor params to `OrderService` — this means the service doesn't resolve instruments itself, which is cleaner but requires the caller to provide instrument metadata
- Pre-flight validation cannot catch server-side rejections (insufficient margin, circuit breaker, etc.)

**Recommendation:** Add a `validate_instrument()` method to `OrderService` that resolves the instrument and checks lot/tick from the resolved metadata, rather than relying on constructor params.

### 4.3 Reconciliation Strategy

**Decision:** Greenfield implements `ReconciliationEngine` as an async background daemon with a configurable sync interval.

**Current state:** Stub implementation. The `_sync_orders()` method is a `pass`.

**Intended design:**
1. Periodically fetch full order book from broker (`BrokerGateway.get_all_orders()`)
2. Compare against `local_order_ledger` (in-memory dict)
3. Detect drift:
   - **Missing broker order:** Local ledger has an order the broker doesn't know about → raise `HIGH` severity alert
   - **Missing local order:** Broker has an order not in local ledger → synthesize state transition, add to ledger
   - **Status mismatch:** Same order, different status → raise `MEDIUM` severity alert
4. Reconcile by updating local ledger to match broker state

**Trade-offs:**
- Async loop is lightweight but shares the event loop with other tasks — a slow reconciliation could block order processing
- In-memory ledger is lost on restart — needs persistence for production

**Recommendation:** 
- Implement `_sync_orders()` with the `BrokerGateway` port
- Add a `LocalOrderLedger` port with both in-memory and SQLite implementations
- Emit reconciliation events via the domain event bus (once wired)

### 4.4 Order Streaming Integration

**Decision:** Greenfield implements `DhanOrderStream` as a WebSocket client extending `BaseWebSocketStreaming`.

**Design:**
- Connects to `wss://api-order-update.dhan.co`
- Sends auth message on connect (`LoginReq` with `MsgCode: 42`)
- Parses incoming messages via `map_order()` (reuses the same mapper as REST)
- Fires `on_order_update` callback with parsed `Order` entity

**Integration gaps:**
- No consumer of `on_order_update` is wired — the callback is set but nothing connects it to the reconciliation engine or order service
- No reconnection-state reconciliation — when WS reconnects after a drop, it doesn't fetch missed updates
- No order state machine validation — incoming status updates are not validated against `order_lifecycle.py`

**Recommendation:**
- Create an `OrderUpdateHandler` that:
  1. Validates the status transition against `order_lifecycle.py`
  2. Updates the local order ledger
  3. Fires domain events for state changes
  4. Feeds the reconciliation engine with the latest known state

---

## 5. Design Principles Applied

| Principle | Application |
|---|---|
| **Dependency Inversion** | `OrderService` depends on `OrderExecutionPort` (Protocol), not on `DhanOrders` (concrete). |
| **Single Responsibility** | Each adapter handles one API domain (orders, exits, triggers, streaming). Validation is in its own module. |
| **Immutable Value Objects** | All domain entities are `@dataclass(frozen=True)`. State changes produce new objects. |
| **Explicit Error Codes** | `error_codes.py` defines string constants. No bare string literals in error paths. |
| **Defense in Depth** | `assert_valid_dhan_payload()` at the adapter boundary, even though the resolver already enforces the contract. |
| **Fail-Safe Defaults** | `allow_live_orders` defaults to `True` in `DhanOrders` (archive defaults to `False`). This is a regression — should default to `False`. |
| **Separation of Concerns** | Transport (HTTP client) is separate from domain logic (order building) is separate from application logic (validation, idempotency). |
| **Interface Segregation** | `OrderExecutionPort` has only 4 methods (place, cancel, get, orderbook). No fat interface. |

---

## 6. Recommended Architecture for Greenfield Order Management

### 6.1 Target Layer Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Consumer Layer                               │
│   (CLI commands, UI handlers, strategy engines, API endpoints)        │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
┌────────────────────────────────┴─────────────────────────────────────┐
│                       Application Service Layer                       │
│                                                                       │
│  ┌──────────────┐  ┌──────────────────┐  ┌────────────────────────┐  │
│  │ OrderService  │  │ TriggerService   │  │ ExitAllService         │  │
│  │               │  │                  │  │                        │  │
│  │ - validate    │  │ - validate       │  │ - close_all_positions  │  │
│  │ - idempotency │  │ - CRUD dispatch  │  │ - cancel_all_orders    │  │
│  │ - risk check  │  │ - response parse │  │ - error aggregation    │  │
│  │ - event emit  │  │                  │  │                        │  │
│  └──────┬───────┘  └────────┬─────────┘  └───────────┬────────────┘  │
│         │                    │                         │               │
└─────────┼────────────────────┼─────────────────────────┼──────────────┘
          │                    │                         │
┌─────────┼────────────────────┼─────────────────────────┼──────────────┐
│         │       Port Layer   │                         │               │
│         │                    │                         │               │
│  OrderExecutionPort   TriggerExecutionPort     ExitAllPort             │
│  (Protocol)           (Protocol)               (Protocol)              │
│         │                    │                         │               │
└─────────┼────────────────────┼─────────────────────────┼──────────────┘
          │                    │                         │
┌─────────┼────────────────────┼─────────────────────────┼──────────────┐
│         │    Adapter Layer   │                         │               │
│         │                    │                         │               │
│  ┌──────┴───────┐  ┌────────┴─────────┐  ┌───────────┴────────────┐  │
│  │ DhanOrders    │  │DhanCondTriggers  │  │ DhanExitAll            │  │
│  │               │  │                  │  │                        │  │
│  │ - payload     │  │ - payload build  │  │ - concurrent square-off│  │
│  │ - HTTP call   │  │ - HTTP call      │  │ - concurrent cancel    │  │
│  │ - parse resp  │  │ - parse resp     │  │ - error aggregation    │  │
│  │ - invariants  │  │ - invariants     │  │                        │  │
│  └──────────────┘  └──────────────────┘  └────────────────────────┘  │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ DhanOrderStream (WebSocket)                                   │     │
│  │ - real-time order updates                                     │     │
│  │ - auth handshake                                              │     │
│  │ - reconnect with backoff                                      │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
          │
┌─────────┼────────────────────────────────────────────────────────────┐
│         │    Cross-Cutting Concerns                                   │
│         │                                                             │
│  ┌──────┴─────────────────────────────────────────────────────────┐  │
│  │ ReconciliationEngine                                            │  │
│  │ - periodic broker-state sync                                    │  │
│  │ - drift detection                                               │  │
│  │ - missing-state synthesis                                       │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────┐  │
│  │ IdempotencyCache  │  │ RiskManager      │  │ EventBus           │  │
│  │ (Redis / in-mem)  │  │ (pre-trade)      │  │ (domain events)    │  │
│  └──────────────────┘  └──────────────────┘  └────────────────────┘  │
│                                                                       │
│  ┌──────────────────┐  ┌──────────────────┐                          │
│  │ OrderStateMachine │  │ InvariantAssert  │                          │
│  │ (transition rules)│  │ (payload safety) │                          │
│  └──────────────────┘  └──────────────────┘                          │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### 6.2 Missing Subsystems to Port

| Subsystem | Priority | Effort | Description |
|---|---|---|---|
| Super Orders | P0 | 3-4 days | Full bracket order lifecycle: place, modify per-leg, cancel per-leg, list. Needs `SuperOrder` and `SuperOrderLeg` domain entities. |
| Forever Orders | P0 | 2-3 days | GTD order lifecycle with SINGLE/OCO modes. Needs `ForeverOrder` domain entity. May be lower priority if Dhan has deprecated this API. |
| Kill Switch | P1 | 0.5 days | Simple POST to `/killswitch`. Needs `KillSwitchPort` in domain. |
| Trade Book | P2 | 1 day | `get_trade_book()` and `get_trade_history()` in adapter + service. Needs `Trade` query port. |
| Slice Orders | P3 | 1 day | POST to `/orders/slicing`. Can be added to `DhanOrders` as a new method. |

### 6.3 Integration Points

| Integration | From | To | Status |
|---|---|---|---|
| Order stream → Reconciliation | `DhanOrderStream.on_order_update` | `ReconciliationEngine.local_order_ledger` | **Not wired** |
| Order stream → State machine | `DhanOrderStream.on_order_update` | `order_lifecycle.validate_transition()` | **Not wired** |
| Order service → Event bus | `OrderService.place_order()` | `EventBus.publish("ORDER_PLACED")` | **Not wired** |
| Order service → Risk manager | `OrderService.place_order()` | `RiskManager.check_order()` | **Not wired** |
| Order service → Idempotency | `OrderService.place_order()` | `IdempotencyCache.check_and_set()` | **Interface exists, no impl** |
| Reconciliation → Alert system | `ReconciliationEngine._sync_orders()` | Drift alerts | **Stub** |

---

## 7. Summary

The greenfield architecture is **structurally superior** to the archive — cleaner separation of concerns, formal state machine, port-based extensibility, and immutable entities. However, it has **significant behavioral gaps**:

1. **Two entire order subsystems** (Super Orders, Forever Orders) are not ported
2. **Critical cross-cutting concerns** (idempotency, risk, events) are stubbed or missing
3. **Reconciliation engine** exists as a skeleton with no implementation
4. **WebSocket streaming** exists but is not integrated with the state machine or reconciliation

The recommended path forward is to:
1. Port the missing subsystems (Super Orders → Forever Orders → Kill Switch)
2. Wire the cross-cutting concerns (idempotency → risk → events)
3. Implement reconciliation
4. Integrate WebSocket streaming with the state machine and reconciliation
