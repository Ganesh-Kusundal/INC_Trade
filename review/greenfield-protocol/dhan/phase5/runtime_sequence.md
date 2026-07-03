# Phase 5 — Runtime Sequences
## Greenfield Broker Replication Protocol — Dhan Order Management

---

## 1. Order Placement Flow

### Archive Flow

```
┌──────────┐     ┌───────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│ OrdersAdapter │────▶│ DhanHttpClient│────▶│ Dhan REST API│
└──────────┘     └───────────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ IdempotencyCache│
                 │ (check-then-act)│
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ validate_order()│
                 │ - lot size      │
                 │ - tick align    │
                 │ - product×seg   │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ RiskManager     │
                 │ .check_order()  │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ identity.resolve│
                 │ → DhanInstrument│
                 │   Ref (carrier) │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │_build_payload() │
                 │ assert_dhan_    │
                 │  payload()      │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ _client.post()  │
                 │ POST /orders    │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │_build_placed_   │
                 │ order() → Order │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ idempotency.put │
                 │ event_bus.publish│
                 │ ORDER_PLACED    │
                 └─────────────────┘
```

**Steps (Archive):**
1. Check `allow_live_orders` flag — reject if disabled
2. Generate `correlation_id` if not provided (UUID4)
3. Acquire idempotency lock; check cache for duplicate
4. Run `validate_order()` — lot size, tick alignment, product×segment
5. Run `validate_order_warnings()` — high notional warning
6. Resolve instrument via `DhanIdentityProvider.resolve_ref()` → `DhanInstrumentRef`
7. Canonicalize enums via `canonicalize_order_enums()`
8. Run pre-trade risk check via `RiskManagerPort.check_order()` (if configured)
9. Build payload dict via `_build_order_payload()`
10. Assert payload invariant via `assert_dhan_payload()`
11. POST to `/orders`
12. Parse response into `Order` domain object
13. Cache response in idempotency cache
14. Publish `ORDER_PLACED` domain event
15. Return `OrderResponse.ok()`

### Greenfield Flow

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│ OrderService │────▶│ DhanOrders   │────▶│ DhanHttpClient│
└──────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                        │                    │
                        ▼                    ▼
                 ┌──────────────┐     ┌─────────────────┐
                 │order_valid.  │     │assert_valid_    │
                 │.validate_    │     │dhan_payload()   │
                 │order_fields()│     └─────────────────┘
                 │.validate_    │              │
                 │lot_size()    │              ▼
                 │.validate_    │     ┌─────────────────┐
                 │tick_align()  │     │map_order_       │
                 │.validate_    │     │response()       │
                 │product_seg() │     └─────────────────┘
                 │.check_       │
                 │notional_warn │
                 └──────────────┘
```

**Steps (Greenfield):**
1. `OrderService.place_order()` — entry point
2. `validate_order_fields()` — symbol, exchange, quantity, price, trigger_price
3. `validate_product_segment()` — product × exchange compatibility
4. `validate_lot_size()` — if lot_size > 0
5. `validate_tick_alignment()` — if tick_size > 0 and price > 0
6. `check_notional_warning()` — log warning if notional > threshold
7. Check idempotency cache (if provided) — return `already_executed` on conflict
8. Delegate to `OrderExecutionPort.place_order()` → `DhanOrders.place_order()`
9. Check `allow_live_orders` flag
10. Resolve instrument via `DhanInstrumentResolver.resolve()` → `DhanInstrumentRef`
11. Build payload with mapped enums (SIDE_MAP, ORDER_TYPE_MAP, etc.)
12. Assert `assert_valid_dhan_payload()`
13. POST to `/orders` via `DhanHttpClient`
14. Map response via `map_order_response()`
15. Return `OrderResponse` to service layer for logging

### Comparison

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| Validation location | Inline in adapter | Extracted to service layer | ✓ Clean separation |
| Risk manager check | Yes (RiskManagerPort) | No | **MISSING** |
| Idempotency | Built-in IdempotencyCache | Optional, passed in | ✓ More flexible |
| Identity carrier | DhanInstrumentRef | DhanInstrumentRef | ✓ Same pattern |
| Invariant assertion | `assert_dhan_payload` | `assert_valid_dhan_payload` | ✓ Equivalent |
| Event publishing | Yes (EventBus) | No | **MISSING** |
| Correlation ID | Auto-generated UUID | Passed by caller | Partial gap |
| Response mapping | Manual construction | `map_order_response()` | ✓ Cleaner |

---

## 2. Order Modification Flow

### Archive Flow

```
┌──────────┐     ┌───────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│ OrdersAdapter │────▶│ DhanHttpClient│────▶│ Dhan REST API│
└──────────┘     └───────────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │allow_live_orders│
                 │ check           │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ PUT /orders/    │
                 │ {order_id}      │
                 │ json=changes    │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ Check errorCode │
                 │ in response     │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ Order.from_     │
                 │ broker_dict()   │
                 │ (fallback if    │
                 │  parse fails)   │
                 └─────────────────┘
```

**Steps (Archive):**
1. Check `allow_live_orders` flag
2. Filter out None values from `**changes`
3. PUT `/orders/{order_id}` with payload
4. Check for `errorCode` in response → raise `OrderError` if present
5. Parse response via `Order.from_broker_dict()` with field mapping
6. Fallback: construct `Order` from partial response + changes

### Greenfield Flow

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│ DhanOrders   │────▶│ DhanHttpClient│────▶│ Dhan REST API│
└──────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │allow_live_orders│
                 │ check           │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ Build payload:  │
                 │ quantity, price,│
                 │ orderType,      │
                 │ validity        │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ POST endpoint   │
                 │ (modify_order)  │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │map_order_       │
                 │response()       │
                 └─────────────────┘
```

**Steps (Greenfield):**
1. Check `allow_live_orders` flag
2. Build payload from non-None parameters (quantity, price, order_type, validity)
3. POST to modify endpoint (note: uses POST, not PUT)
4. Map response via `map_order_response()`

### Comparison

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| HTTP method | PUT | POST | **INCONSISTENCY** — Dhan API uses PUT |
| Error handling | Raises `OrderError` | Returns `OrderResponse` | Different philosophy |
| Parse fallback | Yes (partial response) | No | **MISSING** fallback |
| Validation | None (pass-through) | None | Same |
| Logging | Yes (order_modified) | No | **MISSING** |

---

## 3. Order Cancellation Flow

### Archive Flow

```
┌──────────┐     ┌───────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│ OrdersAdapter │────▶│ DhanHttpClient│────▶│ Dhan REST API│
└──────────┘     └───────────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │allow_live_orders│
                 │ check           │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ DELETE /orders/ │
                 │ {order_id}      │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ Check response  │
                 │ status ∈        │
                 │ {"success","ok"}│
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ Return ok() or  │
                 │ fail() with     │
                 │ errorCode       │
                 └─────────────────┘
```

**Steps (Archive):**
1. Check `allow_live_orders` flag
2. DELETE `/orders/{order_id}`
3. Catch network errors → return `R.fail()` with BRO_ERR_CONNECTION_FAILED
4. Validate response is dict
5. Check `status` field ∈ {"success", "ok"}
6. Return `OrderResponse.ok()` or `OrderResponse.fail()` with error details

### Greenfield Flow

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│ DhanOrders   │────▶│ DhanHttpClient│────▶│ Dhan REST API│
└──────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │allow_live_orders│
                 │ check           │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ POST cancel     │
                 │ endpoint        │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ get_order()     │
                 │ (verify cancel) │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ Check if FILLED │
                 │ (post-cancel    │
                 │  race detect)   │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ Return success  │
                 │ or race warning │
                 └─────────────────┘
```

**Steps (Greenfield):**
1. Check `allow_live_orders` flag
2. POST to cancel endpoint
3. Re-fetch order via `get_order()`
4. Check if order is already FILLED (post-cancel race detection)
5. Return success or race warning

### Comparison

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| HTTP method | DELETE | POST | **INCONSISTENCY** |
| Race detection | No | Yes (get after cancel) | ✓ Greenfield better |
| Network error handling | Returns fail response | Raises exception | Different |
| Status parsing | Checks status field | No response parsing | **MISSING** |

---

## 4. Bracket/Cover Order Flow (Super Orders)

### Archive Flow

```
┌──────────┐     ┌──────────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│SuperOrdersAdapter│────▶│ DhanHttpClient│────▶│ Dhan REST API│
└──────────┘     └──────────────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
                 ┌─────────────────────┐
                 │_validate_super_order│
                 │ BUY: target > entry │
                 │      SL < entry     │
                 │ SELL: target < entry│
                 │       SL > entry    │
                 └─────────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │identity.resolve │
                 │→ DhanInstrument │
                 │  Ref            │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ Build payload:  │
                 │ price, target,  │
                 │ stopLoss,       │
                 │ trailingJump    │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │assert_dhan_     │
                 │payload()        │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │POST /super/     │
                 │orders           │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │_parse_super_    │
                 │order() →        │
                 │SuperOrder with  │
                 │leg details      │
                 └─────────────────┘
```

**Steps (Archive):**
1. Validate super order parameters (target > entry for BUY, etc.)
2. Resolve instrument via identity provider
3. Build payload with entry, target, SL, trailing jump
4. Assert payload invariant
5. POST `/super/orders`
6. Parse response into `SuperOrder` with leg details

**Super Order Legs:**
- ENTRY_LEG — the main order
- TARGET_LEG — profit-taking order
- STOP_LOSS_LEG — risk management order

### Greenfield Status

**NOT PORTED** — No `DhanSuperOrders` adapter exists in greenfield.

**Gap:** Complete super order functionality is missing from greenfield.

---

## 5. GTT Order Flow (Forever Orders)

### Archive Flow

```
┌──────────┐     ┌───────────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│ForeverOrdersAdapt │────▶│ DhanHttpClient│────▶│ Dhan REST API│
└──────────┘     └───────────────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
                 ┌──────────────────────┐
                 │_validate_forever_    │
                 │order()               │
                 │ - order_flag ∈       │
                 │   {SINGLE, OCO}      │
                 │ - OCO requires       │
                 │   price1, trigger1,  │
                 │   quantity1          │
                 └──────────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │identity.resolve │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ Build payload:  │
                 │ orderFlag,      │
                 │ price, trigger, │
                 │ + OCO fields    │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │assert_dhan_     │
                 │payload()        │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │POST /forever/   │
                 │orders           │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │_parse_forever_  │
                 │order() →        │
                 │ForeverOrder     │
                 └─────────────────┘
```

**Steps (Archive):**
1. Validate forever order (SINGLE vs OCO flag)
2. OCO validation: requires price1, trigger_price1, quantity1
3. Resolve instrument
4. Build payload with order flag and optional OCO fields
5. Assert payload invariant
6. POST `/forever/orders`
7. Parse response into `ForeverOrder`

### Greenfield Status

**NOT PORTED** — No `DhanForeverOrders` adapter exists in greenfield.

**Gap:** Complete GTT/OCO functionality is missing from greenfield.

---

## 6. GTT Trigger Management Flow (Conditional Triggers)

### Archive Flow

```
┌──────────┐     ┌──────────────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│ConditionalTriggersAdp│────▶│ DhanHttpClient│────▶│ Dhan REST API│
└──────────┘     └──────────────────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
                 ┌──────────────────────┐
                 │_validate_trigger()   │
                 │ - operator ∈         │
                 │   {CROSSING_UP,      │
                 │    CROSSING_DOWN,    │
                 │    GREATER_THAN,     │
                 │    LESS_THAN}        │
                 │ - comparisonType =   │
                 │   PRICE_WITH_VALUE   │
                 └──────────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ Build payload:  │
                 │ comparisonType, │
                 │ operator,       │
                 │ comparingValue, │
                 │ expDate,        │
                 │ frequency       │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │POST /alerts/    │
                 │orders           │
                 └─────────────────┘
```

**Operations (Archive):**
- `place_trigger()` — POST `/alerts/orders`
- `modify_trigger()` — PUT `/alerts/orders/{alert_id}`
- `delete_trigger()` — DELETE `/alerts/orders/{alert_id}`
- `get_trigger()` — GET `/alerts/orders/{alert_id}`
- `get_all_triggers()` — GET `/alerts/orders`

### Greenfield Flow

```
┌──────────┐     ┌──────────────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│DhanConditionalTriggers│────▶│ DhanHttpClient│────▶│ Dhan REST API│
└──────────┘     └──────────────────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │resolver.resolve │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │ Build payload:  │
                 │ Standard order  │
                 │ fields +        │
                 │ triggerPrice    │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │POST /conditional│
                 │Orders           │
                 └─────────────────┘
```

**Operations (Greenfield):**
- `place_conditional_order()` — POST `/conditionalOrders`
- `cancel_conditional_order()` — DELETE `/conditionalOrders/{trigger_id}`
- `get_conditional_orders()` — GET `/conditionalOrders`

### Comparison

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| Operators | CROSSING_UP/DOWN, GT, LT | Not validated | **MISSING** validation |
| Comparison type | PRICE_WITH_VALUE only | Not validated | **MISSING** validation |
| Modify trigger | Yes (PUT) | No | **MISSING** |
| Get single trigger | Yes | No | **MISSING** |
| OCO support | No | No | Same |
| Endpoint | `/alerts/orders` | `/conditionalOrders` | **DIFFERENT** endpoints |
| Response parsing | Full `ConditionalTrigger` entity | Raw dict | **MISSING** mapping |

---

## 7. Exit All Positions Flow

### Archive Flow

```
┌──────────┐     ┌────────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│ExitAllAdapter  │────▶│ DhanHttpClient│────▶│ Dhan REST API│
└──────────┘     └────────────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │POST /exitall    │
                 │(single call)    │
                 └─────────────────┘
                        │
                        ▼
                 ┌─────────────────┐
                 │_parse_response()│
                 │→ ExitAllResponse│
                 │ positions_closed│
                 │ orders_cancelled│
                 │ success         │
                 └─────────────────┘
```

**Steps (Archive):**
1. POST `/exitall` — single API call
2. Parse response into `ExitAllResponse` with counts

### Greenfield Flow

```
┌──────────┐     ┌────────────────┐     ┌──────────────┐     ┌──────────────┐
│ Consumer │────▶│ DhanExitAll    │────▶│ DhanHttpClient│────▶│ Dhan REST API│
└──────────┘     └────────────────┘     └──────────────┘     └──────────────┘
                        │
                        ▼
                 ┌─────────────────────────┐
                 │close_all_positions()    │
                 │ 1. GET /positions       │
                 │ 2. For each position:   │
                 │    - Calculate net_qty  │
                 │    - Build MARKET order │
                 │    - opposite side      │
                 │ 3. ThreadPoolExecutor   │
                 │    - POST orders        │
                 │    - concurrently       │
                 └─────────────────────────┘
                        │
                        ▼
                 ┌─────────────────────────┐
                 │cancel_all_orders()      │
                 │ 1. GET /orders          │
                 │ 2. Filter active status │
                 │ 3. ThreadPoolExecutor   │
                 │    - POST cancel        │
                 │    - concurrently       │
                 └─────────────────────────┘
```

**Steps (Greenfield):**
1. `close_all_positions()`:
   - Fetch all positions via GET `/positions`
   - Calculate net quantity (buyQty - sellQty)
   - Build MARKET order payload for each non-zero position
   - Submit orders concurrently via `ThreadPoolExecutor`
2. `cancel_all_orders()`:
   - Fetch orderbook via GET `/orders`
   - Filter orders with active status (PENDING, TRANSIT, OPEN, PARTIALLY_FILLED)
   - Cancel each concurrently via `ThreadPoolExecutor`

### Comparison

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| Implementation | Single API call | Manual concurrent orders | **DIFFERENT** approach |
| Positions close | Broker handles | Client builds opposite orders | Greenfield more complex |
| Order cancel | Broker handles | Client fetches + cancels each | Greenfield more complex |
| Concurrency | N/A | ThreadPoolExecutor | ✓ Greenfield parallelizes |
| Response | Structured ExitAllResponse | Raw dict with counts | Different |

---

## 8. Order Status Polling/Streaming Flow

### Archive Flow (Polling via Event Bus)

```
┌──────────┐     ┌───────────────┐     ┌──────────────┐
│ Consumer │────▶│ OrdersAdapter │────▶│  EventBus    │
└──────────┘     └───────────────┘     └──────────────┘
                        │                    │
                        ▼                    ▼
                 ┌─────────────────┐  ┌─────────────────┐
                 │get_order_status │  │publish()        │
                 │(polling)        │  │ORDER_PLACED     │
                 │or               │  │ORDER_MODIFIED   │
                 │get_order()      │  │ORDER_CANCELLED  │
                 └─────────────────┘  └─────────────────┘
```

**Archive approach:**
- Event bus publishes domain events on order lifecycle changes
- Consumers can poll via `get_order_status()` or `get_order()`
- No WebSocket streaming built-in

### Greenfield Flow (WebSocket Streaming)

```
┌──────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────┐
│ Consumer │────▶│ DhanOrderStream  │────▶│ Dhan WebSocket   │────▶│wss://api-    │
└──────────┘     └──────────────────┘     └──────────────────┘     │order-update  │
                        │                                           │.dhan.co      │
                        ▼                                           └──────────────┘
                 ┌─────────────────────────┐
                 │_build_subscribe_message │
                 │ LoginReq:               │
                 │  MsgCode: 42            │
                 │  ClientId + Token       │
                 └─────────────────────────┘
                        │
                        ▼
                 ┌─────────────────────────┐
                 │_on_message()            │
                 │ - Parse JSON            │
                 │ - _parse_order_update() │
                 │ - map_order()           │
                 │ - Fire on_order_update  │
                 │   callback              │
                 └─────────────────────────┘
                        │
                        ▼
                 ┌─────────────────────────┐
                 │ ReconciliationEngine    │
                 │ (background sync)       │
                 │ - Every 30 seconds      │
                 │ - Compare local ledger  │
                 │ - Detect drift          │
                 └─────────────────────────┘
```

**Greenfield approach:**
- WebSocket connection to `wss://api-order-update.dhan.co`
- Auth via `LoginReq` message with MsgCode 42
- Parses incoming messages into `Order` entities via `map_order()`
- Fires `on_order_update` callback
- `ReconciliationEngine` runs background sync every 30 seconds
- Catches ghost fills and dropped WS events

### Comparison

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| Streaming | Event bus (local) | WebSocket (real-time) | ✓ Greenfield better |
| Polling | `get_order_status()` | Via `OrderService.get_order()` | Same capability |
| Reconciliation | None | `ReconciliationEngine` | ✓ Greenfield better |
| Auth | N/A | LoginReq with token | Greenfield specific |
| Reconnect | N/A | Built-in (5s–60s backoff) | ✓ Greenfield robust |

---

## 9. Summary of Gaps

| Feature | Archive | Greenfield | Priority |
|---------|---------|------------|----------|
| Super Orders (bracket/cover) | ✓ Full | ✗ Missing | P1 |
| Forever Orders (GTT/OCO) | ✓ Full | ✗ Missing | P1 |
| Kill switch | ✓ Full | ✗ Missing | P2 |
| Slice orders | ✓ Full | ✗ Missing | P2 |
| Trade book / history | ✓ Full | ✗ Missing | P2 |
| Risk manager check | ✓ Full | ✗ Missing | P1 |
| Event publishing | ✓ Full | ✗ Missing | P2 |
| Conditional trigger modify | ✓ Full | ✗ Missing | P1 |
| Cancel-all (single API) | ✓ Full | ✗ Missing | P2 |
| Post-cancel race detect | ✗ Missing | ✓ Present | — |
| WebSocket streaming | ✗ Missing | ✓ Present | — |
| Reconciliation engine | ✗ Missing | ✓ Present | — |
