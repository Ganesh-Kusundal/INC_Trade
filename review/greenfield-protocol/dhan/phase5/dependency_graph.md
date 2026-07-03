# Phase 5 — Dependency Graph
## Greenfield Broker Replication Protocol — Dhan Order Management

---

## 1. Internal Dependencies (Within Phase 5)

### Archive Internal Dependencies

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ARCHIVE PHASE 5                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐                                                │
│  │  orders.py      │──────────────────────────────────────┐         │
│  │  OrdersAdapter  │                                      │         │
│  └────────┬────────┘                                      │         │
│           │ imports                                       │         │
│           ├────────▶ invariants.py (assert_dhan_payload)  │         │
│           ├────────▶ exceptions.py (DhanError, OrderError)│         │
│           ├────────▶ http_client.py (DhanHttpClient)      │         │
│           ├────────▶ identity.py (DhanIdentityProvider)   │         │
│           ├────────▶ segments.py (EXCHANGE_TO_SEGMENT)    │         │
│           └────────▶ config/endpoints.py (Dhan)           │         │
│                                                           │         │
│  ┌─────────────────┐                                      │         │
│  │super_orders.py  │──────────────────┐                   │         │
│  │SuperOrdersAdapt │                  │                   │         │
│  └────────┬────────┘                  │                   │         │
│           │ imports                   │                   │         │
│           ├────────▶ invariants.py    │                   │         │
│           ├────────▶ exceptions.py    │                   │         │
│           ├────────▶ http_client.py   │                   │         │
│           ├────────▶ identity.py      │                   │         │
│           └────────▶ domain.py        │                   │         │
│                    (SuperOrder)       │                   │         │
│                                       │                   │         │
│  ┌─────────────────┐                  │                   │         │
│  │forever_orders.py│──────────────────┤                   │         │
│  │ForeverOrdersAdpt│                  │                   │         │
│  └────────┬────────┘                  │                   │         │
│           │ imports                   │                   │         │
│           ├────────▶ invariants.py    │                   │         │
│           ├────────▶ exceptions.py    │                   │         │
│           ├────────▶ http_client.py   │                   │         │
│           ├────────▶ identity.py      │                   │         │
│           └────────▶ domain.py        │                   │         │
│                    (ForeverOrder)     │                   │         │
│                                       │                   │         │
│  ┌─────────────────┐                  │                   │         │
│  │exit_all.py      │                  │                   │         │
│  │ExitAllAdapter   │                  │                   │         │
│  └────────┬────────┘                  │                   │         │
│           │ imports                   │                   │         │
│           ├────────▶ exceptions.py    │                   │         │
│           ├────────▶ http_client.py   │                   │         │
│           └────────▶ domain.py        │                   │         │
│                    (ExitAllResponse)  │                   │         │
│                                       │                   │         │
│  ┌─────────────────┐                  │                   │         │
│  │conditional_     │──────────────────┤                   │         │
│  │triggers.py      │                  │                   │         │
│  │ConditionalTrigAd│                  │                   │         │
│  └────────┬────────┘                  │                   │         │
│           │ imports                   │                   │         │
│           ├────────▶ invariants.py ◀──┼───────────────────┘         │
│           ├────────▶ exceptions.py ◀──┤                             │
│           ├────────▶ http_client.py ◀─┤                             │
│           ├────────▶ identity.py ◀────┤                             │
│           └────────▶ domain.py        │                             │
│                    (ConditionalTrigger│                             │
│                                       │                             │
│  ┌─────────────────┐                  │                             │
│  │status_mapper.py │                  │                             │
│  │DHAN_STATUS_MAP  │                  │                             │
│  └─────────────────┘                  │                             │
│                                       │                             │
│  ┌─────────────────┐                  │                             │
│  │ invariants.py   │ ◀────────────────┘                             │
│  │ (shared)        │                                                │
│  └─────────────────┘                                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Shared Infrastructure (Archive)

| Module | Used By | Purpose |
|--------|---------|---------|
| `invariants.py` | orders, super_orders, forever_orders, conditional_triggers | Payload identity assertions |
| `http_client.py` | All adapters | HTTP transport |
| `identity.py` | orders, super_orders, forever_orders, conditional_triggers | Instrument resolution |
| `exceptions.py` | All adapters | Error types |
| `domain.py` | super_orders, forever_orders, exit_all, conditional_triggers | DTOs (SuperOrder, ForeverOrder, etc.) |

### Greenfield Internal Dependencies

```
┌─────────────────────────────────────────────────────────────────────┐
│                       GREENFIELD PHASE 5                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │                  SERVICE LAYER                           │        │
│  │                                                         │        │
│  │  ┌─────────────────┐     ┌──────────────────────────┐   │        │
│  │  │ order_service.py│────▶│ order_validation.py      │   │        │
│  │  │ OrderService    │     │ - validate_order_fields  │   │        │
│  │  │                 │     │ - validate_lot_size      │   │        │
│  │  │                 │     │ - validate_tick_alignment│   │        │
│  │  │                 │     │ - validate_product_seg   │   │        │
│  │  │                 │     │ - check_notional_warning │   │        │
│  │  └────────┬────────┘     └──────────────────────────┘   │        │
│  │           │                                             │        │
│  │           │ depends on port                             │        │
│  │           ▼                                             │        │
│  │  ┌─────────────────┐     ┌──────────────────────────┐   │        │
│  │  │reconciliation.py│     │ OrderExecutionPort       │   │        │
│  │  │ReconciliationEng│     │ (Protocol — interface)   │   │        │
│  │  │                 │     └──────────────────────────┘   │        │
│  │  │ depends on      │                                    │        │
│  │  │ BrokerGateway   │                                    │        │
│  │  └─────────────────┘                                    │        │
│  └─────────────────────────────────────────────────────────┘        │
│                          │                                          │
│                          ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │                  ADAPTER LAYER                           │        │
│  │                                                         │        │
│  │  ┌─────────────────┐                                    │        │
│  │  │ orders.py       │──────────────────────────┐         │        │
│  │  │ DhanOrders      │                          │         │        │
│  │  └────────┬────────┘                          │         │        │
│  │           │ imports                           │         │        │
│  │           ├────────▶ config.py (ENDPOINTS,    │         │        │
│  │           │           ORDER_TYPE_MAP, etc.)   │         │        │
│  │           ├────────▶ http.py (DhanHttpClient) │         │        │
│  │           ├────────▶ identity.py (Resolver)   │         │        │
│  │           ├────────▶ invariants.py            │         │        │
│  │           ├────────▶ mapper.py (map_order)    │         │        │
│  │           └────────▶ utils/price.py           │         │        │
│  │                                               │         │        │
│  │  ┌─────────────────┐                          │         │        │
│  │  │conditional_     │──────────────────────────┤         │        │
│  │  │triggers.py      │                          │         │        │
│  │  │DhanConditional  │                          │         │        │
│  │  │Triggers         │                          │         │        │
│  │  └────────┬────────┘                          │         │        │
│  │           │ imports                           │         │        │
│  │           ├────────▶ config.py ◀──────────────┤         │        │
│  │           ├────────▶ http.py ◀────────────────┤         │        │
│  │           ├────────▶ identity.py ◀────────────┤         │        │
│  │           └────────▶ utils/price.py ◀─────────┤         │        │
│  │                                               │         │        │
│  │  ┌─────────────────┐                          │         │        │
│  │  │ exit_all.py     │                          │         │        │
│  │  │ DhanExitAll     │                          │         │        │
│  │  └────────┬────────┘                          │         │        │
│  │           │ imports                           │         │        │
│  │           ├────────▶ config.py ◀──────────────┤         │        │
│  │           └────────▶ http.py ◀────────────────┤         │        │
│  │                                               │         │        │
│  │  ┌─────────────────┐                          │         │        │
│  │  │ order_stream.py │                          │         │        │
│  │  │ DhanOrderStream │                          │         │        │
│  │  └────────┬────────┘                          │         │        │
│  │           │ imports                           │         │        │
│  │           ├────────▶ base_streaming.py        │         │        │
│  │           ├────────▶ mapper.py ◀──────────────┘         │        │
│  │           └────────▶ domain/entities.py                 │        │
│  │                                                         │        │
│  └─────────────────────────────────────────────────────────┘        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Shared Infrastructure (Greenfield)

| Module | Used By | Purpose |
|--------|---------|---------|
| `config.py` | orders, conditional_triggers, exit_all | ENDPOINTS dict, enum maps |
| `http.py` | orders, conditional_triggers, exit_all | HTTP transport |
| `identity.py` | orders, conditional_triggers | Instrument resolution |
| `invariants.py` | orders | Payload identity assertions |
| `mapper.py` | orders, order_stream | Response parsing |
| `utils/price.py` | orders, conditional_triggers | Price formatting |
| `base_streaming.py` | order_stream | WebSocket base class |

---

## 2. Cross-Phase Dependencies

Phase 5 does not exist in isolation. It depends on infrastructure established in earlier phases.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CROSS-PHASE DEPENDENCIES                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Phase 0: Configuration                                     │    │
│  │  ┌───────────────────────────────────────────────────────┐  │    │
│  │  │ config.py — ENDPOINTS, ORDER_TYPE_MAP, PRODUCT_TYPE_  │  │    │
│  │  │ MAP, SIDE_MAP, VALIDITY_MAP                           │  │    │
│  │  └───────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                          ▲                                          │
│                          │ used by                                  │
│  ┌───────────────────────┼─────────────────────────────────────┐    │
│  │  Phase 1: Authentication                                    │    │
│  │  ┌───────────────────────────────────────────────────────┐  │    │
│  │  │ auth.py — access_token, client_id                     │  │    │
│  │  │ → DhanHttpClient (injects auth headers)               │  │    │
│  │  │ → DhanOrderStream (LoginReq with token)               │  │    │
│  │  └───────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                          ▲                                          │
│                          │ used by                                  │
│  ┌───────────────────────┼─────────────────────────────────────┐    │
│  │  Phase 2: Instruments                                       │    │
│  │  ┌───────────────────────────────────────────────────────┐  │    │
│  │  │ identity.py — DhanInstrumentResolver                  │  │    │
│  │  │ → resolve(symbol, exchange) → DhanInstrumentRef       │  │    │
│  │  │ → provides security_id, exchange_segment              │  │    │
│  │  └───────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                          ▲                                          │
│                          │ used by                                  │
│  ┌───────────────────────┼─────────────────────────────────────┐    │
│  │  Phase 3: HTTP Client                                       │    │
│  │  ┌───────────────────────────────────────────────────────┐  │    │
│  │  │ http.py — DhanHttpClient                              │  │    │
│  │  │ → get(), post(), put(), delete()                      │  │    │
│  │  │ → error handling, rate limiting, retry                │  │    │
│  │  └───────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                          ▲                                          │
│                          │ used by                                  │
│  ┌───────────────────────┼─────────────────────────────────────┐    │
│  │  Phase 5: Order Management                                  │    │
│  │  ┌───────────────────────────────────────────────────────┐  │    │
│  │  │ orders.py, conditional_triggers.py, exit_all.py       │  │    │
│  │  │ order_stream.py                                       │  │    │
│  │  └───────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Phase Dependency Matrix

| Phase | Provides | Used By Phase 5 |
|-------|----------|-----------------|
| Phase 0 | Config (ENDPOINTS, maps) | `config.py` in all adapters |
| Phase 1 | Auth (tokens, client_id) | `DhanHttpClient`, `DhanOrderStream` |
| Phase 2 | Instruments (resolver) | `DhanInstrumentResolver.resolve()` |
| Phase 3 | HTTP client | `DhanHttpClient.get/post/put/delete()` |
| Phase 4 | Market data (optional) | Not directly used by orders |

---

## 3. Domain Model Dependencies

### Entity Dependencies

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DOMAIN MODEL DEPENDENCIES                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  domain/enums.py (zero dependencies)                        │    │
│  │  ┌──────────┐ ┌───────────┐ ┌─────────────┐ ┌──────────┐   │    │
│  │  │  Side    │ │ OrderType │ │ OrderStatus │ │ProductType│   │    │
│  │  │  BUY/SELL│ │ MARKET/   │ │ PENDING/    │ │ INTRADAY/ │   │    │
│  │  │          │ │ LIMIT/SL  │ │ OPEN/FILLED │ │ DELIVERY  │   │    │
│  │  └──────────┘ └───────────┘ └─────────────┘ └──────────┘   │    │
│  │  ┌──────────┐ ┌───────────┐                                 │    │
│  │  │ Validity │ │ AuthMode  │                                 │    │
│  │  │ DAY/IOC/ │ │ STATIC/   │                                 │    │
│  │  │ GTT      │ │ OAUTH/... │                                 │    │
│  │  └──────────┘ └───────────┘                                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                          ▲                                          │
│                          │ imported by                              │
│  ┌───────────────────────┼─────────────────────────────────────┐    │
│  │  domain/entities.py  │                                      │    │
│  │  ┌──────────┐ ┌──────────────┐ ┌───────┐ ┌──────────┐      │    │
│  │  │  Order   │ │OrderResponse │ │ Trade │ │ Position │      │    │
│  │  │          │ │              │ │       │ │          │      │    │
│  │  │ uses:    │ │ uses:        │ │ uses: │ │ uses:    │      │    │
│  │  │ Side,    │ │ OrderStatus  │ │ Side  │ │ProductType│     │    │
│  │  │ OrderType│ │              │ │       │ │          │      │    │
│  │  │ OrderStat│ │              │ │       │ │          │      │    │
│  │  │ ProductType               │ │       │ │          │      │    │
│  │  │ Validity │ │              │ │       │ │          │      │    │
│  │  └──────────┘ └──────────────┘ └───────┘ └──────────┘      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                          ▲                                          │
│                          │ imported by                              │
│  ┌───────────────────────┼─────────────────────────────────────┐    │
│  │  domain/order_lifecycle.py                                  │    │
│  │  ┌───────────────────────────────────────────────────────┐  │    │
│  │  │ ORDER_STATUS_TRANSITIONS — canonical state machine    │  │    │
│  │  │ is_valid_transition() / validate_transition()         │  │    │
│  │  │ uses: OrderStatus                                     │  │    │
│  │  └───────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                          ▲                                          │
│                          │ imported by                              │
│  ┌───────────────────────┼─────────────────────────────────────┐    │
│  │  ports/order_execution.py                                   │    │
│  │  ┌───────────────────────────────────────────────────────┐  │    │
│  │  │ OrderExecutionPort (Protocol)                         │  │    │
│  │  │ uses: Order, OrderResponse, Side, OrderType,          │  │    │
│  │  │       ProductType, Validity                           │  │    │
│  │  └───────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Dependency Direction (Inner → Outer)

```
    enums.py (innermost — zero deps)
        │
        ▼
    entities.py (depends on enums)
        │
        ▼
    order_lifecycle.py (depends on enums)
        │
        ▼
    ports/order_execution.py (depends on entities + enums)
        │
        ▼
    services/order_service.py (depends on port)
        │
        ▼
    adapters/dhan/orders.py (implements port)
```

---

## 4. Service Layer Dependencies

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SERVICE LAYER DEPENDENCIES                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  OrderService                                               │    │
│  │                                                             │    │
│  │  Dependencies:                                              │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │ OrderExecutionPort (injected)                       │    │    │
│  │  │ → Implemented by DhanOrders                         │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │ IdempotencyCache (optional, injected)               │    │    │
│  │  │ → check_and_set(correlation_id)                     │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │ lot_size, tick_size (constructor params)            │    │    │
│  │  │ → From Phase 2 instrument resolution                │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  │                                                             │    │
│  │  Uses:                                                      │    │
│  │  - order_validation.validate_order_fields                   │    │
│  │  - order_validation.validate_lot_size                       │    │
│  │  - order_validation.validate_tick_alignment                 │    │
│  │  - order_validation.validate_product_segment                │    │
│  │  - order_validation.check_notional_warning                  │    │
│  │                                                             │    │
│  │  Returns:                                                   │    │
│  │  - OrderResponse (from entities.py)                         │    │
│  │  - Order (from entities.py)                                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  ReconciliationEngine                                       │    │
│  │                                                             │    │
│  │  Dependencies:                                              │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │ BrokerGateway (injected)                            │    │    │
│  │  │ → Higher-level port exposing get_all_orders()       │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  │  ┌─────────────────────────────────────────────────────┐    │    │
│  │  │ local_order_ledger (Dict[str, OrderResponse])       │    │    │
│  │  │ → In-memory OMS state                               │    │    │
│  │  └─────────────────────────────────────────────────────┘    │    │
│  │                                                             │    │
│  │  Uses:                                                      │    │
│  │  - asyncio (event loop)                                     │    │
│  │  - sync_interval_seconds (default 30)                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Dependency Diagram (Full System)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FULL DEPENDENCY GRAPH                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        CONSUMERS                                     │    │
│  │  CLI  │  REST API  │  Strategy Engine  │  Dashboard                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                  │                                          │
│                                  ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     SERVICE LAYER                                   │    │
│  │                                                                     │    │
│  │  ┌─────────────────┐              ┌─────────────────────────────┐  │    │
│  │  │  OrderService   │              │  ReconciliationEngine       │  │    │
│  │  │                 │              │  (async background)         │  │    │
│  │  │  ┌───────────┐  │              └──────────────┬──────────────┘  │    │
│  │  │  │validation │  │                             │                 │    │
│  │  │  │_order.py  │  │                             │                 │    │
│  │  │  └───────────┘  │                             │                 │    │
│  │  └────────┬────────┘                             │                 │    │
│  └───────────┼──────────────────────────────────────┼─────────────────┘    │
│              │                                      │                      │
│              ▼                                      ▼                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        PORT LAYER                                   │    │
│  │                                                                     │    │
│  │  ┌─────────────────────────┐      ┌─────────────────────────────┐  │    │
│  │  │ OrderExecutionPort      │      │ BrokerGateway               │  │    │
│  │  │ (Protocol)              │      │ (Protocol)                  │  │    │
│  │  │                         │      │                             │  │    │
│  │  │ place_order()           │      │ get_all_orders()            │  │    │
│  │  │ cancel_order()          │      │ (for reconciliation)        │  │    │
│  │  │ get_order()             │      │                             │  │    │
│  │  │ get_orderbook()         │      │                             │  │    │
│  │  └─────────────────────────┘      └─────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│              │                                      │                      │
│              ▼                                      │                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      ADAPTER LAYER (Dhan)                           │    │
│  │                                                                     │    │
│  │  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │    │
│  │  │ DhanOrders   │  │DhanConditional   │  │ DhanExitAll          │  │    │
│  │  │              │  │Triggers          │  │                      │  │    │
│  │  │ place_order  │  │                  │  │ close_all_positions  │  │    │
│  │  │ cancel_order │  │ place_conditional│  │ cancel_all_orders    │  │    │
│  │  │ modify_order │  │ cancel_conditional│ │                      │  │    │
│  │  │ get_order    │  │ get_conditional  │  │                      │  │    │
│  │  │ get_orderbook│  │                  │  │                      │  │    │
│  │  └──────┬───────┘  └────────┬─────────┘  └──────────┬───────────┘  │    │
│  │         │                   │                        │              │    │
│  │  ┌──────▼───────────────────▼────────────────────────▼───────────┐  │    │
│  │  │              SHARED ADAPTER INFRASTRUCTURE                    │  │    │
│  │  │                                                               │  │    │
│  │  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐  │  │    │
│  │  │  │DhanHttpClient│  │DhanInstrument│  │ invariants.py       │  │  │    │
│  │  │  │ (Phase 3)    │  │Resolver      │  │ assert_valid_dhan_  │  │  │    │
│  │  │  │              │  │ (Phase 2)    │  │ payload()           │  │  │    │
│  │  │  └─────────────┘  └──────────────┘  └─────────────────────┘  │  │    │
│  │  │                                                               │  │    │
│  │  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐  │  │    │
│  │  │  │ config.py   │  │ mapper.py    │  │ utils/price.py      │  │  │    │
│  │  │  │ (Phase 0)   │  │              │  │                     │  │  │    │
│  │  │  └─────────────┘  └──────────────┘  └─────────────────────┘  │  │    │
│  │  └───────────────────────────────────────────────────────────────┘  │    │
│  │                                                                     │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │ DhanOrderStream (WebSocket)                                  │   │    │
│  │  │ → base_streaming.py → wss://api-order-update.dhan.co         │   │    │
│  │  └──────────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│              │                                                              │
│              ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                       DOMAIN LAYER                                  │    │
│  │                                                                     │    │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────────┐   │    │
│  │  │  Order   │  │OrderResponse │  │  Trade   │  │   Side       │   │    │
│  │  │          │  │              │  │          │  │   OrderType  │   │    │
│  │  │          │  │              │  │          │  │   OrderStatus│   │    │
│  │  │          │  │              │  │          │  │   ProductType│   │    │
│  │  │          │  │              │  │          │  │   Validity   │   │    │
│  │  └──────────┘  └──────────────┘  └──────────┘  └──────────────┘   │    │
│  │                                                                     │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │ order_lifecycle.py                                           │   │    │
│  │  │ ORDER_STATUS_TRANSITIONS, is_valid_transition()              │   │    │
│  │  └──────────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Greenfield Gap Analysis

### Missing Adapters

| Archive Adapter | Greenfield Equivalent | Status | Priority |
|-----------------|----------------------|--------|----------|
| `SuperOrdersAdapter` | — | **MISSING** | P1 |
| `ForeverOrdersAdapter` | — | **MISSING** | P1 |
| `OrdersAdapter.kill_switch` | — | **MISSING** | P2 |
| `OrdersAdapter.place_slice_order` | — | **MISSING** | P2 |
| `OrdersAdapter.get_trade_book` | — | **MISSING** | P2 |
| `OrdersAdapter.get_trade_history` | — | **MISSING** | P2 |
| `OrdersAdapter.cancel_all_orders` | — | **MISSING** | P2 |

### Missing Service Features

| Archive Feature | Greenfield Equivalent | Status | Priority |
|-----------------|----------------------|--------|----------|
| `RiskManagerPort.check_order()` | — | **MISSING** | P1 |
| `EventBus.publish()` on order events | — | **MISSING** | P2 |
| Auto-generated `correlation_id` | Caller must provide | Partial | P2 |
| `canonicalize_order_enums()` | Inline maps in config.py | ✓ Covered |
| `Order.from_broker_dict()` fallback | `map_order()` | ✓ Covered |

### Missing Domain Entities

| Archive Entity | Greenfield Equivalent | Status |
|----------------|----------------------|--------|
| `SuperOrder` | — | **MISSING** |
| `SuperOrderLeg` | — | **MISSING** |
| `ForeverOrder` | — | **MISSING** |
| `ForeverOrderRequest` | — | **MISSING** |
| `ExitAllResponse` | — | **MISSING** |
| `ConditionalTrigger` | — | **MISSING** |
| `ConditionalTriggerRequest` | — | **MISSING** |

### Missing Validation

| Archive Validation | Greenfield Equivalent | Status |
|--------------------|----------------------|--------|
| Super order target/SL logic | — | **MISSING** |
| Forever order OCO fields | — | **MISSING** |
| Conditional trigger operator validation | — | **MISSING** |
| Conditional trigger comparison_type | — | **MISSING** |
| Tick size alignment (in adapter) | In service layer | ✓ Moved |
| Lot size check (in adapter) | In service layer | ✓ Moved |

### Architectural Gaps

| Concern | Archive | Greenfield | Gap |
|---------|---------|------------|-----|
| Status mapping | `status_mapper.py` with registry | Inline in `mapper.py` | **MISSING** registry pattern |
| Modify HTTP method | PUT (correct) | POST (incorrect) | **BUG** |
| Cancel HTTP method | DELETE (correct) | POST (incorrect) | **BUG** |
| Error propagation | Raises exceptions | Returns responses | Different philosophy |
| Response parsing | Full entity construction | Raw dict in some places | **INCOMPLETE** |

### Implementation Priority

1. **P0 (Blocking)**:
   - Fix HTTP methods (POST → PUT for modify, POST → DELETE for cancel)
   - Add response status parsing in cancel_order

2. **P1 (High)**:
   - Implement `DhanSuperOrders` adapter
   - Implement `DhanForeverOrders` adapter
   - Add `RiskManagerPort` integration to `OrderService`
   - Add conditional trigger modify/get operations
   - Add domain entities (SuperOrder, ForeverOrder, etc.)

3. **P2 (Medium)**:
   - Implement kill switch
   - Implement slice orders
   - Implement trade book/history
   - Add event bus integration
   - Add status mapper registry

4. **P3 (Low)**:
   - Implement cancel-all via single API call (if Dhan supports it)
   - Add correlation_id auto-generation
   - Enhance reconciliation with full broker sync
