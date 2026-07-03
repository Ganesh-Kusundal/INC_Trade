# Phase 5 — Source Audit
## Greenfield Broker Replication Protocol — Dhan Order Management

---

## 1. Executive Summary

Phase 5 covers the **Order Management** subsystem of the Dhan broker adapter. This is the
highest-risk phase in the entire replication protocol: it is the boundary where client intent
becomes financial commitment. A bug here can lose real money.

### Scope

| Capability                        | Archive (legacy)                        | Greenfield (target)                     |
|-----------------------------------|-----------------------------------------|-----------------------------------------|
| Regular order placement           | `OrdersAdapter.place_order`             | `DhanOrders.place_order`                |
| Order modification                | `OrdersAdapter.modify_order`            | `DhanOrders.modify_order`               |
| Order cancellation                | `OrdersAdapter.cancel_order`            | `DhanOrders.cancel_order`               |
| Orderbook / trade book            | `OrdersAdapter.get_orderbook`           | `DhanOrders.get_orderbook`              |
| Slice orders                      | `OrdersAdapter.place_slice_order`       | — (not yet ported)                      |
| Super orders (bracket/cover)      | `SuperOrdersAdapter`                    | — (not yet ported)                      |
| Forever orders (GTT / OCO)        | `ForeverOrdersAdapter`                  | — (not yet ported)                      |
| Conditional triggers (alert GTT)  | `ConditionalTriggersAdapter`            | `DhanConditionalTriggers`               |
| Exit all (panic button)           | `ExitAllAdapter`                        | `DhanExitAll`                           |
| Kill switch                       | `OrdersAdapter.kill_switch`             | — (not yet ported)                      |
| Order status streaming            | Event bus publish                       | `DhanOrderStream` (WebSocket)           |
| Status mapping                    | `status_mapper.py`                      | Inline in `mapper.py`                   |
| Payload invariants                | `invariants.py`                         | `invariants.py` (greenfield)            |
| Order validation                  | Inline in `OrdersAdapter`               | `order_validation.py` (service layer)   |
| Reconciliation                    | —                                       | `ReconciliationEngine`                  |

### Risk Profile

- **P0**: Incorrect payload → exchange rejection or unintended trade
- **P0**: Missing idempotency → duplicate orders on retry
- **P1**: Status mapping errors → phantom fills or missed rejections
- **P1**: Race conditions in cancel → cancel-after-fill

---

## 2. Archive Files

| File | Lines | Purpose |
|------|-------|---------|
| `archive/brokers/dhan/orders.py` | 726 | Core order lifecycle: place, modify, cancel, orderbook, tradebook, slice orders, kill switch |
| `archive/brokers/dhan/super_orders.py` | 334 | Bracket/cover orders with Entry + Target + Stop Loss legs and trailing SL |
| `archive/brokers/dhan/forever_orders.py` | 291 | GTT (Good Till Triggered) orders — SINGLE and OCO modes |
| `archive/brokers/dhan/exit_all.py` | 55 | Panic button: close all positions + cancel all orders in one API call |
| `archive/brokers/dhan/conditional_triggers.py` | 269 | Price-based alert triggers (CROSSING_UP, CROSSING_DOWN, etc.) |
| `archive/brokers/dhan/status_mapper.py` | 41 | Dhan-specific order status → canonical OrderStatus mapping |
| `archive/brokers/dhan/invariants.py` | 264 | Defence-in-depth payload assertions (securityId + exchangeSegment) |

**Total archive lines: 1,980**

---

## 3. Greenfield Files

| File | Lines | Purpose |
|------|-------|---------|
| `brokers/adapters/dhan/orders.py` | 137 | Dhan-specific order adapter: place, cancel, modify, get, orderbook |
| `brokers/adapters/dhan/conditional_triggers.py` | 104 | Conditional (GTT) order adapter: place, cancel, list |
| `brokers/adapters/dhan/exit_all.py` | 103 | Panic button: concurrent position square-off + order cancellation |
| `brokers/adapters/dhan/order_stream.py` | 102 | WebSocket-based real-time order status streaming |
| `brokers/services/order_service.py` | 103 | Application-level order service with validation + idempotency |
| `brokers/services/order_validation.py` | 89 | Market microstructure validation (lot size, tick, product×segment) |
| `brokers/services/reconciliation.py` | 58 | Background daemon syncing local OMS against broker ledger |

**Total greenfield lines: 696**

### Domain / Ports Files

| File | Lines | Purpose |
|------|-------|---------|
| `brokers/domain/order_lifecycle.py` | 64 | Canonical order status transition table + validation |
| `brokers/domain/entities.py` | 169 | Frozen dataclasses: Order, OrderResponse, Trade, Position, Quote, etc. |
| `brokers/domain/enums.py` | 92 | Domain enumerations: Side, OrderType, OrderStatus, ProductType, Validity |
| `brokers/ports/order_execution.py` | 35 | Narrow port interface for order execution (place, cancel, get, orderbook) |

---

## 4. Key Symbols and Classes

### Archive

| Symbol | File | Role |
|--------|------|------|
| `OrdersAdapter` | `orders.py` | Main adapter class — wraps DhanHttpClient for order CRUD |
| `SuperOrdersAdapter` | `super_orders.py` | Bracket/cover order adapter with leg management |
| `ForeverOrdersAdapter` | `forever_orders.py` | GTT order adapter (SINGLE + OCO) |
| `ExitAllAdapter` | `exit_all.py` | Single-call panic button |
| `ConditionalTriggersAdapter` | `conditional_triggers.py` | Price-based alert trigger adapter |
| `assert_dhan_payload` | `invariants.py` | Boundary assertion for payload identity |
| `assert_dhan_identity` | `invariants.py` | Two-arg or carrier-form identity check |
| `assert_dhan_segment` | `invariants.py` | Segment-only validation |
| `assert_valid_security_id` | `invariants.py` | Narrow security_id digit contract |
| `DHAN_STATUS_MAP` | `status_mapper.py` | Dhan-specific status → OrderStatus dict |
| `register_mappings` | `status_mapper.py` | One-time registration with global StatusMapperRegistry |
| `BrokerOrderPayload` | (imported) | Canonical order request DTO |
| `DhanInstrumentRef` | (imported) | Carrier dataclass enforcing Dhan-internal contract |
| `IdempotencyCache` | (imported) | Check-then-act cache preventing duplicate orders |

### Greenfield

| Symbol | File | Role |
|--------|------|------|
| `DhanOrders` | `adapters/dhan/orders.py` | Adapter class — place, cancel, modify, get, orderbook |
| `DhanConditionalTriggers` | `adapters/dhan/conditional_triggers.py` | GTT adapter — place, cancel, list |
| `DhanExitAll` | `adapters/dhan/exit_all.py` | Panic button — concurrent square-off + cancel |
| `DhanOrderStream` | `adapters/dhan/order_stream.py` | WebSocket order update stream |
| `OrderService` | `services/order_service.py` | Application service with validation + idempotency |
| `validate_order_fields` | `services/order_validation.py` | Field-level validation (symbol, qty, price) |
| `validate_lot_size` | `services/order_validation.py` | Lot size multiple check |
| `validate_tick_alignment` | `services/order_validation.py` | Tick size alignment check |
| `validate_product_segment` | `services/order_validation.py` | Product × exchange compatibility |
| `check_notional_warning` | `services/order_validation.py` | Non-blocking high-notional warning |
| `ReconciliationEngine` | `services/reconciliation.py` | Async background sync daemon |
| `Order` | `domain/entities.py` | Frozen order entity |
| `OrderResponse` | `domain/entities.py` | Frozen response with ok/fail factory methods |
| `OrderExecutionPort` | `ports/order_execution.py` | Protocol defining the adapter contract |
| `OrderStatus` | `domain/enums.py` | Canonical status enum with is_terminal/is_active |
| `is_valid_transition` | `domain/order_lifecycle.py` | State machine transition check |
| `validate_transition` | `domain/order_lifecycle.py` | Raises OrderStateError on illegal transition |

---

## 5. Order Types Supported

| Order Type | Archive Enum | Greenfield Enum | Notes |
|------------|--------------|-----------------|-------|
| MARKET | `OrderType.MARKET` | `OrderType.MARKET` | Immediate execution at best price |
| LIMIT | `OrderType.LIMIT` | `OrderType.LIMIT` | Requires price > 0 |
| STOP_LOSS | `OrderType.STOP_LOSS` | `OrderType.STOP_LOSS` | Requires trigger_price > 0 |
| STOP_LOSS_MARKET | `OrderType.STOP_LOSS_MARKET` | `OrderType.STOP_LOSS_MARKET` | SL + market execution |
| AMO (After Market) | Supported via validity | Supported via `Validity.DAY` | Placed outside market hours |

### Product Types

| Product | Archive | Greenfield | Segment Restriction |
|---------|---------|------------|---------------------|
| INTRADAY | Yes | Yes | All segments |
| DELIVERY (CNC) | Yes | Yes | Equity only (NSE/BSE) |
| MARGIN | Yes | Yes | Derivatives |

### Validity Types

| Validity | Archive | Greenfield |
|----------|---------|------------|
| DAY | Yes | Yes |
| IOC | Yes | Yes |
| GTT | Yes (via Forever Orders) | Yes (enum only) |

---

## 6. Order Lifecycle States

### Canonical Status Enum (Greenfield `domain/enums.py`)

```
PENDING → OPEN → PARTIALLY_FILLED → FILLED
                                   → CANCELLED
                                   → PARTIALLY_CANCELLED
         → REJECTED
         → CANCELLED
         → EXPIRED
```

### Status Properties

| Status | `is_terminal` | `is_active` |
|--------|---------------|-------------|
| PENDING | No | Yes |
| OPEN | No | Yes |
| PARTIALLY_FILLED | No | Yes |
| FILLED | Yes | No |
| CANCELLED | Yes | No |
| PARTIALLY_CANCELLED | Yes | No |
| EXPIRED | Yes | No |
| REJECTED | Yes | No |

### Dhan-Specific Status Mappings (Archive `status_mapper.py`)

| Dhan Status String | Canonical OrderStatus |
|--------------------|-----------------------|
| `PLACED` | `OPEN` |
| `TRIGGERED` | `OPEN` |
| `PARTIALLY_CANCELLED` | `PARTIALLY_CANCELLED` |
| *(all COMMON_STATUS_MAP entries)* | *(inherited)* |

### Transition Table (Greenfield `order_lifecycle.py`)

| From | Allowed Transitions |
|------|---------------------|
| PENDING | OPEN, REJECTED, CANCELLED, EXPIRED |
| OPEN | PARTIALLY_FILLED, FILLED, CANCELLED, PARTIALLY_CANCELLED, EXPIRED, REJECTED |
| PARTIALLY_FILLED | FILLED, CANCELLED, PARTIALLY_CANCELLED |
| PARTIALLY_CANCELLED | CANCELLED |
| FILLED | *(terminal)* |
| CANCELLED | *(terminal)* |
| REJECTED | *(terminal)* |
| EXPIRED | *(terminal)* |

---

## 7. Invariant Checks (invariants.py)

The archive `invariants.py` implements a **two-line-of-defence** strategy:

### Line 1: Carrier Enforcement (DhanInstrumentRef.__post_init__)
- Rejects non-Dhan segments at construction time
- Rejects non-digit security_id values
- Runs once when the carrier is built

### Line 2: Boundary Assertions (this module)
Called at every payload-builder boundary before `_client.post`:

| Function | What It Validates |
|----------|-------------------|
| `assert_dhan_payload(payload, context=...)` | Extracts `securityId` + `exchangeSegment` from dict, runs both checks |
| `assert_dhan_identity(security_id, segment, context=...)` | Segment ∈ DHAN_SEGMENTS + security_id is positive digit string |
| `assert_dhan_segment(segment, context=...)` | Segment ∈ DHAN_SEGMENTS (non-empty string) |
| `assert_valid_security_id(security_id, context=...)` | Non-empty, non-bool, digit-only string or positive int |

### Failure Mode
- All helpers raise `DhanIdentityError` (explicit `raise`, not `assert`)
- Works under `python -O` (safe for production)
- Error message includes offending field, value, and context string

### Greenfield Equivalent
- `brokers/adapters/dhan/invariants.py` provides `assert_valid_dhan_payload`
- Called in `DhanOrders.place_order` before `_client.post`
- Same defence-in-depth philosophy, simplified API

---

## 8. REST API Endpoints

### Archive Endpoints (Dhan API)

| Operation | Method | Endpoint | Used By |
|-----------|--------|----------|---------|
| Place order | POST | `/orders` | `OrdersAdapter.place_order` |
| Modify order | PUT | `/orders/{order_id}` | `OrdersAdapter.modify_order` |
| Cancel order | DELETE | `/orders/{order_id}` | `OrdersAdapter.cancel_order` |
| Cancel all | DELETE | `/orders` | `OrdersAdapter.cancel_all_orders` |
| Get order | GET | `/orders/{order_id}` | `OrdersAdapter.get_order` |
| Orderbook | GET | `/orders` | `OrdersAdapter.get_orderbook` |
| Trade book | GET | `/trades` | `OrdersAdapter.get_trade_book` |
| Trade history | GET | `/trades/{from}/{to}/{page}` | `OrdersAdapter.get_trade_history` |
| Slice order | POST | `/orders/slicing` | `OrdersAdapter.place_slice_order` |
| Kill switch | POST | `/killswitch?killSwitchStatus={ACTIVATE\|DEACTIVATE}` | `OrdersAdapter.kill_switch` |
| Place super order | POST | `/super/orders` | `SuperOrdersAdapter.place_super_order` |
| Modify super order | PUT | `/super/orders/{order_id}` | `SuperOrdersAdapter.modify_super_order` |
| Cancel super leg | DELETE | `/super/orders/{order_id}/{leg_name}` | `SuperOrdersAdapter.cancel_super_order_leg` |
| Get super orders | GET | `/super/orders` | `SuperOrdersAdapter.get_super_orders` |
| Place forever order | POST | `/forever/orders` | `ForeverOrdersAdapter.place_forever_order` |
| Modify forever order | PUT | `/forever/orders/{order_id}` | `ForeverOrdersAdapter.modify_forever_order` |
| Cancel forever order | DELETE | `/forever/orders/{order_id}` | `ForeverOrdersAdapter.cancel_forever_order` |
| Get all forever orders | GET | `/forever/all` | `ForeverOrdersAdapter.get_all_forever_orders` |
| Place trigger | POST | `/alerts/orders` | `ConditionalTriggersAdapter.place_trigger` |
| Modify trigger | PUT | `/alerts/orders/{alert_id}` | `ConditionalTriggersAdapter.modify_trigger` |
| Delete trigger | DELETE | `/alerts/orders/{alert_id}` | `ConditionalTriggersAdapter.delete_trigger` |
| Get trigger | GET | `/alerts/orders/{alert_id}` | `ConditionalTriggersAdapter.get_trigger` |
| Get all triggers | GET | `/alerts/orders` | `ConditionalTriggersAdapter.get_all_triggers` |
| Exit all | POST | `/exitall` | `ExitAllAdapter.exit_all` |

### Greenfield Endpoints (via config ENDPOINTS dict)

| Operation | Endpoint Key | Notes |
|-----------|--------------|-------|
| Place order | `orders` | `/orders` |
| Cancel order | `cancel_order` | `/orders/{order_id}` |
| Modify order | `modify_order` | `/orders/{order_id}` |
| Get order | `order_by_id` | `/orders/{order_id}` |
| Orderbook | `orderbook` | `/orders` |
| Positions | `positions` | `/positions` |

---

## 9. Greenfield Architecture

### Layered Design

```
┌─────────────────────────────────────────────────────┐
│  Consumer (CLI / API / Strategy Engine)             │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│  Service Layer                                      │
│  ┌─────────────────┐  ┌──────────────────────────┐  │
│  │  OrderService    │  │  ReconciliationEngine    │  │
│  │  - validation    │  │  - async sync loop       │  │
│  │  - idempotency   │  │  - drift detection       │  │
│  │  - logging       │  │                          │  │
│  └────────┬─────────┘  └──────────────────────────┘  │
│           │                                          │
│  ┌────────▼──────────────────────────────────────┐   │
│  │  order_validation.py                          │   │
│  │  - validate_order_fields                      │   │
│  │  - validate_lot_size                          │   │
│  │  - validate_tick_alignment                    │   │
│  │  - validate_product_segment                   │   │
│  │  - check_notional_warning                     │   │
│  └───────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────┘
                     │ depends on port, not concretion
┌────────────────────▼────────────────────────────────┐
│  Port Layer                                         │
│  ┌──────────────────────────────────────────────┐   │
│  │  OrderExecutionPort (Protocol)               │   │
│  │  - place_order(...)  -> OrderResponse         │   │
│  │  - cancel_order(id)  -> OrderResponse         │   │
│  │  - get_order(id)     -> Order | None          │   │
│  │  - get_orderbook()   -> list[Order]           │   │
│  └──────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────┘
                     │ implemented by
┌────────────────────▼────────────────────────────────┐
│  Adapter Layer (Dhan-specific)                      │
│  ┌──────────────┐ ┌──────────────────┐ ┌─────────┐ │
│  │ DhanOrders    │ │DhanConditional   │ │DhanExit │ │
│  │               │ │Triggers          │ │All      │ │
│  │ place/cancel/ │ │ place/cancel/    │ │ close   │ │
│  │ modify/get    │ │ list             │ │ cancel  │ │
│  └──────┬───────┘ └────────┬─────────┘ └────┬────┘ │
│         │                  │                 │       │
│  ┌──────▼──────────────────▼─────────────────▼────┐ │
│  │  DhanHttpClient (Phase 3)                      │ │
│  │  DhanInstrumentResolver (Phase 2)              │ │
│  │  invariants.assert_valid_dhan_payload           │ │
│  │  mapper.map_order / map_order_response          │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Service layer is broker-agnostic**: `OrderService` depends on `OrderExecutionPort`, not `DhanOrders`
2. **Validation is extracted**: Archive had inline validation in `OrdersAdapter`; greenfield splits it into `order_validation.py`
3. **Adapter is thin**: `DhanOrders` only handles Dhan-specific payload construction and response mapping
4. **Streaming is separate**: `DhanOrderStream` is a standalone WebSocket adapter, not embedded in `DhanOrders`
5. **Reconciliation is async**: Background daemon catches ghost fills and dropped WS events
6. **Frozen entities**: All domain entities are immutable dataclasses — no mutation after construction
