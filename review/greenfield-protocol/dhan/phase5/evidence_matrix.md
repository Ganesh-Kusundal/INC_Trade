# Phase 5 — Order Management: Evidence Matrix

> **Protocol:** Greenfield Broker Replication — Dhan  
> **Phase:** 5 (Order Management)  
> **Date:** 2026-07-03  
> **Auditor:** Automated Review

---

## 1. Verdict Legend

| Verdict | Meaning |
|---|---|
| **IDENTICAL** | Greenfield replicates archive behavior 1:1 with no semantic drift. |
| **PARTIAL** | Greenfield covers the behavior but with reduced fidelity (missing edge cases, weaker error handling, or simplified response shape). |
| **DIVERGENT** | Greenfield implements the behavior differently — different API, different return type, or different control flow. |
| **NOT_PORTED** | Archive behavior has no greenfield equivalent. |
| **IMPROVED** | Greenfield goes beyond the archive — better error handling, cleaner abstraction, or additional safety. |

---

## 2. Full Evidence Table

### 2.1 Order Placement

| # | Behavior | Archive Source | Greenfield Source | Verdict | Evidence |
|---|---|---|---|---|---|
| P1 | Regular order placement (MARKET/LIMIT/SL) | `orders.py` `place_order()` — full payload build, idempotency cache, risk check, invariant assertion, event publish | `DhanOrders.place_order()` + `OrderService.place_order()` | **PARTIAL** | Greenfield splits responsibility across adapter + service. Adapter builds payload and posts. Service does pre-validation (fields, lot, tick, product×segment, notional). **Missing:** idempotency cache is wired in service but `check_and_set` is a stub; no event bus publish; no risk manager integration. |
| P2 | AMO (After Market Order) / validity variants | `orders.py` — validity passed via `BrokerOrderPayload.validity`, canonicalized by `canonicalize_order_enums` | `DhanOrders.place_order()` — `validity` param mapped via `VALIDITY_MAP` | **IDENTICAL** | Both map validity enums to wire format. Greenfield's `VALIDITY_MAP` covers DAY, IOC, GTT equivalently. |
| P3 | Bracket / Cover orders (Super Orders) | `super_orders.py` — `place_super_order()` with entry+target+SL legs, trailing jump, full validation of target/SL vs entry direction | — | **NOT_PORTED** | No `SuperOrders` adapter or service exists in greenfield. Entire bracket/cover order lifecycle is absent. |
| P4 | GTT / Forever Orders (SINGLE + OCO) | `forever_orders.py` — `place_forever_order()` with SINGLE/OCO flag, OCO requires price1/trigger_price1/quantity1, full validation | — | **NOT_PORTED** | No `ForeverOrders` adapter in greenfield. GTD (Good Till Date) order lifecycle is entirely absent. |
| P5 | Conditional Triggers (alert-based GTT) | `conditional_triggers.py` — `place_trigger()` with PRICE_WITH_VALUE comparison, operator validation (CROSSING_UP/DOWN, GREATER_THAN, LESS_THAN), full CRUD | `DhanConditionalTriggers.place_conditional_order()` — basic placement only | **PARTIAL** | Greenfield has placement + cancel + list but: no operator validation, no comparison_type enforcement, no modify_trigger, no get_trigger by ID, no domain entity (returns raw dict). |
| P6 | Slice orders (auto-split large orders) | `orders.py` `place_slice_order()` — POST `/orders/slicing` | — | **NOT_PORTED** | No slice order endpoint in greenfield adapter. |
| P7 | Pre-trade payload invariant assertion | `invariants.py` — `assert_dhan_payload()` called in every place/modify path; checks securityId is digit string, segment is Dhan-valid | `DhanOrders.place_order()` calls `assert_valid_dhan_payload()` | **IDENTICAL** | Greenfield has equivalent invariant module (`brokers.adapters.dhan.invariants`). Called at same boundary points. |
| P8 | Idempotency cache (check-then-act) | `orders.py` — `SimpleIdempotencyCache` with lock context manager, hit returns cached `OrderResponse` | `OrderService.place_order()` — `idempotency_cache.check_and_set()` | **PARTIAL** | Interface exists but `check_and_set` is not implemented (typed as `Any`). No lock/atomic semantics. Archive uses thread-safe lock. |
| P9 | Pre-trade risk check | `orders.py` — `risk_manager.check_order(preview)` before payload build | — | **NOT_PORTED** | No `RiskManagerPort` usage in greenfield order path. |
| P10 | Event bus publish on placement | `orders.py` — `_publish("ORDER_PLACED", order)` after successful placement | — | **NOT_PORTED** | No event bus in greenfield order path. |

### 2.2 Order Modification

| # | Behavior | Archive Source | Greenfield Source | Verdict | Evidence |
|---|---|---|---|---|---|
| M1 | Regular order modify (PUT) | `orders.py` `modify_order()` — PUT `/orders/{id}`, parses response into `Order`, fallback construction if parse fails | `DhanOrders.modify_order()` — POST to endpoint, returns `OrderResponse` | **DIVERGENT** | Archive uses PUT; greenfield uses POST (Dhan API actually accepts both). Archive returns full `Order`; greenfield returns `OrderResponse`. Archive has parse-fallback logic; greenfield delegates to `map_order_response`. |
| M2 | Super Order leg modification | `super_orders.py` `modify_super_order()` — per-leg modify (ENTRY/TARGET/SL) | — | **NOT_PORTED** | No super order adapter in greenfield. |
| M3 | Forever Order modification | `forever_orders.py` `modify_forever_order()` — full re-submission with OCO fields | — | **NOT_PORTED** | No forever order adapter in greenfield. |
| M4 | Conditional Trigger modification | `conditional_triggers.py` `modify_trigger()` — PUT `/alerts/orders/{id}` | — | **NOT_PORTED** | Greenfield `DhanConditionalTriggers` has no modify method. |

### 2.3 Order Cancellation

| # | Behavior | Archive Source | Greenfield Source | Verdict | Evidence |
|---|---|---|---|---|---|
| C1 | Single order cancel | `orders.py` `cancel_order()` — DELETE `/orders/{id}`, checks `status` ∈ {success, ok}, returns structured `OrderResponse` with error_code on failure | `DhanOrders.cancel_order()` — POST to cancel endpoint, then re-fetches order to check for FILLED race | **DIVERGENT** | Archive uses DELETE; greenfield uses POST. Greenfield adds post-cancel race detection (checks if order is already FILLED) — an **improvement** over archive. But greenfield doesn't parse broker error response body. |
| C2 | Cancel all orders | `orders.py` `cancel_all_orders()` — DELETE `/orders` (bulk) | `DhanExitAll.cancel_all_orders()` — fetches orderbook, filters active statuses, cancels each concurrently via `ThreadPoolExecutor` | **DIVERGENT** | Archive uses single bulk DELETE. Greenfield implements manual iterate-and-cancel with concurrency. Greenfield approach is more resilient (handles partial failures) but slower and more API calls. |
| C3 | Super Order leg cancellation | `super_orders.py` `cancel_super_order_leg()` — DELETE `/super/orders/{id}/{leg}` | — | **NOT_PORTED** | No super order adapter in greenfield. |
| C4 | Forever Order cancellation | `forever_orders.py` `cancel_forever_order()` — DELETE `/forever/orders/{id}` | — | **NOT_PORTED** | No forever order adapter in greenfield. |
| C5 | Conditional Trigger deletion | `conditional_triggers.py` `delete_trigger()` — DELETE `/alerts/orders/{id}` | `DhanConditionalTriggers.cancel_conditional_order()` — DELETE `/conditionalOrders/{id}` | **PARTIAL** | Greenfield has cancel but returns raw dict, no structured response parsing. |
| C6 | Kill switch | `orders.py` `kill_switch()` — POST `/killswitch?killSwitchStatus=ACTIVATE\|DEACTIVATE` | — | **NOT_PORTED** | No kill switch in greenfield. |

### 2.4 Order Book Retrieval

| # | Behavior | Archive Source | Greenfield Source | Verdict | Evidence |
|---|---|---|---|---|---|
| Q1 | Full order book | `orders.py` `get_orderbook()` — GET `/orders`, parses each via `Order.from_broker_dict` | `DhanOrders.get_orderbook()` — GET `/orders`, maps via `map_order()` | **IDENTICAL** | Both fetch and parse identically. Greenfield uses dedicated mapper function. |
| Q2 | Single order query | `orders.py` `get_order()` — GET `/orders/{id}` | `DhanOrders.get_order()` — GET by ID, handles nested `data` key and flat response | **IMPROVED** | Greenfield handles both response shapes (nested `data` and flat). Archive only handles nested. |
| Q3 | Order status lookup | `orders.py` `get_order_status()` — delegates to `get_order()` then returns `.status` | — | **NOT_PORTED** | No convenience method in greenfield. Consumer must call `get_order()` and extract status. |
| Q4 | Trade book (today) | `orders.py` `get_trade_book()` — GET `/trades` | — | **NOT_PORTED** | No trade book endpoint in greenfield adapter. |
| Q5 | Trade history (date range) | `orders.py` `get_trade_history()` — GET `/trades/{from}/{to}/{page}` with date validation | — | **NOT_PORTED** | No trade history in greenfield. |

### 2.5 Order Status Mapping

| # | Behavior | Archive Source | Greenfield Source | Verdict | Evidence |
|---|---|---|---|---|---|
| S1 | Dhan-specific status → canonical | `status_mapper.py` — `DHAN_STATUS_MAP` extends `COMMON_STATUS_MAP`, registers with `StatusMapperRegistry` keyed by `BrokerId.DHAN` | `brokers.adapters.dhan.mapper.map_order()` — inline status mapping | **DIVERGENT** | Archive uses a registry pattern with lazy registration. Greenfield uses a direct mapper function. Both cover the same status strings. Greenfield approach is simpler but less extensible. |
| S2 | Order lifecycle state machine | — (not in archive) | `order_lifecycle.py` — `ORDER_STATUS_TRANSITIONS` table, `is_valid_transition()`, `validate_transition()` | **IMPROVED** | Greenfield adds a formal state machine that the archive lacks. Validates legal status transitions. |

### 2.6 GTT Trigger Management

| # | Behavior | Archive Source | Greenfield Source | Verdict | Evidence |
|---|---|---|---|---|---|
| G1 | Place GTT trigger (PRICE_WITH_VALUE) | `conditional_triggers.py` — full validation (operator ∈ {CROSSING_UP, CROSSING_DOWN, GREATER_THAN, LESS_THAN}, comparison_type = PRICE_WITH_VALUE) | `DhanConditionalTriggers.place_conditional_order()` — no validation | **PARTIAL** | Greenfield places orders but skips all trigger-specific validation. |
| G2 | Modify GTT trigger | `conditional_triggers.py` `modify_trigger()` | — | **NOT_PORTED** | No modify in greenfield. |
| G3 | Delete GTT trigger | `conditional_triggers.py` `delete_trigger()` | `DhanConditionalTriggers.cancel_conditional_order()` | **IDENTICAL** | Both DELETE by ID. |
| G4 | Get single GTT trigger | `conditional_triggers.py` `get_trigger()` | — | **NOT_PORTED** | No single-trigger fetch in greenfield. |
| G5 | List all GTT triggers | `conditional_triggers.py` `get_all_triggers()` | `DhanConditionalTriggers.get_conditional_orders()` | **PARTIAL** | Greenfield returns raw dicts; archive parses into `ConditionalTrigger` domain entity. |
| G6 | Forever Orders (SINGLE/OCO) | `forever_orders.py` — full CRUD | — | **NOT_PORTED** | Entire Forever Order subsystem absent. |

### 2.7 Exit All Positions

| # | Behavior | Archive Source | Greenfield Source | Verdict | Evidence |
|---|---|---|---|---|---|
| E1 | Exit all (single API call) | `exit_all.py` — POST `/exitall`, parses `ExitAllResponse` (positions_closed, orders_cancelled, success) | — | **NOT_PORTED** | Greenfield does not use Dhan's native exit-all endpoint. |
| E2 | Close all positions (manual square-off) | — (archive uses single API) | `DhanExitAll.close_all_positions()` — fetches positions, computes net qty, places MARKET orders concurrently | **DIVERGENT** | Greenfield implements manual square-off with `ThreadPoolExecutor`. More granular but doesn't use Dhan's native endpoint. |
| E3 | Cancel all orders (iterate + cancel) | `orders.py` `cancel_all_orders()` — single DELETE `/orders` | `DhanExitAll.cancel_all_orders()` — fetch + filter active + concurrent cancel | **DIVERGENT** | Same divergence as C2. Greenfield is more resilient to partial failures. |

### 2.8 Payload Invariant Validation

| # | Behavior | Archive Source | Greenfield Source | Verdict | Evidence |
|---|---|---|---|---|---|
| I1 | `assert_dhan_payload()` — securityId + segment check | `invariants.py` — 5 functions: `assert_dhan_segment`, `assert_dhan_identity`, `assert_valid_security_id`, `assert_dhan_payload` | `brokers.adapters.dhan.invariants` — `assert_valid_dhan_payload()` | **IDENTICAL** | Greenfield has equivalent invariant module. Called at same boundary. |
| I2 | Carrier-shaped identity assertion | `invariants.py` `assert_dhan_identity()` — accepts `DhanInstrumentRef` carrier or loose (security_id, segment) tuple | Not observed in greenfield invariants | **PARTIAL** | Greenfield invariants module is simpler; carrier-shape detection not confirmed. |
| I3 | Defense-in-depth (PR-B) assertion | Archive calls `assert_dhan_payload` in every place/modify path with context string | `DhanOrders.place_order()` calls `assert_valid_dhan_payload(payload, context="orders.place_order")` | **IDENTICAL** | Same pattern, same context strings. |

### 2.9 Order Streaming (WebSocket)

| # | Behavior | Archive Source | Greenfield Source | Verdict | Evidence |
|---|---|---|---|---|---|
| W1 | Real-time order updates via WebSocket | — (not in archive) | `DhanOrderStream` — extends `BaseWebSocketStreaming`, connects to `wss://api-order-update.dhan.co`, parses order updates, fires `on_order_update` callback | **IMPROVED** | Greenfield adds WebSocket order streaming not present in archive. Includes reconnection logic, token refresh, and auth handshake. |
| W2 | Order update parsing | — | `DhanOrderStream._parse_order_update()` — delegates to `map_order()` | **IMPROVED** | Reuses existing mapper for consistency. |

### 2.10 Reconciliation

| # | Behavior | Archive Source | Greenfield Source | Verdict | Evidence |
|---|---|---|---|---|---|
| R1 | Background reconciliation loop | — (not in archive) | `ReconciliationEngine` — async loop, fetches broker state, compares to local ledger, raises drift alerts | **IMPROVED** | Greenfield adds reconciliation daemon not present in archive. Currently stub implementation (`_sync_orders` is a pass). |
| R2 | Local order ledger | — | `ReconciliationEngine.local_order_ledger: Dict[str, OrderResponse]` | **PARTIAL** | Data structure exists but no integration with order service to populate it. |

---

## 3. QA Validation Notes

| Area | Notes |
|---|---|
| **Payload correctness** | All greenfield adapters use `assert_valid_dhan_payload` at the boundary — matches archive's defense-in-depth. |
| **Enum mapping** | `SIDE_MAP`, `ORDER_TYPE_MAP`, `PRODUCT_TYPE_MAP`, `VALIDITY_MAP` in greenfield config are equivalent to archive's `canonicalize_order_enums()`. |
| **Error handling** | Archive has structured `OrderResponse.fail()` with error codes from broker. Greenfield `DhanOrders.cancel_order()` does NOT parse broker error body — returns generic success/fail. |
| **Live-order guard** | Both archive and greenfield check `_allow_live_orders` before every mutating operation. Coverage is equivalent. |
| **Response parsing** | Archive uses `Order.from_broker_dict()` with `DefaultFieldMapping`. Greenfield uses `map_order()` / `map_order_response()` from dedicated mapper module. |
| **Concurrency** | Greenfield `DhanExitAll` uses `ThreadPoolExecutor` for parallel position squaring / order cancellation. Archive uses sequential bulk calls. |

---

## 4. Test Results Summary

| Category | Archive Test Coverage | Greenfield Test Coverage | Gap |
|---|---|---|---|
| Order placement | Full — validation, idempotency, risk, payload build | Partial — validation in service, adapter untested | No adapter-level unit tests for `DhanOrders.place_order()` |
| Order modification | Full — parse response, fallback construction | Partial — basic happy path | No error-path tests for modify |
| Order cancellation | Full — success/failure parsing, error codes | Partial — race detection tested | No test for broker error response parsing |
| Super Orders | Full — validation, leg CRUD | **None** | Entire subsystem missing |
| Forever Orders | Full — SINGLE/OCO validation, CRUD | **None** | Entire subsystem missing |
| Conditional Triggers | Full — operator validation, CRUD | Minimal — no validation tests | Missing operator/comparison_type validation tests |
| Exit All | Full — response parsing | Partial — concurrent execution | No test for partial failure scenarios |
| Invariants | Full — segment, identity, payload, security_id | Assumed equivalent | Need to verify greenfield invariant coverage matches |
| Order Streaming | N/A (not in archive) | No tests | WebSocket mocking needed |
| Reconciliation | N/A (not in archive) | Stub only | No tests possible until implementation |

---

## 5. Confidence Distribution

| Confidence | Count | Items |
|---|---|---|
| **High (>90%)** | 12 | P1, P2, P7, Q1, Q2, C1, C2, I1, I3, W1, E2, S2 |
| **Medium (60-90%)** | 8 | P5, P8, C5, G1, G5, M1, S1, R1 |
| **Low (<60%)** | 3 | R2 (stub), W2 (no tests), P3 (not ported — severity unclear) |

---

## 6. Gap Severity Summary

| Severity | Count | Items |
|---|---|---|
| **P0 — Critical** | 2 | Super Orders (P3, M2, C3) — entire bracket order subsystem; Forever Orders (P4, M3, C4, G6) — entire GTD subsystem |
| **P1 — High** | 4 | Idempotency cache not implemented (P8); Risk manager not wired (P9); Event bus not wired (P10); Kill switch missing (C6) |
| **P2 — Medium** | 5 | Conditional trigger validation missing (G1); Trade book/history not ported (Q4, Q5); Status mapper registry pattern dropped (S1); Reconciliation is stub (R1, R2) |
| **P3 — Low** | 4 | Order status convenience method missing (Q3); Slice orders not ported (P6); Conditional trigger modify/get missing (M4, G4); Cancel error parsing (C1) |

---

## 7. Open Questions

1. **Super Orders priority:** Does the trading strategy require bracket/cover orders? If not, P0 gap can be deferred to Phase 6+.
2. **Forever Orders vs Conditional Triggers:** Archive has both. Are they redundant? Dhan's API may have deprecated Forever Orders in favor of Conditional Triggers — needs API docs verification.
3. **Idempotency backend:** `OrderService` accepts `idempotency_cache: Any` but no concrete implementation is provided. Should this be Redis-backed, in-memory with TTL, or DB-backed?
4. **Risk manager integration:** Archive wires `RiskManagerPort` in the order adapter. Greenfield has no risk manager in the order path. Is this intentional (deferred to Phase 7) or an oversight?
5. **Exit All strategy:** Greenfield's manual square-off is more resilient but uses N+1 API calls vs archive's single bulk call. Should greenfield use Dhan's native `/exitall` endpoint as primary with manual as fallback?
6. **Reconciliation scope:** `_sync_orders()` is a pass statement. What is the expected data source for the local order ledger? Should it integrate with the order streaming WebSocket?
7. **Event bus:** Archive publishes `ORDER_PLACED` domain events. Greenfield has no event bus. Is this deferred to a later phase or intentionally dropped?

---

## 8. Phase 5 Exit Criteria Validation

| Exit Criterion | Status | Notes |
|---|---|---|
| Regular order placement (MARKET/LIMIT/SL) works end-to-end | **PARTIAL** | Adapter + service exist but idempotency and risk are stubs |
| Order modification works | **PASS** | `DhanOrders.modify_order()` covers basic modify |
| Order cancellation works with error handling | **PARTIAL** | Cancel works but doesn't parse broker error body |
| Order book retrieval works | **PASS** | `get_orderbook()` and `get_order()` both functional |
| Order status mapping covers all Dhan statuses | **PASS** | Mapper covers all known Dhan statuses |
| GTT / Conditional trigger CRUD is complete | **FAIL** | Only place + cancel + list; no modify, no get-by-ID, no validation |
| Super Orders (bracket/cover) are ported | **FAIL** | Not ported |
| Forever Orders (GTD SINGLE/OCO) are ported | **FAIL** | Not ported |
| Exit All (panic button) works | **PASS** | Concurrent implementation is arguably better than archive |
| Payload invariants are enforced | **PASS** | `assert_valid_dhan_payload` called at all boundaries |
| Order streaming (WebSocket) is functional | **PARTIAL** | Adapter exists but no integration tests |
| Reconciliation engine syncs state | **FAIL** | Stub implementation |
| Kill switch is available | **FAIL** | Not ported |

**Overall Phase 5 Readiness:** 5/13 criteria pass, 4 partial, 4 fail. **Not ready for production.**
